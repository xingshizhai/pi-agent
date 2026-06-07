import time
import pytest
from pi.ai.types import (
    TextContent, ToolCall, Usage,
    UserMessage, AssistantMessage, ToolResultMessage,
    TextDelta, ToolCallEnd, StreamDone,
)


def test_text_content_type_literal():
    tc = TextContent(text="hello")
    assert tc.type == "text"
    assert tc.text == "hello"


def test_tool_call_fields():
    tc = ToolCall(id="tc_1", name="read", arguments={"path": "/tmp/foo"})
    assert tc.type == "tool_call"
    assert tc.name == "read"
    assert tc.arguments == {"path": "/tmp/foo"}


def test_user_message_defaults():
    msg = UserMessage(content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp > 0


def test_assistant_message_defaults():
    msg = AssistantMessage(content=[TextContent(text="hi")])
    assert msg.role == "assistant"
    assert msg.stop_reason == "stop"
    assert msg.usage.input == 0


def test_tool_result_message():
    msg = ToolResultMessage(
        tool_call_id="tc_1",
        tool_name="read",
        content=[TextContent(text="file contents")],
    )
    assert msg.role == "tool_result"
    assert not msg.is_error


def test_stream_events_are_dataclasses():
    msg = AssistantMessage(content=[])
    delta = TextDelta(index=0, delta="hello", partial=msg)
    assert delta.delta == "hello"
    assert delta.index == 0

    done = StreamDone(stop_reason="stop", message=msg)
    assert done.stop_reason == "stop"
