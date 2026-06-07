# tests/test_anthropic.py
from __future__ import annotations

import pytest
from pi.ai.types import (
    UserMessage, AssistantMessage, TextContent, ToolCall, ToolResultMessage,
)
from pi.ai.anthropic import convert_messages, convert_tools
from pi.tools.read import ReadTool


def test_convert_messages_user():
    msgs = [UserMessage(content="hello")]
    result = convert_messages(msgs)
    assert result == [{"role": "user", "content": "hello"}]


def test_convert_messages_tool_results_merged():
    msgs = [
        UserMessage(content="hello"),
        AssistantMessage(content=[
            ToolCall(id="tc1", name="read", arguments={"path": "/tmp/x"}),
        ]),
        ToolResultMessage(
            tool_call_id="tc1",
            tool_name="read",
            content=[TextContent(text="file contents")],
        ),
    ]
    result = convert_messages(msgs)
    assert len(result) == 3
    assert result[2]["role"] == "user"
    assert result[2]["content"][0]["type"] == "tool_result"
    assert result[2]["content"][0]["tool_use_id"] == "tc1"


def test_convert_tools():
    tools = [ReadTool()]
    result = convert_tools(tools)
    assert len(result) == 1
    assert result[0]["name"] == "read"
    assert "input_schema" in result[0]
    assert result[0]["input_schema"]["type"] == "object"


def test_convert_messages_assistant_tool_use():
    msgs = [
        AssistantMessage(content=[
            TextContent(text="I will read the file"),
            ToolCall(id="tc1", name="read", arguments={"path": "/foo"}),
        ])
    ]
    result = convert_messages(msgs)
    assert result[0]["role"] == "assistant"
    blocks = result[0]["content"]
    assert blocks[0]["type"] == "text"
    assert blocks[1]["type"] == "tool_use"
    assert blocks[1]["input"] == {"path": "/foo"}
