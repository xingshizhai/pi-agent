package tui

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/pi-agent/agent-go/internal/agent"
)

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmds []tea.Cmd

	switch msg := msg.(type) {

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		headerH := 1 // status bar
		inputH := 5  // input box (border + 3 lines + border)
		vpH := m.height - headerH - inputH
		if vpH < 1 {
			vpH = 1
		}
		if !m.ready {
			m.viewport = viewport.New(m.width, vpH)
			m.ready = true
		} else {
			m.viewport.Width = m.width
			m.viewport.Height = vpH
		}
		m.input.SetWidth(m.width - 4)
		m.rebuildViewport()

	case tea.KeyMsg:
		switch {
		case msg.Type == tea.KeyCtrlC && m.inputMode == ModeNormal && m.input.Value() == "":
			return m, tea.Quit

		case msg.Type == tea.KeyCtrlC && m.inputMode == ModeSending:
			// Cancel current run.
			if m.cancelRun != nil {
				m.cancelRun()
				m.cancelRun = nil
			}
			return m, nil

		case (msg.Type == tea.KeyCtrlJ || (msg.Type == tea.KeyEnter && msg.Alt)) && m.inputMode == ModeNormal:
			// Send message.
			text := strings.TrimSpace(m.input.Value())
			if text == "" {
				return m, nil
			}
			return m.sendMessage(text)

		case msg.Type == tea.KeyUp && m.inputMode == ModeNormal && m.input.Value() == "":
			// Navigate input history.
			if len(m.inputHistory) > 0 {
				if m.historyIdx == -1 {
					m.savedDraft = m.input.Value()
					m.historyIdx = len(m.inputHistory) - 1
				} else if m.historyIdx > 0 {
					m.historyIdx--
				}
				m.input.SetValue(m.inputHistory[m.historyIdx])
				m.input.CursorEnd()
			}
			return m, nil

		case msg.Type == tea.KeyDown && m.historyIdx >= 0:
			if m.historyIdx < len(m.inputHistory)-1 {
				m.historyIdx++
				m.input.SetValue(m.inputHistory[m.historyIdx])
			} else {
				m.historyIdx = -1
				m.input.SetValue(m.savedDraft)
			}
			m.input.CursorEnd()
			return m, nil

		case msg.Type == tea.KeyCtrlL:
			m.messages = nil
			m.streamBuf.Reset()
			m.rebuildViewport()
			return m, nil
		}

		// Handle slash commands (submitted via Ctrl+Enter).
		// We intercept them in the key handler when Enter is pressed.
		// Also check here for immediate /exit etc.
		if m.inputMode == ModeNormal {
			val := strings.TrimSpace(m.input.Value())
			switch val {
			case "/exit", "/quit":
				return m, tea.Quit
			case "/clear":
				m.input.SetValue("")
				m.messages = nil
				m.streamBuf.Reset()
				m.rebuildViewport()
				return m, nil
			case "/help":
				m.input.SetValue("")
				helpMsg := "Commands: /clear  /help  /session  /exit\n" +
					"Keys: Ctrl+Enter=send  Ctrl+C=cancel/quit  ↑↓=history  Ctrl+L=clear"
				m.messages = append(m.messages, RenderMessage{Role: "assistant", Content: helpMsg})
				m.rebuildViewport()
				return m, nil
			case "/session":
				m.input.SetValue("")
				if m.sessionMgr != nil {
					sessions, err := m.sessionMgr.List()
					var info string
					if err != nil || len(sessions) == 0 {
						info = "No sessions found."
					} else {
						var lines []string
						for _, s := range sessions {
							lines = append(lines, fmt.Sprintf("  %s  %s  %s", s.ID[:8], s.CWD, s.Title))
						}
						info = strings.Join(lines, "\n")
					}
					m.messages = append(m.messages, RenderMessage{Role: "assistant", Content: info})
					m.rebuildViewport()
				}
				return m, nil
			}
		}

		// Forward key to input box.
		var inputCmd tea.Cmd
		m.input, inputCmd = m.input.Update(msg)
		cmds = append(cmds, inputCmd)

	case viewport.Model:
		m.viewport = msg

	case agentEventMsg:
		cmds = append(cmds, m.handleAgentEvent(msg.event)...)
	}

	// Update viewport scrolling.
	var vpCmd tea.Cmd
	m.viewport, vpCmd = m.viewport.Update(msg)
	cmds = append(cmds, vpCmd)

	return m, tea.Batch(cmds...)
}

func (m Model) sendMessage(text string) (tea.Model, tea.Cmd) {
	// Record in history.
	m.inputHistory = append(m.inputHistory, text)
	m.historyIdx = -1
	m.input.SetValue("")

	// Add user message to display.
	m.messages = append(m.messages, RenderMessage{Role: "user", Content: text})
	m.inputMode = ModeSending
	m.streaming = true
	m.streamBuf.Reset()
	m.runStart = time.Now()
	m.rebuildViewport()

	// Build agent context and start run.
	agentCtx := m.agentCtxFactory()
	ctx, cancel := context.WithCancel(context.Background())
	m.cancelRun = cancel

	// Load provider via registered factory.
	prov := providerFactory(agentCtx.Provider, agentCtx.APIKey)
	cfg := agent.DefaultConfig()
	eventCh := agent.Run(ctx, text, agentCtx, prov, cfg)
	m.agentEvents = eventCh

	return m, listenAgent(eventCh)
}

func (m Model) handleAgentEvent(ev agent.AgentEvent) []tea.Cmd {
	var cmds []tea.Cmd

	switch ev.Type {
	case agent.EventStreamChunk:
		m.streamBuf.WriteString(ev.TextDelta)
		m.rebuildViewport()
		if m.agentEvents != nil {
			cmds = append(cmds, listenAgent(m.agentEvents))
		}

	case agent.EventToolExecStart:
		m.activeTools[ev.ToolCallID] = ev.ToolName + "…"
		m.rebuildViewport()
		if m.agentEvents != nil {
			cmds = append(cmds, listenAgent(m.agentEvents))
		}

	case agent.EventToolExecUpdate:
		m.activeTools[ev.ToolCallID] = ev.ToolName + ": " + truncate(ev.PartialOutput, 80)
		m.rebuildViewport()
		if m.agentEvents != nil {
			cmds = append(cmds, listenAgent(m.agentEvents))
		}

	case agent.EventToolExecEnd:
		delete(m.activeTools, ev.ToolCallID)
		result := ""
		if ev.ToolResult != nil {
			result = ev.ToolResult.Content
		}
		m.messages = append(m.messages, RenderMessage{
			Role:    "tool",
			Content: "[" + ev.ToolName + "] " + truncate(result, 120),
			IsError: ev.IsError,
		})
		m.rebuildViewport()
		if m.agentEvents != nil {
			cmds = append(cmds, listenAgent(m.agentEvents))
		}

	case agent.EventTurnEnd:
		// Accumulate tokens across turns.
		m.inputTokens += ev.InputTokens
		m.outputTokens += ev.OutputTokens
		if m.agentEvents != nil {
			cmds = append(cmds, listenAgent(m.agentEvents))
		}

	case agent.EventAgentEnd:
		// Finalise streaming message.
		if m.streamBuf.Len() > 0 {
			m.messages = append(m.messages, RenderMessage{
				Role:    "assistant",
				Content: m.streamBuf.String(),
			})
			m.streamBuf.Reset()
		}
		m.streaming = false
		m.inputMode = ModeNormal
		m.lastLatency = elapsedSince(m.runStart)
		m.agentEvents = nil
		if m.cancelRun != nil {
			m.cancelRun()
			m.cancelRun = nil
		}
		m.rebuildViewport()

		// Persist new messages.
		if m.sessionMgr != nil {
			for _, msg := range ev.NewMessages {
				id, err := m.sessionMgr.AppendMessage(m.sessionID, m.lastEntryID, msg)
				if err == nil {
					m.lastEntryID = &id
				}
			}
		}

	case agent.EventError:
		m.flashError = ev.ErrorMessage
		if m.agentEvents != nil {
			cmds = append(cmds, listenAgent(m.agentEvents))
		}
	}

	return cmds
}

func truncate(s string, max int) string {
	// Replace newlines for inline display.
	s = strings.ReplaceAll(s, "\n", " ")
	r := []rune(s)
	if len(r) > max {
		return string(r[:max]) + "…"
	}
	return s
}

