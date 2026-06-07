package agent

import (
	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/tools"
)

// ToolExecutionMode controls how multiple tool calls in a single turn are executed.
type ToolExecutionMode string

const (
	ExecutionSequential ToolExecutionMode = "sequential"
	ExecutionParallel   ToolExecutionMode = "parallel"
)

// Context is the mutable state threaded through the agent loop.
type Context struct {
	SystemPrompt string
	Messages     []ai.Message
	Tools        []tools.Tool
	ModelID      string
	Provider     string
	APIKey       string
}

// AgentEventType enumerates the kinds of events emitted during a run.
type AgentEventType string

const (
	EventAgentStart       AgentEventType = "agent_start"
	EventAgentEnd         AgentEventType = "agent_end"
	EventTurnStart        AgentEventType = "turn_start"
	EventTurnEnd          AgentEventType = "turn_end"
	EventStreamChunk      AgentEventType = "stream_chunk"
	EventToolExecStart    AgentEventType = "tool_exec_start"
	EventToolExecUpdate   AgentEventType = "tool_exec_update"
	EventToolExecEnd      AgentEventType = "tool_exec_end"
	EventError            AgentEventType = "error"
)

// AgentEvent is emitted on the events channel throughout the run.
type AgentEvent struct {
	Type AgentEventType

	// EventStreamChunk
	TextDelta string

	// EventToolExecStart / Update / End
	ToolCallID string
	ToolName   string
	ToolArgs   map[string]any

	// EventToolExecUpdate
	PartialOutput string

	// EventToolExecEnd
	ToolResult *tools.ToolResult
	IsError    bool

	// EventError / EventAgentEnd
	ErrorMessage string

	// EventAgentEnd
	NewMessages []ai.Message

	// Usage summary (EventTurnEnd)
	InputTokens  int
	OutputTokens int
}

// LoopConfig customises an agent loop run.
type LoopConfig struct {
	MaxTurns      int
	ExecutionMode ToolExecutionMode
}

func DefaultConfig() LoopConfig {
	return LoopConfig{
		MaxTurns:      50,
		ExecutionMode: ExecutionParallel,
	}
}
