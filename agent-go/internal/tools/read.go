package tools

import (
	"context"
	"fmt"
	"os"
	"strings"
)

const (
	defaultMaxLines = 2000
	defaultMaxBytes = 200 * 1024 // 200 KB
)

type ReadTool struct{ cwd string }

func NewReadTool(cwd string) *ReadTool { return &ReadTool{cwd: cwd} }

func (t *ReadTool) Name() string        { return "read" }
func (t *ReadTool) Description() string {
	return fmt.Sprintf(
		"Read the contents of a file. Output is truncated to %d lines or %dKB (whichever comes first). "+
			"Use offset (1-indexed line number) and limit to page through large files.",
		defaultMaxLines, defaultMaxBytes/1024,
	)
}
func (t *ReadTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":   map[string]any{"type": "string", "description": "Path to the file (relative or absolute)"},
			"offset": map[string]any{"type": "number", "description": "Line number to start reading from (1-indexed)"},
			"limit":  map[string]any{"type": "number", "description": "Maximum number of lines to read"},
		},
		"required": []string{"path"},
	}
}

func (t *ReadTool) Execute(ctx context.Context, _ string, args map[string]any, _ UpdateFunc) (ToolResult, error) {
	path, ok := args["path"].(string)
	if !ok || path == "" {
		return errResult("read: missing required parameter 'path'"), nil
	}
	path = resolvePath(path, t.cwd)

	data, err := os.ReadFile(path)
	if err != nil {
		return errResult(fmt.Sprintf("read: %v", err)), nil
	}

	allLines := strings.Split(string(data), "\n")
	totalLines := len(allLines)

	// offset is 1-indexed
	startLine := 0
	if v, ok := args["offset"]; ok {
		if n, ok := toInt(v); ok && n > 0 {
			startLine = n - 1
		}
	}
	if startLine >= totalLines {
		return errResult(fmt.Sprintf("read: offset %d is beyond end of file (%d lines)", startLine+1, totalLines)), nil
	}

	maxLines := defaultMaxLines
	if v, ok := args["limit"]; ok {
		if n, ok := toInt(v); ok && n > 0 {
			maxLines = n
		}
	}

	endLine := startLine + maxLines
	if endLine > totalLines {
		endLine = totalLines
	}

	// Byte-limit check.
	var sb strings.Builder
	byteCount := 0
	lastLine := startLine
	for i := startLine; i < endLine; i++ {
		lineBytes := len(allLines[i]) + 1 // +1 for newline
		if byteCount+lineBytes > defaultMaxBytes && i > startLine {
			endLine = i
			break
		}
		byteCount += lineBytes
		lastLine = i
		_ = lastLine
	}

	// Build output with line numbers (1-indexed).
	for i := startLine; i < endLine; i++ {
		fmt.Fprintf(&sb, "%d\t%s\n", i+1, allLines[i])
	}

	// Continuation hint.
	if endLine < totalLines {
		nextOffset := endLine + 1
		sb.WriteString(fmt.Sprintf("\n[Showing lines %d-%d of %d. Use offset=%d to continue.]",
			startLine+1, endLine, totalLines, nextOffset))
	}

	return ToolResult{Content: sb.String()}, nil
}
