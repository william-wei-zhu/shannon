# Shannon

Speech-to-text wrapper for Claude Code. Talk to Claude using your voice.

## Overview

Shannon wraps Claude Code and adds voice input capability. Press **Ctrl+R** to start/stop voice recording. Your speech is transcribed in real-time using OpenAI's Realtime API with `gpt-4o-transcribe` and inserted into Claude Code's input.

## Features

- **Real-time transcription**: Text appears as you speak (updates every ~1.5 seconds)
- **Streaming display**: See your transcription in a status line while recording
- **Seamless integration**: All keyboard input passes through to Claude Code
- **Colorful startup banner**: Bold ASCII art logo on launch

## Requirements

- **macOS** (uses PortAudio for audio capture)
- **Python 3.10+**
- **Claude Code** installed and available as `claude` command
- **OpenAI API key** with access to the Realtime API

## Installation

```bash
# Clone the repository
git clone https://github.com/william-wei-zhu/shannon
cd shannon

# Create virtual environment and install
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here
```

## Usage

```bash
# Activate the virtual environment
source venv/bin/activate

# Start Claude Code with voice input
shannon

# Pass arguments to Claude Code
shannon -p "help me write a function"

# Show Shannon help
shannon --help
```

### Voice Input

1. Press **Ctrl+R** to start recording
2. Speak your message - transcription appears in real-time
3. Press **Ctrl+R** again to stop recording
4. The transcribed text is inserted into Claude Code's input
5. Press Enter to send

While recording, you'll see:
```
[Recording...] Speak now. Press Ctrl+R to stop.
> your transcribed text appears here...
```

## Configuration

### Required

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=sk-your-key-here
```

Or create a `.env` file:

```
OPENAI_API_KEY=sk-your-key-here
```

## How It Works

1. **PTY Wrapper**: Uses `pexpect` to spawn Claude Code in a pseudo-terminal
2. **Input Interception**: Captures Ctrl+R to toggle voice mode, passes all other input through
3. **Audio Capture**: Uses `sounddevice` (PortAudio) to record from the microphone at 24kHz mono
4. **Real-time Transcription**: Streams audio to OpenAI Realtime API via WebSocket, using `gpt-4o-transcribe` for streaming deltas
5. **Periodic Commits**: Audio is committed every 1.5 seconds for real-time text updates
6. **Text Insertion**: Final transcribed text is injected into Claude Code's input buffer

## Troubleshooting

### "PortAudio not found"

```bash
brew install portaudio
```

### "claude command not found"

```bash
npm install -g @anthropic-ai/claude-code
```

### "OPENAI_API_KEY not found"

```bash
export OPENAI_API_KEY=sk-your-key-here
```

### Microphone not working

Grant terminal app microphone access in System Preferences > Security & Privacy > Privacy > Microphone.

## Development

```bash
# Install in development mode
python3 -m venv venv
source venv/bin/activate
pip install -e .

# Test audio capture
python -c "from shannon.audio import test_audio; test_audio()"

# Run Shannon
shannon
```

## License

MIT License - see [LICENSE](LICENSE) for details.
