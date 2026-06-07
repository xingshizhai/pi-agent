# src/pi/main.py
from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="pi — terminal coding agent")
    parser.add_argument(
        "--model",
        default=os.environ.get("PI_MODEL", "claude-sonnet-4-6"),
        help="Model ID (default: claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--provider",
        default="anthropic",
        choices=["anthropic", "openai"],
        help="LLM provider",
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

    if args.provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable not set", file=sys.stderr)
            sys.exit(1)
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            print("Error: OPENAI_API_KEY environment variable not set", file=sys.stderr)
            sys.exit(1)

    from .tui.app import PiApp
    cwd = os.getcwd()
    app = PiApp(model_id=args.model, api_key=api_key, cwd=cwd)
    app.run()


if __name__ == "__main__":
    main()
