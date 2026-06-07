package ai

import "encoding/json"

type Role string

const (
	RoleUser       Role = "user"
	RoleAssistant  Role = "assistant"
	RoleToolResult Role = "tool_result"
)

// ContentBlock is the union of TextContent | ToolCallContent | ToolResultContent.
// We keep it as json.RawMessage and decode by "type" field.
type ContentBlock struct {
	raw json.RawMessage
}

func (c ContentBlock) MarshalJSON() ([]byte, error) { return c.raw, nil }
func (c *ContentBlock) UnmarshalJSON(b []byte) error {
	c.raw = append([]byte(nil), b...)
	return nil
}
func (c ContentBlock) Raw() json.RawMessage { return c.raw }

type contentType struct {
	Type string `json:"type"`
}

func (c ContentBlock) Type() string {
	var t contentType
	_ = json.Unmarshal(c.raw, &t)
	return t.Type
}

type TextContent struct {
	Type string `json:"type"` // "text"
	Text string `json:"text"`
}

type ToolCallContent struct {
	Type      string         `json:"type"` // "tool_call"
	ID        string         `json:"id"`
	Name      string         `json:"name"`
	Arguments map[string]any `json:"arguments"`
}

type ToolResultContent struct {
	Type       string `json:"type"` // "tool_result"
	ToolCallID string `json:"tool_call_id"`
	ToolName   string `json:"tool_name"`
	Content    string `json:"content"`
	IsError    bool   `json:"is_error"`
}

func NewTextBlock(text string) ContentBlock {
	b, _ := json.Marshal(TextContent{Type: "text", Text: text})
	return ContentBlock{raw: b}
}

func NewToolCallBlock(id, name string, args map[string]any) ContentBlock {
	b, _ := json.Marshal(ToolCallContent{Type: "tool_call", ID: id, Name: name, Arguments: args})
	return ContentBlock{raw: b}
}

func NewToolResultBlock(toolCallID, toolName, content string, isError bool) ContentBlock {
	b, _ := json.Marshal(ToolResultContent{
		Type: "tool_result", ToolCallID: toolCallID,
		ToolName: toolName, Content: content, IsError: isError,
	})
	return ContentBlock{raw: b}
}

func (c ContentBlock) AsText() (TextContent, bool) {
	if c.Type() != "text" {
		return TextContent{}, false
	}
	var t TextContent
	err := json.Unmarshal(c.raw, &t)
	return t, err == nil
}

func (c ContentBlock) AsToolCall() (ToolCallContent, bool) {
	if c.Type() != "tool_call" {
		return ToolCallContent{}, false
	}
	var t ToolCallContent
	err := json.Unmarshal(c.raw, &t)
	return t, err == nil
}

func (c ContentBlock) AsToolResult() (ToolResultContent, bool) {
	if c.Type() != "tool_result" {
		return ToolResultContent{}, false
	}
	var t ToolResultContent
	err := json.Unmarshal(c.raw, &t)
	return t, err == nil
}

type Message struct {
	Role      Role           `json:"role"`
	Content   []ContentBlock `json:"content"`
	Timestamp int64          `json:"timestamp"`
}

type Usage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
	CacheRead    int `json:"cache_read_input_tokens,omitempty"`
	CacheWrite   int `json:"cache_creation_input_tokens,omitempty"`
}

type StopReason string

const (
	StopReasonStop     StopReason = "stop"
	StopReasonLength   StopReason = "length"
	StopReasonToolUse  StopReason = "tool_use"
	StopReasonError    StopReason = "error"
	StopReasonAborted  StopReason = "aborted"
)

// AssistantResponse is the completed assistant message after a stream ends.
type AssistantResponse struct {
	Content      []ContentBlock
	StopReason   StopReason
	ErrorMessage string
	Usage        Usage
	Model        string
}

// StreamEvent variants returned on the events channel from Provider.Stream.
type StreamEvent struct {
	Type string // "text_delta" | "tool_call" | "done" | "error"

	// text_delta
	TextDelta string

	// tool_call (complete, after all deltas accumulated)
	ToolCall *ToolCallContent

	// done / error
	StopReason   StopReason
	ErrorMessage string
	Usage        Usage
}

// ToolDefinition is the schema sent to the LLM provider.
type ToolDefinition struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"input_schema"` // JSON Schema
}

// Context is the full conversation context sent to the provider.
type Context struct {
	SystemPrompt string
	Messages     []Message
	Tools        []ToolDefinition
}
