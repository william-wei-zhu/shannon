"""PTY wrapper for Claude Code with voice input support."""

import asyncio
import os
import signal
import sys
import termios
import tty
from typing import List, Optional

import pexpect
from pexpect import TIMEOUT, EOF

from shannon.audio import AsyncAudioRecorder
from shannon.transcriber import TranscriptionSession


# Control character for Ctrl+R
CTRL_R = b"\x12"


class VoiceInputManager:
    """Manages voice input state and transcription."""

    def __init__(self, on_status_change=None, on_text_update=None):
        self.on_status_change = on_status_change
        self.on_text_update = on_text_update

        self._recording = False
        self._audio_recorder = AsyncAudioRecorder()
        self._transcription: Optional[TranscriptionSession] = None
        self._stream_task: Optional[asyncio.Task] = None
        self._current_text = ""

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def current_text(self) -> str:
        return self._current_text

    def _on_transcript_update(self, text: str):
        """Handle transcript updates."""
        self._current_text = text
        if self.on_text_update:
            self.on_text_update(text)

    async def start_recording(self):
        """Start voice recording and transcription."""
        if self._recording:
            return

        self._recording = True
        self._current_text = ""

        if self.on_status_change:
            self.on_status_change(True)

        # Start transcription session
        self._transcription = TranscriptionSession(
            on_text_update=self._on_transcript_update
        )
        await self._transcription.start()

        # Start audio recording
        await self._audio_recorder.start()

        # Start streaming audio to transcription
        self._stream_task = asyncio.create_task(self._stream_audio())

    async def _stream_audio(self):
        """Stream audio chunks to the transcription service."""
        try:
            async for chunk in self._audio_recorder.chunks():
                if self._transcription:
                    await self._transcription.send_audio(chunk)
        except asyncio.CancelledError:
            pass

    async def stop_recording(self) -> str:
        """Stop recording and return the transcribed text."""
        if not self._recording:
            return ""

        self._recording = False

        if self.on_status_change:
            self.on_status_change(False)

        # Stop audio recording
        await self._audio_recorder.stop()

        # Cancel streaming task
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None

        # Stop transcription and get final text
        final_text = ""
        if self._transcription:
            final_text = await self._transcription.stop()
            self._transcription = None

        return final_text or self._current_text

    async def toggle(self) -> Optional[str]:
        """Toggle recording state. Returns transcribed text when stopping."""
        if self._recording:
            return await self.stop_recording()
        else:
            await self.start_recording()
            return None


class ClaudeWrapper:
    """Wraps Claude Code with PTY and handles voice input."""

    def __init__(self, claude_args: List[str]):
        self.claude_args = claude_args
        self.child: Optional[pexpect.spawn] = None

        self._voice = VoiceInputManager(
            on_status_change=self._on_recording_change,
            on_text_update=self._on_transcript_update,
        )
        self._original_termios = None
        self._running = False
        self._status_line = ""
        self._last_transcript = ""

    def _on_recording_change(self, recording: bool):
        """Handle recording state changes."""
        if recording:
            self._show_status("[Recording...] Speak now, press Ctrl+R to stop")
        else:
            self._clear_status()

    def _on_transcript_update(self, text: str):
        """Handle real-time transcript updates."""
        if text != self._last_transcript:
            self._last_transcript = text
            self._show_status(f"[Recording] {text}")

    def _show_status(self, message: str):
        """Show a status message above the current line."""
        # Save cursor, move up, clear line, print status, restore cursor
        if self._status_line:
            # Clear previous status
            sys.stdout.write(f"\r\033[K")
        sys.stdout.write(f"\r\033[s\033[1A\033[K{message}\033[u")
        sys.stdout.flush()
        self._status_line = message

    def _clear_status(self):
        """Clear the status line."""
        if self._status_line:
            sys.stdout.write(f"\r\033[s\033[1A\033[K\033[u")
            sys.stdout.flush()
            self._status_line = ""

    def _setup_terminal(self):
        """Set terminal to raw mode."""
        if sys.stdin.isatty():
            self._original_termios = termios.tcgetattr(sys.stdin)
            tty.setraw(sys.stdin.fileno())

    def _restore_terminal(self):
        """Restore terminal to original mode."""
        if self._original_termios:
            termios.tcsetattr(
                sys.stdin, termios.TCSADRAIN, self._original_termios
            )
            self._original_termios = None

    async def _handle_input(self):
        """Handle input from the user, intercepting Ctrl+R."""
        loop = asyncio.get_event_loop()

        while self._running and self.child and self.child.isalive():
            try:
                # Read input asynchronously
                data = await loop.run_in_executor(
                    None, lambda: os.read(sys.stdin.fileno(), 1024)
                )

                if not data:
                    continue

                # Check for Ctrl+R
                if CTRL_R in data:
                    # Handle voice toggle
                    result = await self._voice.toggle()

                    if result:
                        # Insert transcribed text into Claude Code
                        self.child.send(result)

                    # Remove Ctrl+R from data and send the rest
                    data = data.replace(CTRL_R, b"")
                    if data:
                        self.child.send(data)
                else:
                    # Pass through to Claude Code
                    self.child.send(data)

            except (OSError, IOError):
                break

    async def _handle_output(self):
        """Handle output from Claude Code."""
        while self._running and self.child and self.child.isalive():
            try:
                # Use pexpect's read with timeout
                data = self.child.read_nonblocking(size=4096, timeout=0.05)
                if data:
                    # Write to stdout
                    if isinstance(data, bytes):
                        sys.stdout.buffer.write(data)
                    else:
                        sys.stdout.write(data)
                    sys.stdout.flush()
            except TIMEOUT:
                await asyncio.sleep(0.01)
            except EOF:
                break
            except Exception:
                await asyncio.sleep(0.01)

    def _handle_sigwinch(self, signum, frame):
        """Handle terminal resize."""
        if self.child:
            rows, cols = os.popen("stty size", "r").read().split()
            self.child.setwinsize(int(rows), int(cols))

    async def run(self):
        """Run the wrapped Claude Code."""
        # Build command
        cmd = "claude"
        args = self.claude_args

        # Get terminal size
        rows, cols = 24, 80
        try:
            size = os.popen("stty size", "r").read().split()
            if len(size) == 2:
                rows, cols = int(size[0]), int(size[1])
        except Exception:
            pass

        # Spawn Claude Code
        self.child = pexpect.spawn(
            cmd,
            args,
            encoding=None,  # Binary mode
            dimensions=(rows, cols),
            env=os.environ.copy(),
        )

        # Set up signal handler for window resize
        signal.signal(signal.SIGWINCH, self._handle_sigwinch)

        self._running = True
        self._setup_terminal()

        try:
            # Print help message
            sys.stdout.write("\r\n\033[90m[Shannon] Press Ctrl+R to toggle voice input\033[0m\r\n")
            sys.stdout.flush()

            # Run input and output handlers concurrently
            await asyncio.gather(
                self._handle_input(),
                self._handle_output(),
            )
        finally:
            self._running = False
            self._restore_terminal()

            # Clean up voice input if still recording
            if self._voice.is_recording:
                await self._voice.stop_recording()

            # Wait for Claude to exit
            if self.child:
                self.child.close()

        return self.child.exitstatus if self.child else 0
