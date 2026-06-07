package tui

import (
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/viewport"
	"github.com/pi-agent/agent-go/internal/agent"
	"github.com/pi-agent/agent-go/internal/session"
)

// InputMode describes what the input box is doing.
type InputMode int

const (
	ModeNormal  InputMode = iota
	ModeSending           // waiting for LLM response
)

// RenderMessage is a chat message ready for display.
type RenderMessage struct {
	Role    string // "user" | "assistant" | "tool"
	Content string
	IsError bool
}

// Model is the bubbletea application state.
type Model struct {
	width, height int

	// Chat display.
	viewport viewport.Model
	messages []RenderMessage

	// Current streaming assistant text.
	streamBuf strings.Builder
	streaming bool

	// Active tool execution display.
	activeTools map[string]string // tool_call_id → "tool_name: partial output"

	// Input area.
	input     textarea.Model
	inputMode InputMode

	// History of sent messages for ↑/↓ navigation.
	inputHistory []string
	historyIdx   int
	savedDraft   string

	// Agent events channel (set when a run is in progress).
	agentEvents <-chan agent.AgentEvent
	cancelRun   func() // cancel the current run context

	// Session persistence.
	sessionMgr  *session.Manager
	sessionID   string
	lastEntryID *string

	// Status bar info.
	modelName    string
	provider     string
	inputTokens  int
	outputTokens int
	lastLatency  time.Duration
	runStart     time.Time

	// Error to display transiently.
	flashError string

	// Ready flag: false until first WindowSizeMsg.
	ready bool

	// Agent context factory and API key (set at construction).
	agentCtxFactory func() *agent.Context
	apiKey          string
}
