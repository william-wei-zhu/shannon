# Shannon

**Talk to Claude Code using your voice.** Shannon is a speech-to-text wrapper that adds voice input to Claude Code. Press Ctrl+R, speak, and your words appear as text.

## Quick Start

```bash
# 1. Install PortAudio (required for microphone access)
brew install portaudio

# 2. Clone and install Shannon
git clone https://github.com/william-wei-zhu/shannon
cd shannon
python3 -m venv venv
source venv/bin/activate
pip install -e .

# 3. Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# 4. Run Shannon
shannon
```

That's it! Press **Ctrl+R** to start/stop voice recording.

## Requirements

| Requirement | How to get it |
|-------------|---------------|
| macOS | Required for PortAudio audio capture |
| Python 3.10+ | `brew install python` or [python.org](https://python.org) |
| PortAudio | `brew install portaudio` |
| Claude Code | `npm install -g @anthropic-ai/claude-code` |
| OpenAI API key | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |

## How to Use

1. **Start Shannon** - Run `shannon` (this launches Claude Code with voice support)
2. **Press Ctrl+R** - Start recording, you'll see:
   ```
   [Recording...] Speak now. Press Ctrl+R to stop.
   > your transcribed text appears here...
   ```
3. **Speak** - Your speech is transcribed in real-time
4. **Press Ctrl+R again** - Stop recording, text is inserted into Claude Code
5. **Press Enter** - Send your message to Claude

All other keyboard shortcuts work normally - Shannon just adds voice input on top.

## Configuration

### Required: OpenAI API Key

Set via environment variable:
```bash
export OPENAI_API_KEY=sk-your-key-here
```

Or create a `.env` file in the shannon directory:
```
OPENAI_API_KEY=sk-your-key-here
```

### Optional Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SHANNON_LANGUAGE` | `en` | Language hint for transcription (ISO-639-1: `en`, `es`, `zh`, `ja`, etc.) |
| `SHANNON_POSTPROCESS` | `true` | GPT-4o cleans up transcription errors, grammar, and filler words |

```bash
# Example: Spanish transcription without post-processing
export SHANNON_LANGUAGE=es
export SHANNON_POSTPROCESS=false
```

## Features

- **Real-time transcription** - Text appears as you speak (updates every ~3 seconds)
- **Smart cleanup** - GPT-4o fixes transcription errors, grammar, and removes filler words
- **Multi-language** - Support for any language via language hints
- **Seamless** - All keyboard input passes through to Claude Code normally

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
Grant microphone access: **System Settings > Privacy & Security > Microphone** and enable your terminal app.

### Audio test
```bash
source venv/bin/activate
python -c "from shannon.audio import test_audio; test_audio()"
```

## How It Works

Shannon spawns Claude Code in a pseudo-terminal and intercepts the Ctrl+R key:

1. **Ctrl+R pressed** - Starts recording audio from microphone (24kHz mono)
2. **Audio streaming** - Chunks are sent to OpenAI Realtime API via WebSocket
3. **Live transcription** - `gpt-4o-transcribe` returns text as you speak
4. **Ctrl+R pressed again** - Recording stops, GPT-4o cleans up the transcript
5. **Text inserted** - Final text appears in Claude Code's input

## License

MIT License - see [LICENSE](LICENSE) for details.
