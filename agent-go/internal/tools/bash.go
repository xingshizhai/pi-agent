package tools

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"os/exec"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/pi-agent/agent-go/pkg/ansi"
)

const bashMaxOutputBytes = 200 * 1024 // 200 KB

type BashTool struct{ cwd string }

func NewBashTool(cwd string) *BashTool { return &BashTool{cwd: cwd} }

func (t *BashTool) Name() string        { return "bash" }
func (t *BashTool) Description() string { return "Execute a shell command. stdout and stderr are combined. Output is truncated to 200KB." }
func (t *BashTool) Schema() map[string]any {
	return map[string]any{
		"type": "object",
		"properties": map[string]any{
			"command": map[string]any{"type": "string", "description": "Shell command to execute"},
			"timeout": map[string]any{"type": "number", "description": "Timeout in seconds (optional, no default)"},
		},
		"required": []string{"command"},
	}
}

func (t *BashTool) Execute(ctx context.Context, _ string, args map[string]any, update UpdateFunc) (ToolResult, error) {
	command, _ := args["command"].(string)
	if command == "" {
		return errResult("bash: missing required parameter 'command'"), nil
	}

	// Apply timeout if specified.
	if v, ok := args["timeout"]; ok {
		if secs, ok := toFloat64(v); ok && secs > 0 {
			var cancel context.CancelFunc
			ctx, cancel = context.WithTimeout(ctx, time.Duration(secs*float64(time.Second)))
			defer cancel()
		}
	}

	var cmd *exec.Cmd
	if runtime.GOOS == "windows" {
		cmd = exec.CommandContext(ctx, "cmd", "/C", command)
	} else {
		cmd = exec.CommandContext(ctx, "bash", "-c", command)
	}
	cmd.Dir = t.cwd

	// Use a pipe to stream output.
	pr, pw := io.Pipe()
	cmd.Stdout = pw
	cmd.Stderr = pw

	if err := cmd.Start(); err != nil {
		return errResult(fmt.Sprintf("bash: start: %v", err)), nil
	}

	// Read output in a goroutine, collecting chunks and calling update.
	var mu sync.Mutex
	var outputBuf bytes.Buffer
	var truncated bool

	readerDone := make(chan struct{})
	go func() {
		defer close(readerDone)
		buf := make([]byte, 4096)
		for {
			n, err := pr.Read(buf)
			if n > 0 {
				chunk := ansi.Strip(string(buf[:n]))
				mu.Lock()
				if !truncated {
					remaining := bashMaxOutputBytes - outputBuf.Len()
					if remaining <= 0 {
						truncated = true
					} else if len(chunk) > remaining {
						outputBuf.WriteString(chunk[:remaining])
						truncated = true
					} else {
						outputBuf.WriteString(chunk)
					}
				}
				mu.Unlock()
				if update != nil {
					update(chunk)
				}
			}
			if err != nil {
				break
			}
		}
	}()

	err := cmd.Wait()
	pw.Close()
	<-readerDone

	mu.Lock()
	output := outputBuf.String()
	wasTruncated := truncated
	mu.Unlock()

	var sb strings.Builder
	sb.WriteString(output)

	if wasTruncated {
		sb.WriteString(fmt.Sprintf("\n\n[Output truncated at %s]", formatSize(bashMaxOutputBytes)))
	}

	exitCode := 0
	if err != nil {
		if ctx.Err() != nil {
			sb.WriteString("\n\n[Command timed out or was cancelled]")
		} else if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		}
	}

	content := sb.String()
	if content == "" && exitCode != 0 {
		content = fmt.Sprintf("[exit code %d]", exitCode)
	} else if exitCode != 0 {
		content += fmt.Sprintf("\n[exit code %d]", exitCode)
	}

	return ToolResult{Content: content, IsError: exitCode != 0}, nil
}

func toFloat64(v any) (float64, bool) {
	switch n := v.(type) {
	case float64:
		return n, true
	case int:
		return float64(n), true
	case int64:
		return float64(n), true
	case json_number:
		f, err := n.Float64()
		return f, err == nil
	}
	return 0, false
}
