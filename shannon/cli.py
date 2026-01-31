"""Main CLI entry point for Shannon."""

import asyncio
import sys

from shannon.config import get_api_key
from shannon.wrapper import ClaudeWrapper


def check_dependencies():
    """Check that required dependencies are available."""
    errors = []

    # Check for sounddevice
    try:
        import sounddevice
    except ImportError:
        errors.append("sounddevice not installed. Run: pip install sounddevice")
    except OSError as e:
        errors.append(f"PortAudio not found (required by sounddevice): {e}")

    # Check for OpenAI API key
    try:
        get_api_key()
    except ValueError as e:
        errors.append(str(e))

    # Check for claude command
    import shutil
    if not shutil.which("claude"):
        errors.append("'claude' command not found. Please install Claude Code first.")

    return errors


def print_help():
    """Print Shannon help message."""
    help_text = """
Shannon: Speech-to-text wrapper for Claude Code

Usage: shannon [claude options...]

Shannon wraps Claude Code and adds voice input capability.
Press Ctrl+R while in Claude Code to toggle voice recording.

Voice Input:
  Ctrl+R    Start/stop voice recording
            When recording stops, transcribed text is inserted at cursor

Requirements:
  - OPENAI_API_KEY environment variable (for transcription)
  - 'claude' command available in PATH
  - macOS with microphone access

Examples:
  shannon                    Start Claude Code with voice input
  shannon --help             Show this help (not Claude's help)
  shannon -p "hello"         Pass arguments to Claude Code

Environment:
  OPENAI_API_KEY            Required. Your OpenAI API key.
  SHANNON_SAMPLE_RATE       Audio sample rate (default: 24000)
"""
    print(help_text.strip())


def main():
    """Main entry point."""
    # Handle our own --help
    if "--help" in sys.argv or "-h" in sys.argv:
        # Check if it's the only argument (show our help)
        if len(sys.argv) == 2:
            print_help()
            return 0

    # Check dependencies
    errors = check_dependencies()
    if errors:
        print("Shannon startup failed:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("\nPlease resolve these issues and try again.", file=sys.stderr)
        return 1

    # Get arguments to pass to Claude
    claude_args = sys.argv[1:]

    # Create and run wrapper
    wrapper = ClaudeWrapper(claude_args)

    try:
        exit_code = asyncio.run(wrapper.run())
        return exit_code if exit_code is not None else 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
