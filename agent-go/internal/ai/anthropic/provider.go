package anthropic

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
	defaultEndpoint  = "https://api.anthropic.com/v1/messages"
	anthropicVersion = "2023-06-01"
	defaultMaxTokens = 8192
)

// Provider implements ai.Provider for Anthropic Claude.
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

// ---- request structs -------------------------------------------------------

type reqMessage struct {
	Role    string      `json:"role"`
	Content interface{} `json:"content"` // string or []contentBlock
}

type contentBlock struct {
	Type       string          `json:"type"`
	Text       string          `json:"text,omitempty"`
	ID         string          `json:"id,omitempty"`
	Name       string          `json:"name,omitempty"`
	Input      json.RawMessage `json:"input,omitempty"`
	ToolUseID  string          `json:"tool_use_id,omitempty"`
	Content    interface{}     `json:"content,omitempty"`
	IsError    bool            `json:"is_error,omitempty"`
}

type toolParam struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"input_schema"`
}

type request struct {
	Model     string       `json:"model"`
	MaxTokens int          `json:"max_tokens"`
	System    string       `json:"system,omitempty"`
	Messages  []reqMessage `json:"messages"`
	Tools     []toolParam  `json:"tools,omitempty"`
	Stream    bool         `json:"stream"`
}

// ---- SSE event structs ------------------------------------------------------

type sseContentBlockStart struct {
	Type         string `json:"type"`
	Index        int    `json:"index"`
	ContentBlock struct {
		Type string `json:"type"`
		ID   string `json:"id"`
		Name string `json:"name"`
	} `json:"content_block"`
}

type sseContentBlockDelta struct {
	Type  string `json:"type"`
	Index int    `json:"index"`
	Delta struct {
		Type        string `json:"type"`
		Text        string `json:"text"`
		PartialJSON string `json:"partial_json"`
	} `json:"delta"`
}

type sseMessageDelta struct {
	Type  string `json:"type"`
	Delta struct {
		StopReason string `json:"stop_reason"`
	} `json:"delta"`
	Usage struct {
		OutputTokens int `json:"output_tokens"`
	} `json:"usage"`
}

type sseMessageStart struct {
	Type    string `json:"type"`
	Message struct {
		Usage struct {
			InputTokens              int `json:"input_tokens"`
			CacheCreationInputTokens int `json:"cache_creation_input_tokens"`
			CacheReadInputTokens     int `json:"cache_read_input_tokens"`
		} `json:"usage"`
		Model string `json:"model"`
	} `json:"message"`
}

// ---- conversion helpers -----------------------------------------------------

func convertMessages(msgs []ai.Message) []reqMessage {
	var result []reqMessage
	var pendingToolResults []contentBlock

	flush := func() {
		if len(pendingToolResults) == 0 {
			return
		}
		result = append(result, reqMessage{Role: "user", Content: pendingToolResults})
		pendingToolResults = nil
	}

	for _, m := range msgs {
		switch m.Role {
		case ai.RoleUser:
			flush()
			// Build content array or simple string.
			var blocks []contentBlock
			for _, c := range m.Content {
				if t, ok := c.AsText(); ok {
					blocks = append(blocks, contentBlock{Type: "text", Text: t.Text})
				}
			}
			if len(blocks) == 1 {
				result = append(result, reqMessage{Role: "user", Content: blocks[0].Text})
			} else if len(blocks) > 1 {
				result = append(result, reqMessage{Role: "user", Content: blocks})
			}

		case ai.RoleAssistant:
			flush()
			var blocks []contentBlock
			for _, c := range m.Content {
				switch c.Type() {
				case "text":
					t, _ := c.AsText()
					if t.Text != "" {
						blocks = append(blocks, contentBlock{Type: "text", Text: t.Text})
					}
				case "tool_call":
					tc, _ := c.AsToolCall()
					argBytes, _ := json.Marshal(tc.Arguments)
					blocks = append(blocks, contentBlock{
						Type:  "tool_use",
						ID:    tc.ID,
						Name:  tc.Name,
						Input: argBytes,
					})
				}
			}
			result = append(result, reqMessage{Role: "assistant", Content: blocks})

		case ai.RoleToolResult:
			tr, ok := m.Content[0].AsToolResult()
			if !ok {
				continue
			}
			blk := contentBlock{
				Type:      "tool_result",
				ToolUseID: tr.ToolCallID,
				Content:   tr.Content,
				IsError:   tr.IsError,
			}
			pendingToolResults = append(pendingToolResults, blk)
		}
	}
	flush()
	return result
}

// ---- Stream -----------------------------------------------------------------

func (p *Provider) Stream(ctx context.Context, llmCtx ai.Context, opts ai.StreamOptions) (<-chan ai.StreamEvent, error) {
	maxTokens := opts.MaxTokens
	if maxTokens == 0 {
		maxTokens = defaultMaxTokens
	}

	// Build tools list.
	tools := make([]toolParam, len(llmCtx.Tools))
	for i, t := range llmCtx.Tools {
		tools[i] = toolParam{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
		}
	}

	// Determine model from context (fallback).
	model := "claude-sonnet-4-6"

	reqBody := request{
		Model:     model,
		MaxTokens: maxTokens,
		System:    llmCtx.SystemPrompt,
		Messages:  convertMessages(llmCtx.Messages),
		Tools:     tools,
		Stream:    true,
	}

	bodyBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("anthropic: marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, p.endpoint, bytes.NewReader(bodyBytes))
	if err != nil {
		return nil, fmt.Errorf("anthropic: create request: %w", err)
	}
	httpReq.Header.Set("x-api-key", opts.APIKey)
	httpReq.Header.Set("anthropic-version", anthropicVersion)
	httpReq.Header.Set("content-type", "application/json")
	httpReq.Header.Set("accept", "text/event-stream")

	resp, err := p.client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("anthropic: http request: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		resp.Body.Close()
		return nil, fmt.Errorf("anthropic: http status %d", resp.StatusCode)
	}

	ch := make(chan ai.StreamEvent, 64)
	go func() {
		defer resp.Body.Close()
		defer close(ch)
		p.consumeSSE(ctx, resp.Body, ch)
	}()
	return ch, nil
}

func (p *Provider) consumeSSE(ctx context.Context, body interface{ Read([]byte) (int, error) }, ch chan<- ai.StreamEvent) {
	sseCh := ai.ParseSSE(body.(interface {
		Read([]byte) (int, error)
	}))

	// per-stream state
	type toolState struct {
		id      string
		name    string
		argsBuf strings.Builder
	}
	toolStates := map[int]*toolState{}
	var usage ai.Usage
	var model string

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
				return
			}

			var typeOnly struct {
				Type string `json:"type"`
			}
			_ = json.Unmarshal([]byte(ev.Data), &typeOnly)

			switch typeOnly.Type {
			case "message_start":
				var ms sseMessageStart
				if err := json.Unmarshal([]byte(ev.Data), &ms); err == nil {
					model = ms.Message.Model
					usage.InputTokens = ms.Message.Usage.InputTokens
					usage.CacheRead = ms.Message.Usage.CacheReadInputTokens
					usage.CacheWrite = ms.Message.Usage.CacheCreationInputTokens
					_ = model
				}

			case "content_block_start":
				var cbs sseContentBlockStart
				if err := json.Unmarshal([]byte(ev.Data), &cbs); err == nil {
					if cbs.ContentBlock.Type == "tool_use" {
						toolStates[cbs.Index] = &toolState{
							id:   cbs.ContentBlock.ID,
							name: cbs.ContentBlock.Name,
						}
					}
				}

			case "content_block_delta":
				var cbd sseContentBlockDelta
				if err := json.Unmarshal([]byte(ev.Data), &cbd); err != nil {
					continue
				}
				switch cbd.Delta.Type {
				case "text_delta":
					send(ai.StreamEvent{Type: "text_delta", TextDelta: cbd.Delta.Text})
				case "input_json_delta":
					if ts, ok := toolStates[cbd.Index]; ok {
						ts.argsBuf.WriteString(cbd.Delta.PartialJSON)
					}
				}

			case "content_block_stop":
				var idx struct {
					Index int `json:"index"`
				}
				if err := json.Unmarshal([]byte(ev.Data), &idx); err == nil {
					if ts, ok := toolStates[idx.Index]; ok {
						var args map[string]any
						_ = json.Unmarshal([]byte(ts.argsBuf.String()), &args)
						if args == nil {
							args = map[string]any{}
						}
						tc := &ai.ToolCallContent{
							Type:      "tool_call",
							ID:        ts.id,
							Name:      ts.name,
							Arguments: args,
						}
						send(ai.StreamEvent{Type: "tool_call", ToolCall: tc})
						delete(toolStates, idx.Index)
					}
				}

			case "message_delta":
				var md sseMessageDelta
				if err := json.Unmarshal([]byte(ev.Data), &md); err == nil {
					usage.OutputTokens = md.Usage.OutputTokens
					stopReason := ai.StopReason(md.Delta.StopReason)
					if stopReason == "" {
						stopReason = ai.StopReasonStop
					}
					send(ai.StreamEvent{
						Type: "done", StopReason: stopReason, Usage: usage,
					})
				}

			case "error":
				var errEvent struct {
					Error struct {
						Message string `json:"message"`
					} `json:"error"`
				}
				_ = json.Unmarshal([]byte(ev.Data), &errEvent)
				send(ai.StreamEvent{
					Type: "error", StopReason: ai.StopReasonError,
					ErrorMessage: errEvent.Error.Message,
				})
				return
			}
		}
	}
}
