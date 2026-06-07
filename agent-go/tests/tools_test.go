package tests

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/pi-agent/agent-go/internal/tools"
)

// ---- helpers ----------------------------------------------------------------

func tmpDir(t *testing.T) string {
	t.Helper()
	d := t.TempDir()
	return d
}

func writeFile(t *testing.T, dir, name, content string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("writeFile: %v", err)
	}
	return path
}

// ---- read -------------------------------------------------------------------

func TestReadTool_Basic(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "hello.txt", "line1\nline2\nline3\n")

	tool := tools.NewReadTool(dir)
	res, err := tool.Execute(context.Background(), "id1", map[string]any{"path": "hello.txt"}, nil)
	if err != nil {
		t.Fatal(err)
	}
	if res.IsError {
		t.Fatalf("unexpected error: %s", res.Content)
	}
	if !strings.Contains(res.Content, "1\tline1") {
		t.Errorf("expected line numbers, got: %q", res.Content)
	}
	if !strings.Contains(res.Content, "3\tline3") {
		t.Errorf("expected line3, got: %q", res.Content)
	}
}

func TestReadTool_OffsetLimit(t *testing.T) {
	dir := tmpDir(t)
	lines := "a\nb\nc\nd\ne\n"
	writeFile(t, dir, "f.txt", lines)

	tool := tools.NewReadTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": "f.txt", "offset": float64(2), "limit": float64(2),
	}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	if !strings.Contains(res.Content, "2\tb") {
		t.Errorf("expected line 2, got %q", res.Content)
	}
	if !strings.Contains(res.Content, "3\tc") {
		t.Errorf("expected line 3, got %q", res.Content)
	}
	if strings.Contains(res.Content, "4\td") {
		t.Errorf("should not contain line 4, got %q", res.Content)
	}
}

func TestReadTool_NotFound(t *testing.T) {
	tool := tools.NewReadTool(t.TempDir())
	res, _ := tool.Execute(context.Background(), "id", map[string]any{"path": "nosuchfile.txt"}, nil)
	if !res.IsError {
		t.Fatal("expected error for missing file")
	}
}

// ---- write ------------------------------------------------------------------

func TestWriteTool_Basic(t *testing.T) {
	dir := tmpDir(t)
	tool := tools.NewWriteTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": "subdir/out.txt", "content": "hello world",
	}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	data, err := os.ReadFile(filepath.Join(dir, "subdir", "out.txt"))
	if err != nil {
		t.Fatal(err)
	}
	if string(data) != "hello world" {
		t.Errorf("unexpected content: %q", data)
	}
}

// ---- edit -------------------------------------------------------------------

func TestEditTool_SingleEdit(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "f.go", "package main\n\nfunc hello() {}\n")
	tool := tools.NewEditTool(dir)

	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": "f.go",
		"edits": []any{
			map[string]any{"oldText": "func hello() {}", "newText": "func hello() { fmt.Println(\"hi\") }"},
		},
	}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	data, _ := os.ReadFile(filepath.Join(dir, "f.go"))
	if !strings.Contains(string(data), "fmt.Println") {
		t.Errorf("edit not applied: %s", data)
	}
}

func TestEditTool_NotFound(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "f.txt", "hello world\n")
	tool := tools.NewEditTool(dir)

	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": "f.txt",
		"edits": []any{
			map[string]any{"oldText": "not present", "newText": "replacement"},
		},
	}, nil)
	if !res.IsError {
		t.Fatal("expected error for missing oldText")
	}
}

func TestEditTool_NotUnique(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "f.txt", "foo\nfoo\n")
	tool := tools.NewEditTool(dir)

	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": "f.txt",
		"edits": []any{
			map[string]any{"oldText": "foo", "newText": "bar"},
		},
	}, nil)
	if !res.IsError {
		t.Fatal("expected error for non-unique oldText")
	}
	if !strings.Contains(res.Content, "2 times") {
		t.Errorf("expected count in error message, got: %s", res.Content)
	}
}

func TestEditTool_MultipleEdits(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "f.txt", "alpha\nbeta\ngamma\n")
	tool := tools.NewEditTool(dir)

	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": "f.txt",
		"edits": []any{
			map[string]any{"oldText": "alpha", "newText": "ALPHA"},
			map[string]any{"oldText": "gamma", "newText": "GAMMA"},
		},
	}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	data, _ := os.ReadFile(filepath.Join(dir, "f.txt"))
	if !strings.Contains(string(data), "ALPHA") || !strings.Contains(string(data), "GAMMA") {
		t.Errorf("edits not applied: %s", data)
	}
	if strings.Contains(string(data), "alpha") || strings.Contains(string(data), "gamma") {
		t.Errorf("old text still present: %s", data)
	}
}

// ---- bash -------------------------------------------------------------------

func TestBashTool_Echo(t *testing.T) {
	if os.Getenv("CI") == "" {
		// Only run bash tests if we can (skip on restricted envs).
	}
	dir := tmpDir(t)
	tool := tools.NewBashTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"command": "echo hello",
	}, nil)
	if res.IsError {
		t.Skip("bash not available:", res.Content)
	}
	if !strings.Contains(res.Content, "hello") {
		t.Errorf("expected 'hello', got %q", res.Content)
	}
}

func TestBashTool_ExitCode(t *testing.T) {
	dir := tmpDir(t)
	tool := tools.NewBashTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"command": "exit 1",
	}, nil)
	if !res.IsError {
		t.Error("expected IsError for non-zero exit code")
	}
}

// ---- find -------------------------------------------------------------------

func TestFindTool_Basic(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "a.go", "")
	writeFile(t, dir, "b.go", "")
	writeFile(t, dir, "c.txt", "")

	tool := tools.NewFindTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": dir, "pattern": "*.go",
	}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	if !strings.Contains(res.Content, "a.go") || !strings.Contains(res.Content, "b.go") {
		t.Errorf("expected .go files, got %q", res.Content)
	}
	if strings.Contains(res.Content, "c.txt") {
		t.Errorf("should not include .txt file, got %q", res.Content)
	}
}

// ---- grep -------------------------------------------------------------------

func TestGrepTool_Basic(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "a.txt", "hello world\nfoo bar\n")
	writeFile(t, dir, "b.txt", "hello go\n")

	tool := tools.NewGrepTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{
		"path": dir, "pattern": "hello",
	}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	if !strings.Contains(res.Content, "hello") {
		t.Errorf("expected match, got %q", res.Content)
	}
}

// ---- ls ---------------------------------------------------------------------

func TestLsTool_Basic(t *testing.T) {
	dir := tmpDir(t)
	writeFile(t, dir, "x.txt", "content")
	if err := os.Mkdir(filepath.Join(dir, "subdir"), 0o755); err != nil {
		t.Fatal(err)
	}

	tool := tools.NewLsTool(dir)
	res, _ := tool.Execute(context.Background(), "id", map[string]any{"path": dir}, nil)
	if res.IsError {
		t.Fatal(res.Content)
	}
	if !strings.Contains(res.Content, "x.txt") {
		t.Errorf("expected x.txt in output, got %q", res.Content)
	}
	if !strings.Contains(res.Content, "subdir") {
		t.Errorf("expected subdir in output, got %q", res.Content)
	}
}
