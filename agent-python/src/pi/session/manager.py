# src/pi/session/manager.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..ai.types import (
    AssistantMessage, Message, TextContent, ThinkingContent,
    ToolCall, ToolResultMessage, UserMessage, Usage,
)

DEFAULT_SESSION_DIR = Path.home() / ".pi" / "sessions"


@dataclass
class Session:
    id: str
    cwd: str
    created_at: str
    messages: list[Message] = field(default_factory=list)
    model_id: str = ""
    thinking_level: str = "none"


@dataclass
class SessionMeta:
    id: str
    cwd: str
    created_at: str
    message_count: int


class SessionManager:
    def __init__(self, session_dir: Path | str | None = None) -> None:
        self.dir = Path(session_dir) if session_dir else DEFAULT_SESSION_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.pi"

    def new_session(self, cwd: str) -> Session:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        session = Session(id=session_id, cwd=cwd, created_at=now)

        header = {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": now,
            "cwd": cwd,
        }
        self._path(session_id).write_text(json.dumps(header) + "\n", encoding="utf-8")
        return session

    def append_message(self, session: Session, message: Message) -> None:
        entry_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        lines = self._path(session.id).read_text().splitlines()
        parent_id = None
        if len(lines) > 1:
            try:
                last = json.loads(lines[-1])
                parent_id = last.get("id")
            except (json.JSONDecodeError, KeyError):
                pass

        msg_dict = _message_to_dict(message)

        entry = {
            "type": "message",
            "id": entry_id,
            "parentId": parent_id,
            "timestamp": now,
            "message": msg_dict,
        }
        with self._path(session.id).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        session.messages.append(message)

    def load_session(self, session_id: str) -> Session:
        path = self._path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        lines = path.read_text(encoding="utf-8").splitlines()
        header = json.loads(lines[0])

        session = Session(
            id=header["id"],
            cwd=header.get("cwd", ""),
            created_at=header.get("timestamp", ""),
        )

        for line in lines[1:]:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("type") == "message":
                msg = _dict_to_message(entry["message"])
                if msg:
                    session.messages.append(msg)
            elif entry.get("type") == "model_change":
                session.model_id = entry.get("modelId", "")

        return session

    def list_sessions(self) -> list[SessionMeta]:
        metas: list[SessionMeta] = []
        for path in sorted(self.dir.glob("*.pi"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
                header = json.loads(lines[0])
                if header.get("type") != "session":
                    continue
                msg_count = sum(
                    1 for line in lines[1:]
                    if line.strip() and json.loads(line).get("type") == "message"
                )
                metas.append(SessionMeta(
                    id=header["id"],
                    cwd=header.get("cwd", ""),
                    created_at=header.get("timestamp", ""),
                    message_count=msg_count,
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        return metas

    def delete_session(self, session_id: str) -> None:
        path = self._path(session_id)
        if path.exists():
            path.unlink()


def _message_to_dict(msg: Message) -> dict:
    if isinstance(msg, UserMessage):
        return {"role": "user", "content": msg.content, "timestamp": msg.timestamp}
    if isinstance(msg, AssistantMessage):
        blocks = []
        for block in msg.content:
            if isinstance(block, TextContent):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolCall):
                blocks.append({
                    "type": "tool_call",
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.arguments,
                })
            elif isinstance(block, ThinkingContent):
                blocks.append({"type": "thinking", "thinking": block.thinking})
        return {
            "role": "assistant",
            "content": blocks,
            "model": msg.model,
            "stop_reason": msg.stop_reason,
            "usage": {"input": msg.usage.input, "output": msg.usage.output},
            "timestamp": msg.timestamp,
        }
    if isinstance(msg, ToolResultMessage):
        return {
            "role": "tool_result",
            "tool_call_id": msg.tool_call_id,
            "tool_name": msg.tool_name,
            "content": [{"type": "text", "text": c.text} for c in msg.content],
            "is_error": msg.is_error,
            "timestamp": msg.timestamp,
        }
    return {}


def _dict_to_message(d: dict) -> Message | None:
    role = d.get("role")
    if role == "user":
        return UserMessage(content=d.get("content", ""), timestamp=d.get("timestamp", 0))
    if role == "assistant":
        content_blocks = []
        for block in d.get("content", []):
            btype = block.get("type")
            if btype == "text":
                content_blocks.append(TextContent(text=block["text"]))
            elif btype == "tool_call":
                content_blocks.append(ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=block.get("arguments", {}),
                ))
            elif btype == "thinking":
                content_blocks.append(ThinkingContent(thinking=block["thinking"]))
        usage_raw = d.get("usage", {})
        return AssistantMessage(
            content=content_blocks,
            model=d.get("model", ""),
            stop_reason=d.get("stop_reason", "stop"),
            usage=Usage(input=usage_raw.get("input", 0), output=usage_raw.get("output", 0)),
            timestamp=d.get("timestamp", 0),
        )
    if role == "tool_result":
        content = [TextContent(text=c.get("text", "")) for c in d.get("content", [])]
        return ToolResultMessage(
            tool_call_id=d.get("tool_call_id", ""),
            tool_name=d.get("tool_name", ""),
            content=content,
            is_error=d.get("is_error", False),
            timestamp=d.get("timestamp", 0),
        )
    return None
