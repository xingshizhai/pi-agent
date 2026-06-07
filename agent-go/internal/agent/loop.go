package agent

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/tools"
)

// Run executes the agent loop for the given user message.
// Events are sent on the returned channel; the channel is closed when the loop ends.
func Run(
	ctx context.Context,
	userMsg string,
	agentCtx *Context,
	provider ai.Provider,
	config LoopConfig,
) <-chan AgentEvent {
	ch := make(chan AgentEvent, 128)

	go func() {
		defer close(ch)
		emit := func(e AgentEvent) {
			select {
			case ch <- e:
			case <-ctx.Done():
			}
		}

		emit(AgentEvent{Type: EventAgentStart})

		// Append user message.
		userMessage := ai.Message{
			Role:      ai.RoleUser,
			Content:   []ai.ContentBlock{ai.NewTextBlock(userMsg)},
			Timestamp: now(),
		}
		agentCtx.Messages = append(agentCtx.Messages, userMessage)

		// Build tool map.
		toolMap := make(map[string]tools.Tool, len(agentCtx.Tools))
		for _, t := range agentCtx.Tools {
			toolMap[t.Name()] = t
		}

		var newMessages []ai.Message
		newMessages = append(newMessages, userMessage)

		maxTurns := config.MaxTurns
		if maxTurns <= 0 {
			maxTurns = 50
		}

		for turn := 0; turn < maxTurns; turn++ {
			if ctx.Err() != nil {
				break
			}
			emit(AgentEvent{Type: EventTurnStart})

			// Build LLM context.
			llmCtx := ai.Context{
				SystemPrompt: agentCtx.SystemPrompt,
				Messages:     agentCtx.Messages,
				Tools:        buildToolDefs(agentCtx.Tools),
			}

			// Call provider.
			streamCh, err := provider.Stream(ctx, llmCtx, ai.StreamOptions{
				APIKey:    agentCtx.APIKey,
				MaxTokens: 8192,
			})
			if err != nil {
				emit(AgentEvent{Type: EventError, ErrorMessage: err.Error()})
				break
			}

			// Consume stream.
			var textBuf strings.Builder
			var toolCalls []ai.ToolCallContent
			var usage ai.Usage
			var stopReason ai.StopReason

			for ev := range streamCh {
				if ctx.Err() != nil {
					break
				}
				switch ev.Type {
				case "text_delta":
					textBuf.WriteString(ev.TextDelta)
					emit(AgentEvent{Type: EventStreamChunk, TextDelta: ev.TextDelta})
				case "tool_call":
					if ev.ToolCall != nil {
						toolCalls = append(toolCalls, *ev.ToolCall)
					}
				case "done":
					usage = ev.Usage
					stopReason = ev.StopReason
				case "error":
					emit(AgentEvent{Type: EventError, ErrorMessage: ev.ErrorMessage})
					stopReason = ai.StopReasonError
				}
			}

			if ctx.Err() != nil {
				break
			}

			// Build assistant message.
			var assistantContent []ai.ContentBlock
			if textBuf.Len() > 0 {
				assistantContent = append(assistantContent, ai.NewTextBlock(textBuf.String()))
			}
			for _, tc := range toolCalls {
				assistantContent = append(assistantContent, ai.NewToolCallBlock(tc.ID, tc.Name, tc.Arguments))
			}
			assistantMsg := ai.Message{
				Role:      ai.RoleAssistant,
				Content:   assistantContent,
				Timestamp: now(),
			}
			agentCtx.Messages = append(agentCtx.Messages, assistantMsg)
			newMessages = append(newMessages, assistantMsg)

			emit(AgentEvent{
				Type:         EventTurnEnd,
				InputTokens:  usage.InputTokens,
				OutputTokens: usage.OutputTokens,
			})

			// Stop if no tool calls or error.
			if len(toolCalls) == 0 || stopReason == ai.StopReasonError {
				break
			}

			// Execute tools.
			outcomes := executeTools(ctx, toolCalls, toolMap, config.ExecutionMode, emit)

			// Build tool result messages and append.
			for _, o := range outcomes {
				tr := ai.Message{
					Role: ai.RoleToolResult,
					Content: []ai.ContentBlock{
						ai.NewToolResultBlock(o.call.ID, o.call.Name, o.result.Content, o.result.IsError),
					},
					Timestamp: now(),
				}
				agentCtx.Messages = append(agentCtx.Messages, tr)
				newMessages = append(newMessages, tr)
			}

			// Check if any tool requested termination.
			allTerminate := len(outcomes) > 0
			for _, o := range outcomes {
				if !o.result.Terminate {
					allTerminate = false
					break
				}
			}
			if allTerminate {
				break
			}
		}

		if ctx.Err() != nil {
			emit(AgentEvent{
				Type:         EventAgentEnd,
				ErrorMessage: fmt.Sprintf("cancelled: %v", ctx.Err()),
				NewMessages:  newMessages,
			})
			return
		}

		emit(AgentEvent{Type: EventAgentEnd, NewMessages: newMessages})
	}()

	return ch
}

func buildToolDefs(ts []tools.Tool) []ai.ToolDefinition {
	defs := make([]ai.ToolDefinition, len(ts))
	for i, t := range ts {
		defs[i] = ai.ToolDefinition{
			Name:        t.Name(),
			Description: t.Description(),
			InputSchema: t.Schema(),
		}
	}
	return defs
}

func now() int64 {
	return time.Now().UnixMilli()
}
