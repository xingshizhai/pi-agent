package tools

import "context"

// ToolResult is returned by every tool execution.
type ToolResult struct {
	Content   string
	IsError   bool
	Terminate bool
}

// UpdateFunc is called with partial output during long-running tools.
type UpdateFunc func(partial string)

// Tool is the interface every built-in tool must implement.
type Tool interface {
	Name() string
	Description() string
	// Schema returns a JSON Schema object describing the input parameters.
	Schema() map[string]any
	Execute(ctx context.Context, id string, args map[string]any, update UpdateFunc) (ToolResult, error)
}

func errResult(msg string) ToolResult { return ToolResult{Content: msg, IsError: true} }

