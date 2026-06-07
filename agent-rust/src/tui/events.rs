use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use crate::tui::state::AppState;

/// Handle a keyboard event and update AppState.
/// Returns true if the app should trigger cancellation of the running agent.
pub fn handle_key(state: &mut AppState, key: KeyEvent) -> bool {
    // While streaming: only Ctrl+C is handled (to cancel)
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
            if !state.input_buf.trim().is_empty() {
                state.send_requested = true;
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

        // Ctrl+L → clear chat display (history stays in memory)
        KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            state.messages.clear();
        }

        // Scroll
        KeyCode::PageUp => {
            state.scroll_offset = state.scroll_offset.saturating_add(5);
        }
        KeyCode::PageDown => {
            state.scroll_offset = state.scroll_offset.saturating_sub(5);
        }

        // Text editing
        KeyCode::Backspace => {
            state.input_buf.pop();
        }
        KeyCode::Enter => {
            // Plain Enter adds a newline (for multi-line input)
            state.input_buf.push('\n');
        }
        KeyCode::Char(c) => {
            // Handle /exit and /quit slash commands
            state.input_buf.push(c);
            let trimmed = state.input_buf.trim();
            if trimmed == "/exit" || trimmed == "/quit" {
                state.quit = true;
            }
        }

        _ => {}
    }

    false
}
