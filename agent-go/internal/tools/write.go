package tools

import (
	"context"
	"fmt"
	"os"
)

type WriteTool struct{ cwd string }

func NewWriteTool(cwd string) *WriteTool { return &WriteTool{cwd: cwd} }

func (t *WriteTool) Name() string        { return "write" }
func (t *WriteTool) Description() string { return "Write content to a file, creating parent directories as needed." }
func (t *WriteTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":    map[string]any{"type": "string", "description": "Path to the file"},
			"content": map[string]any{"type": "string", "description": "Content to write"},
		},
		"required": []string{"path", "content"},
	}
}

func (t *WriteTool) Execute(_ context.Context, _ string, args map[string]any, _ UpdateFunc) (ToolResult, error) {
	path, _ := args["path"].(string)
	content, _ := args["content"].(string)
	if path == "" {
		return errResult("write: missing required parameter 'path'"), nil
	}
	path = resolvePath(path, t.cwd)
	if err := mkdirForFile(path); err != nil {
		return errResult(fmt.Sprintf("write: create directories: %v", err)), nil
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		return errResult(fmt.Sprintf("write: %v", err)), nil
	}
	return ToolResult{Content: fmt.Sprintf("Written to %s", path)}, nil
}
