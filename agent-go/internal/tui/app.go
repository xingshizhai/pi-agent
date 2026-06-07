package tui

import (
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/pi-agent/agent-go/internal/agent"
	"github.com/pi-agent/agent-go/internal/session"
)

// agentEventMsg wraps an agent.AgentEvent for the bubbletea message loop.
type agentEventMsg struct{ event agent.AgentEvent }

// New builds the initial Model.
func New(
	modelName, provider, apiKey string,
	agentCtxFactory func() *agent.Context,
	sessionMgr *session.Manager,
	sessionID string,
	initialMessages []RenderMessage,
) Model {
	ta := textarea.New()
	ta.Placeholder = "Type a message... (Ctrl+Enter to send, Ctrl+C to cancel)"
	ta.Focus()
	ta.SetHeight(3)
	ta.CharLimit = 0
	ta.ShowLineNumbers = false
	ta.KeyMap.InsertNewline.SetKeys("enter")

	vp := viewport.New(80, 20)
	vp.SetContent("")

	m := Model{
		viewport:    vp,
		input:       ta,
		modelName:   modelName,
		provider:    provider,
		inputHistory: []string{},
		historyIdx:  -1,
		activeTools: map[string]string{},
		sessionMgr:  sessionMgr,
		sessionID:   sessionID,
	}
	m.messages = initialMessages

	// Store factory for use in update.
	m.agentCtxFactory = agentCtxFactory
	m.apiKey = apiKey
	return m
}

// Run starts the bubbletea program.
func Run(m Model) error {
	p := tea.NewProgram(m, tea.WithAltScreen(), tea.WithMouseCellMotion())
	_, err := p.Run()
	return err
}

// --- bubbletea interface ---------------------------------------------------

func (m Model) Init() tea.Cmd {
	return textarea.Blink
}

// listenAgent reads the next event from the agent channel and returns it as a tea.Msg.
func listenAgent(ch <-chan agent.AgentEvent) tea.Cmd {
	return func() tea.Msg {
		ev, ok := <-ch
		if !ok {
			return agentEventMsg{event: agent.AgentEvent{Type: agent.EventAgentEnd}}
		}
		return agentEventMsg{event: ev}
	}
}

// --- View -----------------------------------------------------------------

var (
	userStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("12")).Bold(true)
	assistantStyle = lipgloss.NewStyle().Foreground(lipgloss.Color("10"))
	toolStyle      = lipgloss.NewStyle().Foreground(lipgloss.Color("11"))
	errorStyle     = lipgloss.NewStyle().Foreground(lipgloss.Color("9"))
	dimStyle       = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
	statusStyle    = lipgloss.NewStyle().Foreground(lipgloss.Color("8")).Reverse(true)
	borderStyle    = lipgloss.NewStyle().BorderStyle(lipgloss.NormalBorder()).BorderForeground(lipgloss.Color("8"))
)

func (m Model) View() string {
	if !m.ready {
		return "Loading..."
	}
	chat := m.renderChat()
	inputBox := m.renderInput()
	status := m.renderStatus()
	return lipgloss.JoinVertical(lipgloss.Left, chat, inputBox, status)
}

func (m Model) renderChat() string {
	return m.viewport.View()
}

func (m Model) renderInput() string {
	prefix := ""
	if m.inputMode == ModeSending {
		prefix = dimStyle.Render("● ") // streaming indicator
	}
	return borderStyle.Width(m.width - 2).Render(prefix + m.input.View())
}

func (m Model) renderStatus() string {
	var parts []string
	parts = append(parts, m.modelName)
	if m.inputTokens > 0 || m.outputTokens > 0 {
		parts = append(parts, fmt.Sprintf("↑%d ↓%d tokens", m.inputTokens, m.outputTokens))
	}
	if m.lastLatency > 0 {
		parts = append(parts, fmt.Sprintf("%.1fs", m.lastLatency.Seconds()))
	}
	if m.flashError != "" {
		parts = append(parts, errorStyle.Render("⚠ "+m.flashError))
	}
	line := " " + strings.Join(parts, "  │  ") + " "
	return statusStyle.Width(m.width).Render(line)
}

func (m *Model) rebuildViewport() {
	var sb strings.Builder
	for _, msg := range m.messages {
		switch msg.Role {
		case "user":
			fmt.Fprintf(&sb, "%s %s\n\n", userStyle.Render("You:"), msg.Content)
		case "assistant":
			fmt.Fprintf(&sb, "%s %s\n\n", assistantStyle.Render("Assistant:"), msg.Content)
		case "tool":
			content := msg.Content
			if len([]rune(content)) > 60 {
				content = string([]rune(content)[:60])
			}
			prefix := "  [" + content + "]"
			if msg.IsError {
				fmt.Fprintf(&sb, "%s\n", errorStyle.Render(prefix))
			} else {
				fmt.Fprintf(&sb, "%s\n", toolStyle.Render(prefix))
			}
		}
	}

	// Append currently streaming text.
	if m.streaming && m.streamBuf.Len() > 0 {
		fmt.Fprintf(&sb, "%s %s", assistantStyle.Render("Assistant:"), m.streamBuf.String())
	}

	// Show active tool executions.
	for _, v := range m.activeTools {
		fmt.Fprintf(&sb, "\n%s", toolStyle.Render("  ⟳ "+v))
	}

	m.viewport.SetContent(sb.String())
	m.viewport.GotoBottom()
}

// elapsedSince formats a duration since start.
func elapsedSince(start time.Time) time.Duration {
	return time.Since(start).Round(time.Millisecond)
}
