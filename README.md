# Shannon

Speech-to-text wrapper for Claude Code. Talk to Claude using your voice.

## Overview

Shannon wraps Claude Code and adds voice input capability. Press **Ctrl+R** to start/stop voice recording. Your speech is transcribed in real-time using OpenAI's Realtime API and inserted into Claude Code's input.

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

# Install in development mode
pip install -e .

# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here
```

Or install directly from the repository:

```bash
pip install git+https://github.com/william-wei-zhu/shannon.git
```

## Usage

Run `shannon` instead of `claude`:

```bash
# Start Claude Code with voice input
shannon

# Pass arguments to Claude Code
shannon -p "help me write a function"

# Show Shannon help
shannon --help
```

### Voice Input

1. Press **Ctrl+R** to start recording
2. Speak your message
3. Press **Ctrl+R** again to stop recording
4. The transcribed text appears at your cursor
5. Edit if needed, then press Enter to send

While recording, you'll see a status indicator:
```
[Recording] Hello, I want to create a function that...
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+R | Toggle voice recording |
| All other keys | Passed through to Claude Code |

## Configuration

### Required

Set your OpenAI API key:

```bash
export OPENAI_API_KEY=sk-your-key-here
```

Or create a `.env` file in your working directory:

```
OPENAI_API_KEY=sk-your-key-here
```

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `SHANNON_SAMPLE_RATE` | 24000 | Audio sample rate (24kHz required by Realtime API) |

## How It Works

Shannon creates a pseudo-terminal (PTY) that wraps Claude Code:

1. **PTY Wrapper**: Uses `pexpect` to spawn Claude Code in a pseudo-terminal
2. **Input Interception**: Captures Ctrl+R to toggle voice mode, passes all other input through
3. **Audio Capture**: Uses `sounddevice` (PortAudio) to record from the microphone
4. **Real-time Transcription**: Streams audio to OpenAI's Realtime API via WebSocket
5. **Text Insertion**: Injects transcribed text into Claude Code's input buffer

## Troubleshooting

### "PortAudio not found"

Install PortAudio:

```bash
brew install portaudio
```

### "claude command not found"

Install Claude Code:

```bash
npm install -g @anthropic-ai/claude-code
```

### "OPENAI_API_KEY not found"

Set your API key:

```bash
export OPENAI_API_KEY=sk-your-key-here
```

### Microphone not working

Grant terminal app microphone access in System Preferences > Security & Privacy > Privacy > Microphone.

## Development

```bash
# Install in development mode
pip install -e .

# Test audio capture
python -c "from shannon.audio import test_audio; test_audio()"

# Run Shannon
shannon
```

## License

MIT License - see [LICENSE](LICENSE) for details.
