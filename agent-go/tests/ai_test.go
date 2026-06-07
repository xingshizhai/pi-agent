package tests

import (
	"strings"
	"testing"

	"github.com/pi-agent/agent-go/internal/ai"
)

// ---- SSE parsing ------------------------------------------------------------

func TestParseSSE_Basic(t *testing.T) {
	input := "event: message_start\ndata: {\"type\":\"message_start\"}\n\ndata: {\"type\":\"content_block_delta\"}\n\n"
	ch := ai.ParseSSE(strings.NewReader(input))

	ev1 := <-ch
	if ev1.Event != "message_start" {
		t.Errorf("expected event=message_start, got %q", ev1.Event)
	}
	if ev1.Data != `{"type":"message_start"}` {
		t.Errorf("unexpected data: %q", ev1.Data)
	}

	ev2 := <-ch
	if ev2.Data != `{"type":"content_block_delta"}` {
		t.Errorf("unexpected data: %q", ev2.Data)
	}

	_, ok := <-ch
	if ok {
		t.Error("channel should be closed after input exhausted")
	}
}

func TestParseSSE_DataPrefix(t *testing.T) {
	// data: lines must have the leading space stripped per SSE spec
	input := "data: hello world\n\n"
	ch := ai.ParseSSE(strings.NewReader(input))
	ev := <-ch
	if ev.Data != "hello world" {
		t.Errorf("expected 'hello world', got %q", ev.Data)
	}
}

func TestParseSSE_CommentSkipped(t *testing.T) {
	input := ": this is a comment\ndata: real\n\n"
	ch := ai.ParseSSE(strings.NewReader(input))
	ev := <-ch
	if ev.Data != "real" {
		t.Errorf("expected 'real', got %q", ev.Data)
	}
}

func TestParseSSE_MultilineData(t *testing.T) {
	input := "data: line1\ndata: line2\n\n"
	ch := ai.ParseSSE(strings.NewReader(input))
	ev := <-ch
	if !strings.Contains(ev.Data, "line1") || !strings.Contains(ev.Data, "line2") {
		t.Errorf("expected multiline data, got %q", ev.Data)
	}
}

// ---- ContentBlock helpers ---------------------------------------------------

func TestContentBlock_Text(t *testing.T) {
	b := ai.NewTextBlock("hello")
	if b.Type() != "text" {
		t.Errorf("expected type=text, got %q", b.Type())
	}
	tc, ok := b.AsText()
	if !ok {
		t.Fatal("AsText returned false")
	}
	if tc.Text != "hello" {
		t.Errorf("expected 'hello', got %q", tc.Text)
	}
}

func TestContentBlock_ToolCall(t *testing.T) {
	args := map[string]any{"path": "foo.txt"}
	b := ai.NewToolCallBlock("id1", "read", args)
	if b.Type() != "tool_call" {
		t.Errorf("expected type=tool_call, got %q", b.Type())
	}
	tc, ok := b.AsToolCall()
	if !ok {
		t.Fatal("AsToolCall returned false")
	}
	if tc.Name != "read" {
		t.Errorf("expected name=read, got %q", tc.Name)
	}
	if tc.Arguments["path"] != "foo.txt" {
		t.Errorf("unexpected arguments: %v", tc.Arguments)
	}
}

func TestContentBlock_ToolResult(t *testing.T) {
	b := ai.NewToolResultBlock("call1", "read", "file content", false)
	if b.Type() != "tool_result" {
		t.Errorf("expected type=tool_result, got %q", b.Type())
	}
	tr, ok := b.AsToolResult()
	if !ok {
		t.Fatal("AsToolResult returned false")
	}
	if tr.ToolCallID != "call1" {
		t.Errorf("unexpected tool_call_id: %q", tr.ToolCallID)
	}
	if tr.IsError {
		t.Error("expected IsError=false")
	}
}
