// Package mock provides a deterministic AI provider for testing.
// It replays pre-defined turns without making any HTTP calls.
package mock

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/pi-agent/agent-go/internal/ai"
)

// ToolCallSpec describes a single tool call in a mock turn.
type ToolCallSpec struct {
	ID   string         `json:"id"`
	Name string         `json:"name"`
	Args map[string]any `json:"args"`
}

// TurnSpec describes one full LLM response turn.
type TurnSpec struct {
	ToolCalls  []ToolCallSpec `json:"tool_calls"`
	Text       string         `json:"text"`
	StopReason string         `json:"stop_reason"` // "tool_use" | "end_turn" | "stop"
}

// Provider replays TurnSpec slices as LLM responses.
type Provider struct {
	turns []TurnSpec
	idx   int
}

func New(turns []TurnSpec) *Provider {
	return &Provider{turns: turns}
}

// NewFromJSON parses a JSON array of TurnSpec and returns a Provider.
func NewFromJSON(raw []byte) (*Provider, error) {
	var turns []TurnSpec
	if err := json.Unmarshal(raw, &turns); err != nil {
		return nil, fmt.Errorf("mock provider: parse turns: %w", err)
	}
	return New(turns), nil
}

func (p *Provider) Stream(_ context.Context, _ ai.Context, _ ai.StreamOptions) (<-chan ai.StreamEvent, error) {
	ch := make(chan ai.StreamEvent, 64)

	if p.idx >= len(p.turns) {
		go func() {
			defer close(ch)
			ch <- ai.StreamEvent{
				Type:       "done",
				StopReason: ai.StopReasonStop,
				TextDelta:  "[mock: no more turns]",
			}
		}()
		return ch, nil
	}

	turn := p.turns[p.idx]
	p.idx++

	go func() {
		defer close(ch)

		if turn.Text != "" {
			ch <- ai.StreamEvent{Type: "text_delta", TextDelta: turn.Text}
		}

		for i, tc := range turn.ToolCalls {
			id := tc.ID
			if id == "" {
				id = fmt.Sprintf("mock-tool-%d-%d", p.idx, i)
			}
			args := tc.Args
			if args == nil {
				args = map[string]any{}
			}
			ch <- ai.StreamEvent{
				Type: "tool_call",
				ToolCall: &ai.ToolCallContent{
					Type:      "tool_call",
					ID:        id,
					Name:      tc.Name,
					Arguments: args,
				},
			}
		}

		stopReason := ai.StopReason(turn.StopReason)
		switch stopReason {
		case "tool_use", "tool_calls":
			stopReason = ai.StopReasonToolUse
		case "end_turn", "stop", "":
			stopReason = ai.StopReasonStop
		}
		ch <- ai.StreamEvent{Type: "done", StopReason: stopReason}
	}()

	return ch, nil
}
