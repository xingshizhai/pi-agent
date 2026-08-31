# src/pi/main.py
"""CLI 入口层 — 程序启动点（对应 architecture.md 第二节 CLI 入口层）

职责：
  1. 加载 .env 环境变量
  2. 解析命令行参数
  3. 路由到 TUI 模式（默认）或 Headless 模式（PI_HEADLESS=1）
  4. 校验 API Key，选择 Provider 和默认模型

不包含业务逻辑，只做配置与启动。
"""
from __future__ import annotations

import argparse
import os
import sys


def _load_dotenv() -> None:
    """从当前目录或父目录加载 .env，不覆盖已设置的环境变量。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except ImportError:
        pass


def main() -> None:
    _load_dotenv()

    # 跨语言测试 harness 使用：stdin JSON → stdout NDJSON，无 TUI
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
        default=os.environ.get("PI_PROVIDER", "kimi"),
        choices=["anthropic", "openai", "openrouter", "kimi"],
        help="LLM provider (default: kimi)",
    )
    parser.add_argument("--session", help="Resume session by ID (or unique ID prefix)")
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

    # 按 provider 解析 API Key 和默认模型
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
    elif provider == "kimi":
        api_key = (
            os.environ.get("KIMI_API_KEY")
            or os.environ.get("MOONSHOT_API_KEY", "")
        )
        default_model = os.environ.get("KIMI_DEFAULT_MODEL", "kimi-for-coding")
        if not api_key:
            print("Error: KIMI_API_KEY not set (add it to .env or environment)", file=sys.stderr)
            sys.exit(1)
    else:  # openai
        api_key = os.environ.get("OPENAI_API_KEY", "")
        default_model = "gpt-4o"
        if not api_key:
            print("Error: OPENAI_API_KEY not set (add it to .env or environment)", file=sys.stderr)
            sys.exit(1)

    model_id = args.model or default_model

    session_id = None
    if args.session:
        from .session.manager import SessionManager
        mgr = SessionManager()
        if (mgr.dir / f"{args.session}.pi").exists():
            session_id = args.session
        else:
            matches = [m for m in mgr.list_sessions() if m.id.startswith(args.session)]
            if len(matches) == 1:
                session_id = matches[0].id
            elif not matches:
                print(f"Error: no session found matching '{args.session}'", file=sys.stderr)
                sys.exit(1)
            else:
                ids = ", ".join(m.id[:8] for m in matches)
                print(f"Error: ambiguous session ID '{args.session}', matches: {ids}", file=sys.stderr)
                sys.exit(1)

    from .tui.app import PiApp
    cwd = os.getcwd()
    app = PiApp(model_id=model_id, api_key=api_key, cwd=cwd, provider=provider, session_id=session_id)
    app.run()   # 进入 Textual 事件循环，阻塞直到用户退出


if __name__ == "__main__":
    main()
