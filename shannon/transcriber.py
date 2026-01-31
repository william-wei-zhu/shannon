"""OpenAI Realtime API client for speech-to-text transcription."""

import asyncio
import base64
import json
from typing import Callable, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from shannon.config import get_api_key, REALTIME_API_URL, REALTIME_MODEL, TRANSCRIPTION_MODEL


class RealtimeTranscriber:
    """Handles real-time transcription using OpenAI's Realtime API."""

    def __init__(
        self,
        on_transcript_delta: Optional[Callable[[str], None]] = None,
        on_transcript_done: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the transcriber.

        Args:
            on_transcript_delta: Called with incremental transcript text.
            on_transcript_done: Called when transcription is complete with full text.
        """
        self.on_transcript_delta = on_transcript_delta
        self.on_transcript_done = on_transcript_done

        self._ws: Optional[ClientConnection] = None
        self._connected = False
        self._transcript = ""
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self):
        """Connect to the OpenAI Realtime API for transcription."""
        api_key = get_api_key()

        # Use the realtime model with transcription enabled
        url = f"{REALTIME_API_URL}?model={REALTIME_MODEL}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        self._ws = await websockets.connect(url, additional_headers=headers)
        self._connected = True
        self._transcript = ""

        # Configure the session for transcription
        await self._configure_session()

        # Start receiving messages
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def _configure_session(self):
        """Configure the session for streaming transcription."""
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm16",
                "input_audio_transcription": {
                    "model": TRANSCRIPTION_MODEL,  # gpt-4o-transcribe for streaming deltas
                },
                "turn_detection": None,  # Manual commit for periodic updates
            },
        }
        await self._send(config)

    async def _send(self, message: dict):
        """Send a message to the WebSocket."""
        if self._ws and self._connected:
            await self._ws.send(json.dumps(message))

    async def _receive_loop(self):
        """Receive and process messages from the WebSocket."""
        if not self._ws:
            return

        try:
            async for message in self._ws:
                await self._handle_message(json.loads(message))
        except websockets.exceptions.ConnectionClosed:
            self._connected = False
        except Exception:
            self._connected = False

    async def _handle_message(self, message: dict):
        """Handle a message from the Realtime API."""
        msg_type = message.get("type", "")

        if msg_type == "conversation.item.input_audio_transcription.completed":
            # Final transcription for an audio segment
            transcript = message.get("transcript", "")
            if transcript:
                self._transcript = transcript
                if self.on_transcript_done:
                    self.on_transcript_done(transcript)

        elif msg_type == "conversation.item.input_audio_transcription.delta":
            # Incremental transcription update
            delta = message.get("delta", "")
            if delta and self.on_transcript_delta:
                self.on_transcript_delta(delta)

        elif msg_type == "error":
            error = message.get("error", {})
            error_msg = error.get("message", "Unknown error")
            raise RuntimeError(f"Realtime API error: {error_msg}")

    async def send_audio(self, audio_bytes: bytes):
        """Send audio data to the API for transcription.

        Args:
            audio_bytes: PCM16 audio data at 24kHz mono.
        """
        if not self._connected:
            return

        # Base64 encode the audio
        audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")

        message = {
            "type": "input_audio_buffer.append",
            "audio": audio_b64,
        }
        await self._send(message)

    async def commit_audio(self):
        """Commit the audio buffer to trigger transcription."""
        if not self._connected:
            return

        # Commit the audio buffer - transcription events will follow automatically
        await self._send({"type": "input_audio_buffer.commit"})

    async def clear_audio(self):
        """Clear the audio buffer."""
        if not self._connected:
            return

        await self._send({"type": "input_audio_buffer.clear"})
        self._transcript = ""

    async def disconnect(self):
        """Disconnect from the API."""
        self._connected = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None

        if self._ws:
            await self._ws.close()
            self._ws = None

    def is_connected(self) -> bool:
        """Check if connected to the API."""
        return self._connected

    def get_transcript(self) -> str:
        """Get the current transcript."""
        return self._transcript


class TranscriptionSession:
    """Manages a transcription session with periodic commits for real-time streaming."""

    COMMIT_INTERVAL = 1.5  # Commit every 1.5 seconds for real-time updates

    def __init__(
        self,
        on_text_update: Optional[Callable[[str], None]] = None,
        on_complete: Optional[Callable[[str], None]] = None,
    ):
        """Initialize the transcription session.

        Args:
            on_text_update: Called with current transcript text as it updates in real-time.
            on_complete: Called when session ends with final transcript.
        """
        self.on_text_update = on_text_update
        self.on_complete = on_complete

        self._transcriber: Optional[RealtimeTranscriber] = None
        self._accumulated_text = ""  # Confirmed text from completed segments
        self._pending_text = ""  # Current streaming text
        self._running = False
        self._commit_task: Optional[asyncio.Task] = None
        self._has_audio = False

    def _on_delta(self, delta: str):
        """Handle incremental transcript updates (streaming)."""
        self._pending_text += delta
        full_text = self._accumulated_text + self._pending_text
        if self.on_text_update:
            self.on_text_update(full_text)

    def _on_done(self, text: str):
        """Handle completed transcription segment."""
        if text:
            # Add to accumulated text with space separator
            if self._accumulated_text:
                self._accumulated_text += " " + text
            else:
                self._accumulated_text = text
            self._pending_text = ""
            if self.on_text_update:
                self.on_text_update(self._accumulated_text)

    async def _periodic_commit(self):
        """Commit audio periodically for real-time updates."""
        try:
            while self._running:
                await asyncio.sleep(self.COMMIT_INTERVAL)
                if self._running and self._transcriber and self._has_audio:
                    await self._transcriber.commit_audio()
                    self._has_audio = False
        except asyncio.CancelledError:
            pass

    async def start(self):
        """Start the transcription session."""
        self._transcriber = RealtimeTranscriber(
            on_transcript_delta=self._on_delta,
            on_transcript_done=self._on_done,
        )
        await self._transcriber.connect()
        self._running = True
        self._accumulated_text = ""
        self._pending_text = ""
        self._has_audio = False

        # Start periodic commit for real-time updates
        self._commit_task = asyncio.create_task(self._periodic_commit())

    async def send_audio(self, audio_bytes: bytes):
        """Send audio data for transcription."""
        if self._transcriber and self._running:
            await self._transcriber.send_audio(audio_bytes)
            self._has_audio = True

    async def stop(self) -> str:
        """Stop the session and return the final transcript."""
        self._running = False

        # Cancel periodic commit
        if self._commit_task:
            self._commit_task.cancel()
            try:
                await self._commit_task
            except asyncio.CancelledError:
                pass
            self._commit_task = None

        if self._transcriber:
            # Commit any remaining audio
            if self._has_audio:
                await self._transcriber.commit_audio()

            # Wait for final transcription
            await asyncio.sleep(1.0)

            # Get final transcript
            final_text = self._accumulated_text
            if self._pending_text:
                final_text += (" " if final_text else "") + self._pending_text

            # Disconnect
            await self._transcriber.disconnect()
            self._transcriber = None

            if self.on_complete:
                self.on_complete(final_text)

            return final_text.strip()

        return self._accumulated_text

    def is_running(self) -> bool:
        """Check if session is running."""
        return self._running

    def get_current_text(self) -> str:
        """Get the current transcript text."""
        return self._accumulated_text + self._pending_text
