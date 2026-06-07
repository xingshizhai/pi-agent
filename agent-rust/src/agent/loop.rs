use std::sync::Arc;
use chrono::Utc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

use crate::agent::{executor, AgentContext, AgentEvent, ToolCall};
use crate::ai::{
    provider::Provider,
    types::{Message, MessageContent, Role, StreamEvent, StreamOptions},
};

/// Run the agent loop for one user message.
///
/// Emits events to `event_tx` for the TUI to display.
/// Runs until: LLM returns no tool calls, max_turns exceeded, or cancellation.
pub async fn run(
    user_msg: String,
    ctx: &mut AgentContext,
    provider: Arc<dyn Provider>,
    event_tx: mpsc::Sender<AgentEvent>,
    cancel: CancellationToken,
    max_turns: usize,
) -> anyhow::Result<()> {
    ctx.messages.push(Message {
        role: Role::User,
        content: vec![MessageContent::Text { text: user_msg }],
        timestamp: Utc::now().timestamp_millis(),
    });

    let _ = event_tx.send(AgentEvent::AgentStart).await;

    for _turn in 0..max_turns {
        let _ = event_tx.send(AgentEvent::TurnStart).await;

        let opts = StreamOptions {
            api_key: ctx.api_key.clone(),
            max_tokens: 8192,
        };

        let mut rx = provider.stream(
            &ctx.messages,
            &ctx.system_prompt,
            &ctx.tool_definitions(),
            opts,
        ).await?;

        let mut tool_calls: Vec<ToolCall> = Vec::new();
        let mut text_buf = String::new();

        // Consume the stream, collecting text and tool calls
        loop {
            tokio::select! {
                evt = rx.recv() => {
                    match evt {
                        Some(StreamEvent::TextDelta(delta)) => {
                            text_buf.push_str(&delta);
                            let _ = event_tx.send(AgentEvent::StreamChunk(delta)).await;
                        }
                        Some(StreamEvent::ToolCall { id, name, arguments }) => {
                            tool_calls.push(ToolCall { id, name, arguments });
                        }
                        Some(StreamEvent::Done { .. }) | None => break,
                        Some(StreamEvent::Error(e)) => {
                            let _ = event_tx.send(AgentEvent::Error(e.to_string())).await;
                            let _ = event_tx.send(AgentEvent::AgentEnd).await;
                            return Ok(());
                        }
                    }
                }
                _ = cancel.cancelled() => {
                    let _ = event_tx.send(AgentEvent::AgentEnd).await;
                    return Ok(());
                }
            }
        }

        // Build assistant message from what we received
        let mut assistant_content = Vec::new();
        if !text_buf.is_empty() {
            assistant_content.push(MessageContent::Text { text: text_buf });
        }
        for tc in &tool_calls {
            assistant_content.push(MessageContent::ToolCall {
                id: tc.id.clone(),
                name: tc.name.clone(),
                arguments: tc.arguments.clone(),
            });
        }

        if !assistant_content.is_empty() {
            ctx.messages.push(Message {
                role: Role::Assistant,
                content: assistant_content,
                timestamp: Utc::now().timestamp_millis(),
            });
        }

        // No tool calls → conversation turn is done
        if tool_calls.is_empty() {
            let _ = event_tx.send(AgentEvent::TurnEnd).await;
            break;
        }

        // Execute all tool calls (parallel)
        let results = executor::execute_parallel(
            tool_calls,
            &ctx.tools,
            &event_tx,
            cancel.clone(),
        ).await;

        // Append tool results to message history
        for r in results {
            ctx.messages.push(Message {
                role: Role::ToolResult,
                content: vec![MessageContent::ToolResult {
                    tool_call_id: r.call_id,
                    tool_name: r.tool_name,
                    content: r.content,
                    is_error: r.is_error,
                }],
                timestamp: Utc::now().timestamp_millis(),
            });
        }

        let _ = event_tx.send(AgentEvent::TurnEnd).await;
        // Loop again — LLM sees tool results and continues
    }

    let _ = event_tx.send(AgentEvent::AgentEnd).await;
    Ok(())
}
