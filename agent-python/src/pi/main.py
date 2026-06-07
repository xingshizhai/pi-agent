# src/pi/main.py
from __future__ import annotations

import argparse
import os
import sys


def _load_dotenv() -> None:
    """Load .env file from the current directory or any parent directory."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)  # don't override already-set env vars
    except ImportError:
        pass  # python-dotenv not installed, silently skip


def main() -> None:
    # Load .env before anything else so env vars are available everywhere.
    _load_dotenv()

    # Headless mode for test harness: PI_HEADLESS=1
    if os.environ.get("PI_HEADLESS") == "1":
        from .headless import run as headless_run
        headless_run()
        return

    parser = argparse.ArgumentParser(description="pi — terminal coding agent")
    parser.add_argument(
        "--model",
        default=os.environ.get("PI_MODEL"),
        help="Model ID (default depends on provider)",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("PI_PROVIDER", "anthropic"),
        choices=["anthropic", "openai", "openrouter"],
        help="LLM provider (default: anthropic)",
    )
    parser.add_argument("--session", help="Resume session by ID")
    parser.add_argument("--list-sessions", action="store_true", help="List saved sessions")
    args = parser.parse_args()

    if args.list_sessions:
        from .session.manager import SessionManager
        mgr = SessionManager()
        sessions = mgr.list_sessions()
        if not sessions:
            print("No sessions found.")
            return
        for meta in sessions:
            print(f"{meta.id[:8]}  {meta.cwd}  ({meta.message_count} messages)")
        return

    # Resolve API key and default model per provider.
    provider = args.provider
    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        default_model = "claude-sonnet-4-5"
        if not api_key:
            print("Error: ANTHROPIC_API_KEY not set (add it to .env or environment)", file=sys.stderr)
            sys.exit(1)
    elif provider == "openrouter":
        api_key = (
            os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        default_model = "anthropic/claude-sonnet-4-5"
        if not api_key:
            print("Error: OPENROUTER_API_KEY not set (add it to .env or environment)", file=sys.stderr)
            sys.exit(1)
    else:  # openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        default_model = "gpt-4o"
        if not api_key:
            print("Error: OPENAI_API_KEY not set (add it to .env or environment)", file=sys.stderr)
            sys.exit(1)

    model_id = args.model or default_model

    from .tui.app import PiApp
    cwd = os.getcwd()
    app = PiApp(model_id=model_id, api_key=api_key, cwd=cwd, provider=provider)
    app.run()


if __name__ == "__main__":
    main()
