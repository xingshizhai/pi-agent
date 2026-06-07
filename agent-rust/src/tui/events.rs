use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use crate::tui::state::{AppState, ChatMessage};

/// Handle a keyboard event and update AppState.
/// Returns true if the app should trigger cancellation of the running agent.
pub fn handle_key(state: &mut AppState, key: KeyEvent) -> bool {
    // While streaming: only Ctrl+C is handled (to cancel).
    if state.is_streaming {
        if key.code == KeyCode::Char('c')
            && key.modifiers.contains(KeyModifiers::CONTROL)
        {
            return true; // signal: cancel the running agent
        }
        return false;
    }

    match key.code {
        // Ctrl+Enter OR Alt+Enter → send message
        KeyCode::Enter
            if key.modifiers.contains(KeyModifiers::CONTROL)
                || key.modifiers.contains(KeyModifiers::ALT) =>
        {
            let trimmed = state.input_buf.trim().to_string();
            if !trimmed.is_empty() {
                if handle_slash_command(state, &trimmed) {
                    state.input_buf.clear();
                } else {
                    state.push_history(trimmed);
                    state.send_requested = true;
                }
            }
        }

        // Ctrl+C with empty input → quit; with text → clear input
        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            if state.input_buf.is_empty() {
                state.quit = true;
            } else {
                state.input_buf.clear();
            }
        }

        // Ctrl+L → clear chat display
        KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            state.messages.clear();
            state.stream_buf.clear();
        }

        // PageUp / PageDown: scroll chat
        KeyCode::PageUp => {
            state.scroll_offset = state.scroll_offset.saturating_add(5);
        }
        KeyCode::PageDown => {
            state.scroll_offset = state.scroll_offset.saturating_sub(5);
        }
        KeyCode::Home => {
            state.scroll_offset = u16::MAX; // scroll to top (clamped in render)
        }
        KeyCode::End => {
            state.scroll_offset = 0;
        }

        // Up arrow: navigate input history (only when input is empty)
        KeyCode::Up if state.input_buf.is_empty() || state.history_idx.is_some() => {
            if !state.input_history.is_empty() {
                match state.history_idx {
                    None => {
                        state.saved_draft = state.input_buf.clone();
                        state.history_idx = Some(state.input_history.len() - 1);
                    }
                    Some(idx) if idx > 0 => {
                        state.history_idx = Some(idx - 1);
                    }
                    _ => {}
                }
                if let Some(idx) = state.history_idx {
                    state.input_buf = state.input_history[idx].clone();
                }
            }
        }

        // Down arrow: navigate input history forward
        KeyCode::Down if state.history_idx.is_some() => {
            let len = state.input_history.len();
            if let Some(idx) = state.history_idx {
                if idx + 1 < len {
                    state.history_idx = Some(idx + 1);
                    state.input_buf = state.input_history[idx + 1].clone();
                } else {
                    state.history_idx = None;
                    state.input_buf = state.saved_draft.clone();
                }
            }
        }

        // Text editing
        KeyCode::Backspace => {
            state.input_buf.pop();
        }
        KeyCode::Enter => {
            // Plain Enter adds a newline for multi-line input.
            state.input_buf.push('\n');
        }
        KeyCode::Char(c) => {
            state.input_buf.push(c);
        }

        _ => {}
    }

    false
}

/// Returns true if the command was handled (and input should be cleared).
fn handle_slash_command(state: &mut AppState, cmd: &str) -> bool {
    match cmd {
        "/exit" | "/quit" => {
            state.quit = true;
            true
        }
        "/clear" => {
            state.messages.clear();
            state.stream_buf.clear();
            true
        }
        "/help" => {
            state.messages.push(ChatMessage {
                role: "assistant".into(),
                content: concat!(
                    "Commands: /clear  /help  /exit\n",
                    "Keys: Ctrl+Enter=send  Ctrl+C=cancel/quit\n",
                    "      ↑↓=history  PageUp/PageDown=scroll  Ctrl+L=clear"
                ).into(),
                is_error: false,
            });
            true
        }
        _ if cmd.starts_with('/') => {
            state.messages.push(ChatMessage {
                role: "tool".into(),
                content: format!("✗ Unknown command: {cmd}  (try /help)"),
                is_error: true,
            });
            true
        }
        _ => false,
    }
}
