package tools

import (
	"context"
	"fmt"
	"os"
	"strings"
)

type LsTool struct{ cwd string }

func NewLsTool(cwd string) *LsTool { return &LsTool{cwd: cwd} }

func (t *LsTool) Name() string        { return "ls" }
func (t *LsTool) Description() string { return "List the contents of a directory." }
func (t *LsTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{"type": "string", "description": "Directory path"},
		},
		"required": []string{"path"},
	}
}

func (t *LsTool) Execute(_ context.Context, _ string, args map[string]any, _ UpdateFunc) (ToolResult, error) {
	path, _ := args["path"].(string)
	if path == "" {
		path = "."
	}
	path = resolvePath(path, t.cwd)

	entries, err := os.ReadDir(path)
	if err != nil {
		return errResult(fmt.Sprintf("ls: %v", err)), nil
	}

	var sb strings.Builder
	for _, e := range entries {
		kind := "file"
		if e.IsDir() {
			kind = "dir"
		}
		info, _ := e.Info()
		size := int64(0)
		if info != nil && !e.IsDir() {
			size = info.Size()
		}
		fmt.Fprintf(&sb, "%s\t%s\t%d\n", kind, e.Name(), size)
	}
	if sb.Len() == 0 {
		return ToolResult{Content: "(empty directory)"}, nil
	}
	return ToolResult{Content: sb.String()}, nil
}
