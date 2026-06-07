use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;

use crate::agent::types::{AgentEvent, ToolCall, ToolCallResult};
use crate::tools::Tool;

/// Execute all tool calls in parallel using a JoinSet.
/// Emits ToolExecStart and ToolExecEnd events for each.
pub async fn execute_parallel(
    calls: Vec<ToolCall>,
    tools: &HashMap<String, Arc<dyn Tool>>,
    event_tx: &mpsc::Sender<AgentEvent>,
    cancel: CancellationToken,
) -> Vec<ToolCallResult> {
    let mut set: JoinSet<ToolCallResult> = JoinSet::new();

    for call in calls {
        let tool = match tools.get(&call.name) {
            Some(t) => Arc::clone(t),
            None => {
                // Unknown tool — report error immediately
                let _ = event_tx.send(AgentEvent::ToolExecEnd {
                    id: call.id.clone(),
                    name: call.name.clone(),
                    is_error: true,
                    content: format!("unknown tool: {}", call.name),
                }).await;
                continue;
            }
        };

        let tx = event_tx.clone();
        let cancel = cancel.clone();
        let call_id = call.id.clone();
        let tool_name = call.name.clone();
        let args = call.arguments.clone();

        // Notify TUI that execution started
        let _ = event_tx.send(AgentEvent::ToolExecStart {
            id: call_id.clone(),
            name: tool_name.clone(),
            args: args.clone(),
        }).await;

        set.spawn(async move {
            let tx2 = tx.clone();
            let cid = call_id.clone();

            // on_update callback streams partial output to the TUI
            let on_update: crate::tools::UpdateFn = Box::new(move |partial: &str| {
                let _ = tx2.try_send(AgentEvent::ToolExecUpdate {
                    id: cid.clone(),
                    partial: partial.to_string(),
                });
            });

            let result = tool.execute(&call_id, args, cancel, Some(&on_update)).await;

            let _ = tx.send(AgentEvent::ToolExecEnd {
                id: call_id.clone(),
                name: tool_name.clone(),
                is_error: result.is_error,
                content: result.content.clone(),
            }).await;

            ToolCallResult {
                call_id,
                tool_name,
                is_error: result.is_error,
                content: result.content,
            }
        });
    }

    let mut results = Vec::new();
    while let Some(join_result) = set.join_next().await {
        if let Ok(r) = join_result {
            results.push(r);
        }
    }
    results
}
