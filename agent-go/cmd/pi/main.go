package main

import (
	"fmt"
	"os"
	"strconv"

	"github.com/pi-agent/agent-go/internal/agent"
	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/ai/anthropic"
	openaiProvider "github.com/pi-agent/agent-go/internal/ai/openai"
	"github.com/pi-agent/agent-go/internal/session"
	"github.com/pi-agent/agent-go/internal/tools"
	"github.com/pi-agent/agent-go/internal/tui"
)

func main() {
	cfg := loadConfig()

	// Validate API key.
	if cfg.APIKey == "" {
		fmt.Fprintln(os.Stderr, "Error: no API key found. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.")
		os.Exit(1)
	}

	// Initialise session manager.
	sessMgr, err := session.New(cfg.SessionDir)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: init session manager: %v\n", err)
		os.Exit(1)
	}

	// Create or resume session.
	cwd, _ := os.Getwd()
	sessionHdr, err := sessMgr.NewSession(cwd)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: create session: %v\n", err)
		os.Exit(1)
	}

	// Build system prompt.
	systemPrompt := buildSystemPrompt(cwd)

	// Build provider.
	prov := buildProvider(cfg.Provider, cfg.APIKey)

	// Agent context factory — called fresh on each user message so that
	// messages accumulated in the session are included.
	var agentCtx *agent.Context
	agentCtx = &agent.Context{
		SystemPrompt: systemPrompt,
		Messages:     nil,
		Tools:        buildTools(cwd),
		ModelID:      cfg.ModelID,
		Provider:     cfg.Provider,
		APIKey:       cfg.APIKey,
	}

	ctxFactory := func() *agent.Context { return agentCtx }

	// Patch tui buildProvider to return the real provider.
	_ = prov // used in TUI via closure below
	tui.SetProviderFactory(func(_, _ string) ai.Provider { return prov })

	// Start TUI.
	m := tui.New(cfg.ModelID, cfg.Provider, cfg.APIKey, ctxFactory, sessMgr, sessionHdr.ID, nil)
	if err := tui.Run(m); err != nil {
		fmt.Fprintf(os.Stderr, "TUI error: %v\n", err)
		os.Exit(1)
	}
}

// ----- config ---------------------------------------------------------------

type config struct {
	Provider   string
	ModelID    string
	APIKey     string
	SessionDir string
	MaxTurns   int
}

func loadConfig() config {
	cfg := config{MaxTurns: 50}

	// Provider / model selection.
	if key := os.Getenv("ANTHROPIC_API_KEY"); key != "" {
		cfg.Provider = "anthropic"
		cfg.ModelID = "claude-sonnet-4-6"
		cfg.APIKey = key
	} else if key := os.Getenv("OPENAI_API_KEY"); key != "" {
		cfg.Provider = "openai"
		cfg.ModelID = "gpt-4o"
		cfg.APIKey = key
	}

	if v := os.Getenv("PI_SESSION_DIR"); v != "" {
		cfg.SessionDir = v
	}
	if v := os.Getenv("PI_MAX_TURNS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			cfg.MaxTurns = n
		}
	}
	if v := os.Getenv("PI_MODEL"); v != "" {
		cfg.ModelID = v
	}
	return cfg
}

// ----- helpers ---------------------------------------------------------------

func buildProvider(prov, _ string) ai.Provider {
	if prov == "openai" {
		return openaiProvider.New()
	}
	return anthropic.New()
}

func buildTools(cwd string) []tools.Tool {
	return []tools.Tool{
		tools.NewReadTool(cwd),
		tools.NewWriteTool(cwd),
		tools.NewEditTool(cwd),
		tools.NewBashTool(cwd),
		tools.NewFindTool(cwd),
		tools.NewGrepTool(cwd),
		tools.NewLsTool(cwd),
	}
}

func buildSystemPrompt(cwd string) string {
	return fmt.Sprintf(`You are a coding assistant. You have access to tools to read, write, and edit files, run bash commands, search for files and content, and list directories.

Current working directory: %s

Guidelines:
- Use read to examine files before editing them.
- Use edit (with the edits array) instead of write when making targeted changes to existing files.
- Use bash for running tests, builds, and other shell commands.
- Be concise and focused. Complete tasks step by step.
- When you finish a task, summarise what you did.
`, cwd)
}
