# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Shannon is a speech-to-text wrapper CLI for Claude Code. It spawns Claude Code in a PTY and intercepts Ctrl+R to toggle voice recording. Speech is transcribed via OpenAI's Realtime API and inserted into Claude Code's input.

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
                                                    ↓
Ctrl+R pressed → transcribed text inserted into PTY → Claude Code receives it
```

### Key Components

- **`cli.py`**: Entry point. Checks dependencies (sounddevice, API key, claude command), creates `ClaudeWrapper`, runs async event loop.

- **`wrapper.py`**: Core PTY management.
  - `ClaudeWrapper`: Spawns Claude Code via pexpect, sets terminal to raw mode, runs concurrent input/output handlers
  - `VoiceInputManager`: Coordinates audio recording and transcription, manages toggle state
  - Intercepts `CTRL_R` (0x12) from input stream, passes everything else through

- **`audio.py`**: Microphone capture using sounddevice.
  - `AudioRecorder`: Sync interface with callback, converts float32 to PCM16
  - `AsyncAudioRecorder`: Async wrapper with generator for streaming chunks
  - Audio format: 24kHz mono PCM16 (required by OpenAI Realtime API)

- **`transcriber.py`**: OpenAI Realtime API client.
  - `RealtimeTranscriber`: WebSocket connection, sends base64-encoded audio, receives transcription events
  - `TranscriptionSession`: Higher-level wrapper managing the full record→transcribe→return flow
  - Uses Whisper-1 for transcription via `input_audio_transcription` config

- **`config.py`**: Loads `OPENAI_API_KEY` from environment or `.env` file, defines audio constants.

### Async Pattern

The wrapper runs two concurrent tasks:
1. `_handle_input()`: Reads from stdin, intercepts Ctrl+R, forwards to PTY
2. `_handle_output()`: Reads from PTY (non-blocking), writes to stdout

Voice recording spawns a third task (`_stream_audio()`) that continuously sends audio chunks to the WebSocket.
