package openai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/pi-agent/agent-go/internal/ai"
)

const (
	defaultEndpoint  = "https://api.openai.com/v1/chat/completions"
	defaultMaxTokens = 8192
)

// Provider implements ai.Provider for OpenAI.
type Provider struct {
	endpoint string
	client   *http.Client
}

func New() *Provider {
	return &Provider{
		endpoint: defaultEndpoint,
		client:   &http.Client{Timeout: 10 * time.Minute},
	}
}

// ---- request structs --------------------------------------------------------

type reqMessage struct {
	Role       string      `json:"role"`
	Content    interface{} `json:"content,omitempty"`
	ToolCallID string      `json:"tool_call_id,omitempty"`
	ToolCalls  []toolCall  `json:"tool_calls,omitempty"`
	Name       string      `json:"name,omitempty"`
}

type toolCall struct {
	ID       string `json:"id"`
	Type     string `json:"type"` // "function"
	Function struct {
		Name      string `json:"name"`
		Arguments string `json:"arguments"`
	} `json:"function"`
}

type toolDef struct {
	Type     string `json:"type"` // "function"
	Function struct {
		Name        string         `json:"name"`
		Description string         `json:"description"`
		Parameters  map[string]any `json:"parameters"`
	} `json:"function"`
}

type request struct {
	Model          string       `json:"model"`
	Messages       []reqMessage `json:"messages"`
	Tools          []toolDef    `json:"tools,omitempty"`
	Stream         bool         `json:"stream"`
	StreamOptions  *streamOpts  `json:"stream_options,omitempty"`
	MaxTokens      int          `json:"max_tokens,omitempty"`
}

type streamOpts struct {
	IncludeUsage bool `json:"include_usage"`
}

// ---- SSE delta structs -------------------------------------------------------

type delta struct {
	Role      string     `json:"role"`
	Content   string     `json:"content"`
	ToolCalls []struct {
		Index    int    `json:"index"`
		ID       string `json:"id"`
		Type     string `json:"type"`
		Function struct {
			Name      string `json:"name"`
			Arguments string `json:"arguments"`
		} `json:"function"`
	} `json:"tool_calls"`
}

type choice struct {
	Index        int    `json:"index"`
	Delta        delta  `json:"delta"`
	FinishReason string `json:"finish_reason"`
}

type chunkUsage struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
}

type chunk struct {
	Choices []choice    `json:"choices"`
	Usage   *chunkUsage `json:"usage"`
}

// ---- message conversion -----------------------------------------------------

func convertMessages(msgs []ai.Message) []reqMessage {
	var result []reqMessage
	for _, m := range msgs {
		switch m.Role {
		case ai.RoleUser:
			var sb strings.Builder
			for _, c := range m.Content {
				if t, ok := c.AsText(); ok {
					sb.WriteString(t.Text)
				}
			}
			result = append(result, reqMessage{Role: "user", Content: sb.String()})

		case ai.RoleAssistant:
			var sb strings.Builder
			var calls []toolCall
			for _, c := range m.Content {
				switch c.Type() {
				case "text":
					t, _ := c.AsText()
					sb.WriteString(t.Text)
				case "tool_call":
					tc, _ := c.AsToolCall()
					argBytes, _ := json.Marshal(tc.Arguments)
					calls = append(calls, toolCall{
						ID:   tc.ID,
						Type: "function",
						Function: struct {
							Name      string `json:"name"`
							Arguments string `json:"arguments"`
						}{Name: tc.Name, Arguments: string(argBytes)},
					})
				}
			}
			rm := reqMessage{Role: "assistant"}
			if sb.Len() > 0 {
				rm.Content = sb.String()
			}
			if len(calls) > 0 {
				rm.ToolCalls = calls
			}
			result = append(result, rm)

		case ai.RoleToolResult:
			tr, ok := m.Content[0].AsToolResult()
			if !ok {
				continue
			}
			result = append(result, reqMessage{
				Role:       "tool",
				Content:    tr.Content,
				ToolCallID: tr.ToolCallID,
			})
		}
	}
	return result
}

// ---- Stream -----------------------------------------------------------------

func (p *Provider) Stream(ctx context.Context, llmCtx ai.Context, opts ai.StreamOptions) (<-chan ai.StreamEvent, error) {
	maxTokens := opts.MaxTokens
	if maxTokens == 0 {
		maxTokens = defaultMaxTokens
	}

	tools := make([]toolDef, len(llmCtx.Tools))
	for i, t := range llmCtx.Tools {
		tools[i] = toolDef{Type: "function"}
		tools[i].Function.Name = t.Name
		tools[i].Function.Description = t.Description
		tools[i].Function.Parameters = t.InputSchema
	}

	// Prepend system message.
	msgs := convertMessages(llmCtx.Messages)
	if llmCtx.SystemPrompt != "" {
		msgs = append([]reqMessage{{Role: "system", Content: llmCtx.SystemPrompt}}, msgs...)
	}

	reqBody := request{
		Model:         "gpt-4o",
		Messages:      msgs,
		Tools:         tools,
		Stream:        true,
		StreamOptions: &streamOpts{IncludeUsage: true},
		MaxTokens:     maxTokens,
	}

	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("openai: marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, p.endpoint, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, fmt.Errorf("openai: create request: %w", err)
	}
	httpReq.Header.Set("Authorization", "Bearer "+opts.APIKey)
	httpReq.Header.Set("Content-Type", "application/json")

	resp, err := p.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("openai: http request: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("openai: http status %d", resp.StatusCode)
	}

	ch := make(chan ai.StreamEvent, 64)
	go func() {
		defer resp.Body.Close()
		defer close(ch)
		p.consumeSSE(ctx, resp, ch)
	}()
	return ch, nil
}

func (p *Provider) consumeSSE(ctx context.Context, resp *http.Response, ch chan<- ai.StreamEvent) {
	sseCh := ai.ParseSSE(resp.Body)

	// Accumulate tool call arguments indexed by tool_calls[i].index.
	type tcState struct {
		id        string
		name      string
		argsBuf   strings.Builder
	}
	tcStates := map[int]*tcState{}
	var usage ai.Usage

	send := func(e ai.StreamEvent) {
		select {
		case ch <- e:
		case <-ctx.Done():
		}
	}

	for {
		select {
		case <-ctx.Done():
			send(ai.StreamEvent{
				Type: "error", StopReason: ai.StopReasonAborted,
				ErrorMessage: ctx.Err().Error(),
			})
			return
		case ev, ok := <-sseCh:
			if !ok {
				return
			}
			if ev.Data == "[DONE]" {
				send(ai.StreamEvent{Type: "done", StopReason: ai.StopReasonStop, Usage: usage})
				return
			}

			var c chunk
			if err := json.Unmarshal([]byte(ev.Data), &c); err != nil {
				continue
			}

			if c.Usage != nil {
				usage.InputTokens = c.Usage.PromptTokens
				usage.OutputTokens = c.Usage.CompletionTokens
			}

			for _, choice := range c.Choices {
				if choice.Delta.Content != "" {
					send(ai.StreamEvent{Type: "text_delta", TextDelta: choice.Delta.Content})
				}
				for _, tc := range choice.Delta.ToolCalls {
					st, exists := tcStates[tc.Index]
					if !exists {
						st = &tcState{}
						tcStates[tc.Index] = st
					}
					if tc.ID != "" {
						st.id = tc.ID
					}
					if tc.Function.Name != "" {
						st.name = tc.Function.Name
					}
					st.argsBuf.WriteString(tc.Function.Arguments)
				}

				if choice.FinishReason == "tool_calls" {
					for _, st := range tcStates {
						var args map[string]any
						_ = json.Unmarshal([]byte(st.argsBuf.String()), &args)
						if args == nil {
							args = map[string]any{}
						}
						send(ai.StreamEvent{
							Type: "tool_call",
							ToolCall: &ai.ToolCallContent{
								Type: "tool_call", ID: st.id, Name: st.name, Arguments: args,
							},
						})
					}
					tcStates = map[int]*tcState{}
					send(ai.StreamEvent{Type: "done", StopReason: ai.StopReasonToolUse, Usage: usage})
					return
				} else if choice.FinishReason == "stop" {
					send(ai.StreamEvent{Type: "done", StopReason: ai.StopReasonStop, Usage: usage})
					return
				} else if choice.FinishReason == "length" {
					send(ai.StreamEvent{Type: "done", StopReason: ai.StopReasonLength, Usage: usage})
					return
				}
			}
		}
	}
}
