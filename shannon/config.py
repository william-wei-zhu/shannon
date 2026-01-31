"""Configuration management for Shannon."""

import os
from dotenv import load_dotenv

# Load .env file from current directory or parent directories
load_dotenv()


def get_api_key() -> str:
    """Get OpenAI API key from environment."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not found. Please set it in your environment or .env file.\n"
            "Example: export OPENAI_API_KEY=sk-your-key-here"
        )
    return api_key


# Audio settings (required by OpenAI Realtime API)
SAMPLE_RATE = 24000  # 24kHz required by Realtime API
CHANNELS = 1  # Mono audio
CHUNK_DURATION_MS = 100  # Send audio every 100ms
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION_MS / 1000)  # Samples per chunk

# OpenAI Realtime API settings
REALTIME_MODEL = "gpt-4o-realtime-preview-2024-12-17"
REALTIME_API_URL = "wss://api.openai.com/v1/realtime"
TRANSCRIPTION_MODEL = "gpt-4o-transcribe"  # Supports streaming deltas

# Transcription language (ISO-639-1 code) - improves accuracy and latency
# Set to None for auto-detection, or specify: "en", "es", "zh", "ja", etc.
TRANSCRIPTION_LANGUAGE = os.getenv("SHANNON_LANGUAGE", "en")

# Post-processing settings
# Set SHANNON_POSTPROCESS=false to disable post-processing
POSTPROCESS_ENABLED = os.getenv("SHANNON_POSTPROCESS", "true").lower() == "true"
POSTPROCESS_MODEL = "gpt-4o"  # Use full model for reliable text cleanup
