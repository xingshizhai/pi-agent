package tools

import (
	"context"
	"fmt"
	"os"
	"strings"
)

type EditTool struct{ cwd string }

func NewEditTool(cwd string) *EditTool { return &EditTool{cwd: cwd} }

func (t *EditTool) Name() string        { return "edit" }
func (t *EditTool) Description() string {
	return "Edit a file by replacing one or more exact text strings. " +
		"Each oldText must appear exactly once in the file. " +
		"All edits are validated against the original file before any changes are written."
}
func (t *EditTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path": map[string]any{"type": "string", "description": "Path to the file"},
			"edits": map[string]any{
				"type":        "array",
				"description": "One or more targeted replacements. Each oldText must be unique in the file.",
				"items": map[string]any{
					"type": "object",
					"properties": map[string]any{
						"oldText": map[string]any{"type": "string", "description": "Exact text to replace (must appear exactly once)"},
						"newText": map[string]any{"type": "string", "description": "Replacement text"},
					},
					"required": []string{"oldText", "newText"},
				},
			},
		},
		"required": []string{"path", "edits"},
	}
}

func (t *EditTool) Execute(_ context.Context, _ string, args map[string]any, _ UpdateFunc) (ToolResult, error) {
	path, _ := args["path"].(string)
	if path == "" {
		return errResult("edit: missing required parameter 'path'"), nil
	}
	path = resolvePath(path, t.cwd)

	// Parse edits array.
	editsRaw, ok := args["edits"].([]any)
	if !ok || len(editsRaw) == 0 {
		return errResult("edit: 'edits' must be a non-empty array"), nil
	}

	type editItem struct{ oldText, newText string }
	edits := make([]editItem, 0, len(editsRaw))
	for i, e := range editsRaw {
		m, ok := e.(map[string]any)
		if !ok {
			return errResult(fmt.Sprintf("edit: edits[%d] must be an object", i)), nil
		}
		oldText, _ := m["oldText"].(string)
		newText, _ := m["newText"].(string)
		if oldText == "" {
			return errResult(fmt.Sprintf("edit: edits[%d].oldText is empty", i)), nil
		}
		edits = append(edits, editItem{oldText, newText})
	}

	data, err := os.ReadFile(path)
	if err != nil {
		return errResult(fmt.Sprintf("edit: read file: %v", err)), nil
	}
	content := string(data)

	// Validate all edits against the original file.
	for i, e := range edits {
		count := strings.Count(content, e.oldText)
		if count == 0 {
			return errResult(fmt.Sprintf("edit: edits[%d].oldText not found in file:\n%q", i, truncateStr(e.oldText, 200))), nil
		}
		if count > 1 {
			return errResult(fmt.Sprintf("edit: edits[%d].oldText appears %d times (must be unique):\n%q", i, count, truncateStr(e.oldText, 200))), nil
		}
	}

	// Apply all edits (each oldText appears exactly once, so order doesn't matter for correctness,
	// but we apply them in sequence to produce intuitive results).
	result := content
	for _, e := range edits {
		result = strings.Replace(result, e.oldText, e.newText, 1)
	}

	if err := os.WriteFile(path, []byte(result), 0o644); err != nil {
		return errResult(fmt.Sprintf("edit: write file: %v", err)), nil
	}

	return ToolResult{Content: fmt.Sprintf("Edited %s (%d replacement(s) applied)", path, len(edits))}, nil
}

func truncateStr(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}
