// Package headless implements the PI_HEADLESS=1 test protocol.
//
// Input (stdin, JSON):
//
//	{"prompt": "...", "mock_turns": [...] | null, "cwd": "..."}
//
// Output (stdout, NDJSON):
//
//	{"type": "agent_start"}
//	{"type": "turn_start",  "turn": 1}
//	{"type": "tool_call",   "id": "t1", "name": "read",   "args": {...}}
//	{"type": "tool_result", "id": "t1", "name": "read",   "content": "...", "is_error": false}
//	{"type": "turn_end",    "turn": 1}
//	{"type": "agent_end",   "turns": 2}
//	{"type": "error",       "message": "..."}   (only on fatal errors)
package headless

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"

	"github.com/pi-agent/agent-go/internal/agent"
	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/ai/mock"
	"github.com/pi-agent/agent-go/internal/tools"
)

// Input is the JSON payload read from stdin.
type Input struct {
	Prompt     string           `json:"prompt"`
	MockTurns  []mock.TurnSpec  `json:"mock_turns"`
	CWD        string           `json:"cwd"`
	HasMock    bool             // set internally: mock_turns key was present
}

// UnmarshalJSON handles the distinction between null and absent mock_turns.
func (inp *Input) UnmarshalJSON(data []byte) error {
	type Alias Input
	var raw struct {
		Alias
		MockTurns *[]mock.TurnSpec `json:"mock_turns"`
	}
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	*inp = Input(raw.Alias)
	if raw.MockTurns != nil {
		inp.MockTurns = *raw.MockTurns
		inp.HasMock = true
	}
	return nil
}

const systemPrompt = `You are a coding assistant. You have access to tools to read, write, ` +
	`and edit files, run bash commands, search for files and content, and list directories.

Guidelines:
- Use read to examine files before editing them.
- Use edit (with the edits array) instead of write when making targeted changes.
- Use bash for running tests, builds, and shell commands.
- Work methodically. When you finish, summarise what you did.`

// Run reads stdin, executes the agent, writes NDJSON events to stdout.
func Run(apiKey, providerName, modelID string) error {
	// Parse input from stdin.
	rawBytes, err := io.ReadAll(os.Stdin)
	if err != nil {
		return fmt.Errorf("headless: read stdin: %w", err)
	}
	var inp Input
	if err := json.Unmarshal(rawBytes, &inp); err != nil {
		return fmt.Errorf("headless: parse stdin: %w", err)
	}

	// Resolve working directory.
	cwd := inp.CWD
	if cwd == "" {
		var err error
		cwd, err = os.Getwd()
		if err != nil {
			cwd = "."
		}
	}

	// Build provider.
	var prov ai.Provider
	if inp.HasMock {
		prov = mock.New(inp.MockTurns)
	} else {
		prov = buildRealProvider(providerName, apiKey)
	}

	// Build agent context.
	agentCtx := &agent.Context{
		SystemPrompt: systemPrompt,
		Messages:     nil,
		Tools:        buildTools(cwd),
		ModelID:      modelID,
		Provider:     providerName,
		APIKey:       apiKey,
	}

	// Override max turns from env.
	cfg := agent.DefaultConfig()
	if v := os.Getenv("PI_MAX_TURNS"); v != "" {
		var n int
		if _, err := fmt.Sscanf(v, "%d", &n); err == nil && n > 0 {
			cfg.MaxTurns = n
		}
	}

	// Run agent loop and emit NDJSON events.
	ctx := context.Background()
	eventCh := agent.Run(ctx, inp.Prompt, agentCtx, prov, cfg)

	emit := func(v any) {
		b, _ := json.Marshal(v)
		fmt.Println(string(b))
	}

	turn := 0
	for ev := range eventCh {
		switch ev.Type {
		case agent.EventAgentStart:
			emit(map[string]any{"type": "agent_start"})

		case agent.EventTurnStart:
			turn++
			emit(map[string]any{"type": "turn_start", "turn": turn})

		case agent.EventTurnEnd:
			emit(map[string]any{
				"type":          "turn_end",
				"turn":          turn,
				"input_tokens":  ev.InputTokens,
				"output_tokens": ev.OutputTokens,
			})

		case agent.EventStreamChunk:
			// Stream chunks are noisy; omit from headless output to keep it clean.
			// TUI uses them; tests don't need them.

		case agent.EventToolExecStart:
			emit(map[string]any{
				"type": "tool_call",
				"id":   ev.ToolCallID,
				"name": ev.ToolName,
				"args": ev.ToolArgs,
			})

		case agent.EventToolExecUpdate:
			// Partial updates — skip in headless mode.

		case agent.EventToolExecEnd:
			content := ""
			if ev.ToolResult != nil {
				content = ev.ToolResult.Content
			}
			emit(map[string]any{
				"type":     "tool_result",
				"id":       ev.ToolCallID,
				"name":     ev.ToolName,
				"content":  content,
				"is_error": ev.IsError,
			})

		case agent.EventAgentEnd:
			emit(map[string]any{
				"type":         "agent_end",
				"turns":        turn,
				"error_message": ev.ErrorMessage,
			})

		case agent.EventError:
			emit(map[string]any{
				"type":    "error",
				"message": ev.ErrorMessage,
			})
		}
	}

	return nil
}

func buildTools(cwd string) []tools.Tool {
	return []tools.Tool{
		tools.NewReadTool(cwd),
		tools.NewWriteTool(cwd),
		tools.NewEditTool(cwd),
		tools.NewBashTool(cwd),
		tools.NewFindTool(cwd),
		tools.NewGrepTool(cwd),
		tools.NewLsTool(cwd),
	}
}
