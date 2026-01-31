# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shannon is a speech-to-text wrapper CLI for Claude Code. It spawns Claude Code in a PTY and intercepts Ctrl+R to toggle voice recording. Speech is transcribed in real-time via OpenAI's Realtime API using `gpt-4o-transcribe` and inserted into Claude Code's input.

**Platform**: macOS only (uses PortAudio for audio capture)

## Development Commands

```bash
# Create virtual environment and install
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Test audio capture
python -c "from shannon.audio import test_audio; test_audio()"

# Run Shannon
shannon
```

## Architecture

The data flow is: **User Input → PTY Wrapper → Claude Code**, with voice input handled as:

```
Ctrl+R pressed → AudioRecorder starts → chunks stream to TranscriptionSession
                                                    ↓
                                    OpenAI Realtime API (WebSocket)
                                    - Periodic commits every 3s
                                    - gpt-4o-transcribe for streaming deltas
                                                    ↓
                            Real-time UI shows transcript as it streams
                                                    ↓
Ctrl+R pressed → GPT-4o post-processes (removes filler words, fixes errors)
                                                    ↓
                    Final text inserted into PTY → Claude Code receives it
```

### Key Components

- **`cli.py`**: Entry point. Displays startup banner, checks dependencies (sounddevice, API key, claude command), creates `ClaudeWrapper`, runs async event loop.

- **`wrapper.py`**: Core PTY management.
  - `ClaudeWrapper`: Spawns Claude Code via pexpect, sets terminal to raw mode, runs concurrent input/output handlers, displays recording UI
  - `VoiceInputManager`: Coordinates audio recording and transcription, manages toggle state
  - Intercepts `CTRL_R` (0x12) from input stream, passes everything else through

- **`audio.py`**: Microphone capture using sounddevice.
  - `AudioRecorder`: Sync interface with callback, converts float32 to PCM16
  - `AsyncAudioRecorder`: Async wrapper with generator for streaming chunks
  - Audio format: 24kHz mono PCM16 (required by OpenAI Realtime API)

- **`transcriber.py`**: OpenAI Realtime API client.
  - `RealtimeTranscriber`: WebSocket connection, sends base64-encoded audio, receives transcription events
  - `TranscriptionSession`: Manages periodic commits (every 3s) for real-time updates, accumulates transcript segments
  - `postprocess_transcript()`: GPT-4o cleans up final transcript (removes filler words, fixes errors, removes trailing artifacts)
  - Uses `gpt-4o-transcribe` for true streaming deltas (text appears character by character)

- **`config.py`**: Configuration management.
  - Loads `OPENAI_API_KEY` from environment or `.env` file
  - `SHANNON_LANGUAGE`: Language hint for transcription (default: `en`)
  - `SHANNON_POSTPROCESS`: Enable/disable GPT-4o cleanup (default: `true`)
  - Audio constants: 24kHz sample rate, mono, 100ms chunks

### Real-time Transcription Flow

1. Audio chunks are continuously sent to the Realtime API via WebSocket
2. Every 3 seconds, the audio buffer is committed to trigger transcription
3. `gpt-4o-transcribe` returns streaming deltas (incremental text)
4. UI updates in real-time as deltas arrive
5. When recording stops, final commit captures remaining audio
6. GPT-4o post-processes the transcript (removes filler words like "um", "uh", fixes errors, removes trailing artifacts)
