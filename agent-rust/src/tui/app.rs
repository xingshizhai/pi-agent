use std::sync::Arc;
use anyhow::Result;
use crossterm::event::{Event, EventStream};
use futures_util::StreamExt;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

use crate::agent::{self, AgentContext, AgentEvent};
use crate::ai::provider::Provider;
use crate::tui::{events::handle_key, render::render, state::{AppState, ChatMessage}};

async fn recv_agent_event(rx: &mut Option<mpsc::Receiver<AgentEvent>>) -> Option<AgentEvent> {
    if let Some(r) = rx {
        r.recv().await
    } else {
        std::future::pending::<Option<AgentEvent>>().await
    }
}

/// Main TUI event loop.
/// Runs until the user quits (Ctrl+C on empty input, or /exit command).
pub async fn run(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    ctx: AgentContext,
    provider: Arc<dyn Provider>,
    max_turns: usize,
) -> Result<()> {
    let model_name = ctx.model_id.clone();
    let mut state = AppState::new(&model_name);

    // crossterm async event stream
    let mut event_stream = EventStream::new();

    // Agent event channel (populated when agent is running)
    let mut agent_rx: Option<mpsc::Receiver<AgentEvent>> = None;

    // Cancellation token for the current agent run
    let mut cancel = CancellationToken::new();

    loop {
        // Draw frame
        terminal.draw(|f| render(f, &state))?;

        tokio::select! {
            // Keyboard / terminal events
            maybe_event = event_stream.next() => {
                match maybe_event {
                    Some(Ok(Event::Key(key))) => {
                        let should_cancel = handle_key(&mut state, key);

                        if should_cancel {
                            cancel.cancel();
                            cancel = CancellationToken::new();
                            continue;
                        }

                        if state.quit {
                            break;
                        }

                        if state.send_requested {
                            state.send_requested = false;
                            let user_input = std::mem::take(&mut state.input_buf);

                            state.messages.push(ChatMessage {
                                role: "user".into(),
                                content: user_input.clone(),
                                is_error: false,
                            });
                            state.scroll_offset = 0;

                            // Snapshot the context for the agent task
                            let mut ctx_snapshot = ctx.clone();

                            let (tx, rx) = mpsc::channel::<AgentEvent>(256);
                            agent_rx = Some(rx);

                            let p = Arc::clone(&provider);
                            let cancel_clone = cancel.clone();

                            tokio::spawn(async move {
                                if let Err(e) = agent::r#loop::run(
                                    user_input,
                                    &mut ctx_snapshot,
                                    p,
                                    tx,
                                    cancel_clone,
                                    max_turns,
                                ).await {
                                    tracing::error!("agent loop error: {e}");
                                }
                            });
                        }
                    }
                    Some(Ok(Event::Resize(_, _))) => {
                        // ratatui redraws automatically on next iteration
                    }
                    Some(Err(e)) => {
                        tracing::error!("terminal event error: {e}");
                        break;
                    }
                    None => break,
                    _ => {}
                }
            }

            // Agent events (streaming LLM output, tool calls, etc.)
            agent_event = recv_agent_event(&mut agent_rx) => {
                if let Some(evt) = agent_event {
                    state.apply_agent_event(evt);
                } else {
                    // Channel closed → agent finished
                    agent_rx = None;
                }
            }
        }
    }

    Ok(())
}
