"""PTY wrapper for Claude Code with voice input support."""

import asyncio
import os
import signal
import sys
import termios
import time
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

    def _get_max_transcript_lines(self) -> int:
        """Calculate max transcript lines based on terminal size."""
        try:
            rows, _ = os.get_terminal_size()
        except OSError:
            rows = 24
        # Reserve 4 rows: 1 for status line, 3 for prompt/safety margin
        # Minimum of 3 lines to always show something useful
        return max(3, rows - 4)

    def __init__(self, claude_args: List[str]):
        self.claude_args = claude_args
        self.child: Optional[pexpect.spawn] = None

        self._voice = VoiceInputManager(
            on_status_change=self._on_recording_change,
            on_text_update=self._on_transcript_update,
        )
        self._original_termios = None
        self._running = False
        self._recording_display_active = False
        self._last_transcript = ""
        self._ui_lines_used = 0
        self._pause_output = False  # Pause Claude Code output during voice processing

    def _on_recording_change(self, recording: bool):
        """Handle recording state changes."""
        if recording:
            self._pause_output = True  # Pause Claude Code output while recording
            self._last_transcript = ""
            self._show_recording_ui("")
        else:
            self._clear_recording_ui()
            # Note: _pause_output stays True until text is sent to Claude Code

    def _on_transcript_update(self, text: str):
        """Handle real-time transcript updates - show in UI."""
        # Only update UI if still recording (prevents race condition with stop)
        if self._voice.is_recording and text != self._last_transcript:
            self._last_transcript = text
            self._show_recording_ui(text)

    def _wrap_text(self, text: str, width: int) -> list[str]:
        """Wrap text to specified width, returning list of lines."""
        if not text or width <= 0:
            return []

        lines = []
        words = text.split()
        current_line = ""

        for word in words:
            if not current_line:
                # Start new line
                if len(word) <= width:
                    current_line = word
                else:
                    # Word is longer than width, split it
                    while len(word) > width:
                        lines.append(word[:width])
                        word = word[width:]
                    current_line = word
            elif len(current_line) + 1 + len(word) <= width:
                # Word fits on current line
                current_line += " " + word
            else:
                # Word doesn't fit, start new line
                lines.append(current_line)
                if len(word) <= width:
                    current_line = word
                else:
                    # Word is longer than width, split it
                    while len(word) > width:
                        lines.append(word[:width])
                        word = word[width:]
                    current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    def _show_recording_ui(self, transcript: str):
        """Show recording UI with transcript below status line."""
        # Get terminal width
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            cols = 80

        # Calculate available width for transcript (accounting for "> " prefix)
        prefix = "> "
        continuation_prefix = "  "
        available_width = cols - len(prefix)

        # Wrap transcript text
        wrapped_lines = self._wrap_text(transcript, available_width) if transcript else []

        # Dynamic limit based on terminal height, keeping most recent lines
        max_lines = self._get_max_transcript_lines()
        if len(wrapped_lines) > max_lines:
            wrapped_lines = wrapped_lines[-max_lines:]

        # Total lines: 1 status + transcript lines
        total_lines = 1 + len(wrapped_lines)

        # ALWAYS clear old UI first if active (fixes growing UI bug)
        if self._recording_display_active and self._ui_lines_used > 0:
            sys.stdout.write("\033[s")  # Save cursor
            sys.stdout.write(f"\033[{self._ui_lines_used}A")  # Move up
            for _ in range(self._ui_lines_used):
                sys.stdout.write("\033[2K\n")  # Clear ENTIRE line, move down
            sys.stdout.write("\033[u")  # Restore cursor

        # If we need more lines than before, create space by printing newlines
        # This pushes cursor down so UI expands downward, not upward into previous content
        if total_lines > self._ui_lines_used:
            extra_lines = total_lines - self._ui_lines_used
            sys.stdout.write("\n" * extra_lines)

        # Save cursor position
        sys.stdout.write("\033[s")

        # Move up to start of UI area
        sys.stdout.write(f"\033[{total_lines}A")

        # Show status line (clear entire line first)
        sys.stdout.write("\033[2K")
        sys.stdout.write("\r\033[91m[Recording...]\033[0m Speak now. Press \033[1mCtrl+R\033[0m to stop.")

        # Show transcript lines
        for i, line in enumerate(wrapped_lines):
            sys.stdout.write("\n\033[2K")  # Move down and clear ENTIRE line
            line_prefix = prefix if i == 0 else continuation_prefix
            sys.stdout.write(f"\r\033[93m{line_prefix}{line}\033[0m")

        # Restore cursor position
        sys.stdout.write("\033[u")
        sys.stdout.flush()

        self._ui_lines_used = total_lines
        self._recording_display_active = True

    def _clear_recording_ui(self):
        """Clear the recording UI."""
        if self._recording_display_active and self._ui_lines_used > 0:
            # Reset terminal state and colors first
            sys.stdout.write("\033[0m")  # Reset all attributes
            # Move up to start of UI area
            sys.stdout.write(f"\033[{self._ui_lines_used}A")
            # Clear each line and move back down
            for _ in range(self._ui_lines_used):
                sys.stdout.write("\033[2K\n")  # Clear ENTIRE line, move down
            # Move cursor back up to original position (before we printed newlines for UI space)
            sys.stdout.write(f"\033[{self._ui_lines_used}A")
            # Reset terminal state again to ensure clean state for Claude Code
            sys.stdout.write("\033[0m\033[?25h")  # Reset attributes + show cursor
            sys.stdout.flush()
            self._recording_display_active = False
            self._ui_lines_used = 0

            # Small delay to ensure terminal processes the clear commands
            time.sleep(0.1)

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
                        # Insert final transcribed text into Claude Code
                        self.child.send(result.encode('utf-8'))

                    # Resume Claude Code output now that text is sent
                    self._pause_output = False

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
                    # Skip output while voice input is being processed
                    # This prevents Claude Code's cursor movements from corrupting display
                    if self._pause_output:
                        continue

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
