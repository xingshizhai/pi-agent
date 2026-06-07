package tools

import (
	"context"
	"io/fs"
	"path/filepath"
	"strings"
)

type FindTool struct{ cwd string }

func NewFindTool(cwd string) *FindTool { return &FindTool{cwd: cwd} }

func (t *FindTool) Name() string        { return "find" }
func (t *FindTool) Description() string { return "Recursively find files or directories matching a glob pattern." }
func (t *FindTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":    map[string]any{"type": "string", "description": "Directory to search in"},
			"pattern": map[string]any{"type": "string", "description": "Filename glob pattern (e.g. *.go)"},
			"type": map[string]any{
				"type":        "string",
				"enum":        []string{"file", "dir", "any"},
				"description": "Entry type filter (default: any)",
			},
		},
		"required": []string{"path", "pattern"},
	}
}

func (t *FindTool) Execute(_ context.Context, _ string, args map[string]any, _ UpdateFunc) (ToolResult, error) {
	root, _ := args["path"].(string)
	pattern, _ := args["pattern"].(string)
	typeFilter, _ := args["type"].(string)
	if root == "" {
		return errResult("find: missing required parameter 'path'"), nil
	}
	if pattern == "" {
		return errResult("find: missing required parameter 'pattern'"), nil
	}
	root = resolvePath(root, t.cwd)

	var results []string
	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return nil // skip unreadable
		}
		if path == root {
			return nil
		}
		matched, _ := filepath.Match(pattern, d.Name())
		if !matched {
			return nil
		}
		switch typeFilter {
		case "file":
			if d.IsDir() {
				return nil
			}
		case "dir":
			if !d.IsDir() {
				return nil
			}
		}
		rel, _ := filepath.Rel(root, path)
		results = append(results, rel)
		return nil
	})
	if err != nil {
		return errResult("find: " + err.Error()), nil
	}
	if len(results) == 0 {
		return ToolResult{Content: "(no matches)"}, nil
	}
	return ToolResult{Content: strings.Join(results, "\n")}, nil
}
