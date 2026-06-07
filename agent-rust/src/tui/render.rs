use ratatui::{
    layout::{Constraint, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};

use crate::tui::state::AppState;

pub fn render(f: &mut Frame, state: &AppState) {
    let chunks = Layout::vertical([
        Constraint::Min(1),
        Constraint::Length(5),
        Constraint::Length(1),
    ])
    .split(f.area());

    render_chat(f, state, chunks[0]);
    render_input(f, state, chunks[1]);
    render_status(f, state, chunks[2]);
}

fn render_chat(f: &mut Frame, state: &AppState, area: ratatui::layout::Rect) {
    let mut lines: Vec<Line> = Vec::new();

    for msg in &state.messages {
        let (prefix, prefix_style, text_style) = match msg.role.as_str() {
            "user" => (
                "You: ",
                Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
                Style::default(),
            ),
            "assistant" => (
                "Assistant: ",
                Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
                Style::default(),
            ),
            "tool" => (
                "",
                Style::default().fg(Color::Yellow),
                Style::default().fg(Color::DarkGray),
            ),
            _ => ("", Style::default(), Style::default()),
        };

        let final_style = if msg.is_error {
            Style::default().fg(Color::Red)
        } else {
            text_style
        };

        lines.push(Line::from(vec![
            Span::styled(prefix, prefix_style),
            Span::styled(&msg.content, final_style),
        ]));
        lines.push(Line::raw(""));
    }

    // Show streaming text with cursor
    if state.is_streaming && !state.stream_buf.is_empty() {
        lines.push(Line::from(vec![
            Span::styled(
                "Assistant: ",
                Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
            ),
            Span::raw(&state.stream_buf),
            Span::styled("▊", Style::default().fg(Color::Green)),
        ]));
    } else if state.is_streaming {
        lines.push(Line::from(vec![
            Span::styled(
                "Assistant: ",
                Style::default().fg(Color::Green).add_modifier(Modifier::BOLD),
            ),
            Span::styled("thinking...", Style::default().fg(Color::DarkGray)),
        ]));
    }

    // Auto-scroll: compute how far down we are
    let total = lines.len() as u16;
    let visible = area.height.saturating_sub(2); // subtract borders
    let auto_scroll = total.saturating_sub(visible);
    let scroll = auto_scroll.saturating_sub(state.scroll_offset);

    let widget = Paragraph::new(Text::from(lines))
        .block(Block::default().borders(Borders::ALL).title(" Pi Agent "))
        .wrap(Wrap { trim: false })
        .scroll((scroll, 0));

    f.render_widget(widget, area);
}

fn render_input(f: &mut Frame, state: &AppState, area: ratatui::layout::Rect) {
    let title = if state.is_streaming {
        " Input (streaming — Ctrl+C to cancel) "
    } else {
        " Input (Ctrl+Enter to send) "
    };

    let widget = Paragraph::new(state.input_buf.as_str())
        .block(Block::default().borders(Borders::ALL).title(title))
        .wrap(Wrap { trim: false });

    f.render_widget(widget, area);
}

fn render_status(f: &mut Frame, state: &AppState, area: ratatui::layout::Rect) {
    let status = format!("  {}  ", state.status_model);
    let widget = Paragraph::new(status)
        .style(Style::default().bg(Color::DarkGray).fg(Color::White));
    f.render_widget(widget, area);
}
