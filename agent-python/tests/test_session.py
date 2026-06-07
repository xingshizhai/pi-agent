# tests/test_session.py
import json
import pytest
from pathlib import Path
from pi.session.manager import SessionManager, Session
from pi.ai.types import UserMessage, AssistantMessage, TextContent


def test_new_session_creates_file(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    session_file = tmp_path / f"{session.id}.pi"
    assert session_file.exists()
    first_line = session_file.read_text().splitlines()[0]
    header = json.loads(first_line)
    assert header["type"] == "session"
    assert header["version"] == 3
    assert header["id"] == session.id


def test_append_message_entry(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    msg = UserMessage(content="hello")
    mgr.append_message(session, msg)

    lines = (tmp_path / f"{session.id}.pi").read_text().splitlines()
    assert len(lines) == 2
    entry = json.loads(lines[1])
    assert entry["type"] == "message"
    assert entry["message"]["role"] == "user"


def test_load_session_restores_messages(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    mgr.append_message(session, UserMessage(content="hi"))
    mgr.append_message(session, AssistantMessage(content=[TextContent(text="hello!")]))

    loaded = mgr.load_session(session.id)
    assert len(loaded.messages) == 2
    assert loaded.messages[0].role == "user"
    assert loaded.messages[1].role == "assistant"


def test_list_sessions(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    s1 = mgr.new_session(cwd="/tmp")
    s2 = mgr.new_session(cwd="/home")
    sessions = mgr.list_sessions()
    ids = [s.id for s in sessions]
    assert s1.id in ids
    assert s2.id in ids


def test_delete_session(tmp_path):
    mgr = SessionManager(session_dir=tmp_path)
    session = mgr.new_session(cwd="/tmp")
    mgr.delete_session(session.id)
    assert not (tmp_path / f"{session.id}.pi").exists()
