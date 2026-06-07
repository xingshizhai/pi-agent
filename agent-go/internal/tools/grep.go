package tools

import (
	"bufio"
	"context"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

const grepMaxResults = 1000

type GrepTool struct{ cwd string }

func NewGrepTool(cwd string) *GrepTool { return &GrepTool{cwd: cwd} }

func (t *GrepTool) Name() string        { return "grep" }
func (t *GrepTool) Description() string { return "Search for a regex pattern in files. Returns file:line:content matches." }
func (t *GrepTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"path":        map[string]any{"type": "string", "description": "File or directory to search"},
			"pattern":     map[string]any{"type": "string", "description": "Regular expression pattern"},
			"recursive":   map[string]any{"type": "boolean", "description": "Recurse into subdirectories (default: true)"},
			"ignore_case": map[string]any{"type": "boolean", "description": "Case-insensitive search (default: false)"},
		},
		"required": []string{"path", "pattern"},
	}
}

func (t *GrepTool) Execute(_ context.Context, _ string, args map[string]any, _ UpdateFunc) (ToolResult, error) {
	root, _ := args["path"].(string)
	pattern, _ := args["pattern"].(string)
	if root == "" {
		return errResult("grep: missing required parameter 'path'"), nil
	}
	if pattern == "" {
		return errResult("grep: missing required parameter 'pattern'"), nil
	}
	root = resolvePath(root, t.cwd)

	ignoreCase := false
	if v, ok := args["ignore_case"].(bool); ok {
		ignoreCase = v
	}
	recursive := true
	if v, ok := args["recursive"].(bool); ok {
		recursive = v
	}

	reStr := pattern
	if ignoreCase {
		reStr = "(?i)" + pattern
	}
	re, err := regexp.Compile(reStr)
	if err != nil {
		return errResult(fmt.Sprintf("grep: invalid pattern: %v", err)), nil
	}

	var results []string
	walkFn := func(path string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			if d != nil && d.IsDir() && !recursive && path != root {
				return fs.SkipDir
			}
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return nil
		}
		defer f.Close()

		rel, _ := filepath.Rel(t.cwd, path)
		scanner := bufio.NewScanner(f)
		lineNo := 0
		for scanner.Scan() {
			lineNo++
			line := scanner.Text()
			if re.MatchString(line) {
				results = append(results, fmt.Sprintf("%s:%d:%s", rel, lineNo, line))
				if len(results) >= grepMaxResults {
					return fmt.Errorf("limit reached")
				}
			}
		}
		return nil
	}

	fi, err := os.Stat(root)
	if err != nil {
		return errResult(fmt.Sprintf("grep: %v", err)), nil
	}
	if fi.IsDir() {
		_ = filepath.WalkDir(root, walkFn)
	} else {
		_ = walkFn(root, &fileEntry{fi}, nil)
	}

	if len(results) == 0 {
		return ToolResult{Content: "(no matches)"}, nil
	}
	out := strings.Join(results, "\n")
	if len(results) >= grepMaxResults {
		out += fmt.Sprintf("\n[Truncated at %d matches]", grepMaxResults)
	}
	return ToolResult{Content: out}, nil
}

// fileEntry wraps os.FileInfo to implement fs.DirEntry for single-file grep.
type fileEntry struct{ fi os.FileInfo }

func (e *fileEntry) Name() string               { return e.fi.Name() }
func (e *fileEntry) IsDir() bool                { return e.fi.IsDir() }
func (e *fileEntry) Type() fs.FileMode          { return e.fi.Mode().Type() }
func (e *fileEntry) Info() (fs.FileInfo, error) { return e.fi, nil }
