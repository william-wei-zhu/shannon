"""Audio capture using sounddevice for macOS."""

import asyncio
import queue
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

from shannon.config import SAMPLE_RATE, CHANNELS, CHUNK_SIZE


class AudioRecorder:
    """Captures audio from the microphone and provides chunks for streaming."""

    def __init__(self, on_audio_chunk: Optional[Callable[[bytes], None]] = None):
        """Initialize the audio recorder.

        Args:
            on_audio_chunk: Callback function that receives audio chunks as PCM16 bytes.
        """
        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self.chunk_size = CHUNK_SIZE
        self.on_audio_chunk = on_audio_chunk

        self._recording = False
        self._stream: Optional[sd.InputStream] = None
        self._audio_queue: queue.Queue[bytes] = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Called by sounddevice for each audio chunk."""
        if status:
            pass  # Ignore status messages (xruns, etc.)

        if self._recording:
            # Convert float32 to PCM16 (int16)
            audio_int16 = (indata * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()

            # Put in queue for async processing
            self._audio_queue.put(audio_bytes)

            # Also call callback if provided
            if self.on_audio_chunk:
                self.on_audio_chunk(audio_bytes)

    def start(self):
        """Start recording audio from the microphone."""
        if self._recording:
            return

        self._recording = True
        self._audio_queue = queue.Queue()

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            self._recording = False
            raise RuntimeError(f"Failed to start audio recording: {e}") from e

    def stop(self):
        """Stop recording audio."""
        self._recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._recording

    def get_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get the next audio chunk from the queue.

        Args:
            timeout: How long to wait for a chunk in seconds.

        Returns:
            Audio chunk as PCM16 bytes, or None if no chunk available.
        """
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_queue(self):
        """Clear any pending audio chunks."""
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break


class AsyncAudioRecorder:
    """Async wrapper for AudioRecorder that yields audio chunks."""

    def __init__(self):
        self._recorder = AudioRecorder()
        self._chunks: asyncio.Queue[bytes] = asyncio.Queue()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_chunk(self, chunk: bytes):
        """Callback to put chunks into async queue."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._chunks.put_nowait, chunk)

    async def start(self):
        """Start recording."""
        self._loop = asyncio.get_event_loop()
        self._chunks = asyncio.Queue()
        self._recorder.on_audio_chunk = self._on_chunk
        self._recorder.start()

    async def stop(self):
        """Stop recording."""
        self._recorder.stop()
        self._recorder.on_audio_chunk = None

    def is_recording(self) -> bool:
        """Check if recording."""
        return self._recorder.is_recording()

    async def get_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get next audio chunk asynchronously."""
        try:
            return await asyncio.wait_for(self._chunks.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def chunks(self):
        """Async generator that yields audio chunks while recording."""
        while self._recorder.is_recording():
            chunk = await self.get_chunk()
            if chunk:
                yield chunk


def test_audio():
    """Test audio capture - records for 3 seconds and prints chunk info."""
    import time

    print("Testing audio capture...")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Channels: {CHANNELS}")
    print(f"Chunk size: {CHUNK_SIZE} samples")
    print()

    chunks_received = 0
    total_bytes = 0

    def on_chunk(chunk: bytes):
        nonlocal chunks_received, total_bytes
        chunks_received += 1
        total_bytes += len(chunk)

    recorder = AudioRecorder(on_audio_chunk=on_chunk)

    print("Recording for 3 seconds...")
    recorder.start()
    time.sleep(3)
    recorder.stop()

    print(f"Chunks received: {chunks_received}")
    print(f"Total bytes: {total_bytes}")
    print(f"Average chunk size: {total_bytes / chunks_received if chunks_received else 0:.0f} bytes")
    print("Audio test complete!")


if __name__ == "__main__":
    test_audio()
