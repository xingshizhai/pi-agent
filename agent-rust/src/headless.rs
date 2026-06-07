use std::io::Read;
use std::sync::Arc;
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

use crate::agent::{self, AgentContext, AgentEvent};
use crate::ai::{
    mock::{MockProvider, MockTurn, MockToolCall},
    provider::Provider,
};
use crate::tools::all_tools;

const SYSTEM_PROMPT: &str = "\
You are a coding assistant with access to file system tools. \
Use the read, write, edit, bash, find, grep, and ls tools to help complete programming tasks. \
Be concise, work methodically, and prefer small targeted edits over large rewrites.";

#[derive(Deserialize)]
struct HeadlessInput {
    prompt: String,
    mock_turns: Option<Vec<MockTurnInput>>,
}

#[derive(Deserialize)]
struct MockTurnInput {
    #[serde(default)]
    tool_calls: Vec<MockToolCallInput>,
    text: Option<String>,
    #[serde(default = "default_stop_reason")]
    stop_reason: String,
}

fn default_stop_reason() -> String {
    "end_turn".to_string()
}

#[derive(Deserialize)]
struct MockToolCallInput {
    id: String,
    name: String,
    args: Value,
}

pub async fn run(api_key: String, use_openrouter: bool) -> anyhow::Result<()> {
    // Read stdin
    let mut raw = String::new();
    std::io::stdin().read_to_string(&mut raw)?;
    let input: HeadlessInput = serde_json::from_str(&raw)
        .map_err(|e| anyhow::anyhow!("invalid headless input: {e}"))?;

    // Build provider
    let provider: Arc<dyn Provider> = if let Some(mock_turns) = input.mock_turns {
        let turns: Vec<MockTurn> = mock_turns
            .into_iter()
            .map(|t| MockTurn {
                tool_calls: t
                    .tool_calls
                    .into_iter()
                    .map(|c| MockToolCall {
                        id: c.id,
                        name: c.name,
                        args: c.args,
                    })
                    .collect(),
                text: t.text,
                stop_reason: t.stop_reason,
            })
            .collect();
        Arc::new(MockProvider::new(turns))
    } else if use_openrouter {
        Arc::new(crate::ai::openai::OpenAIProvider::with_base_url(
            "https://openrouter.ai/api/v1",
        ))
    } else {
        Arc::new(crate::ai::anthropic::AnthropicProvider::new())
    };

    let model_id = std::env::var("PI_MODEL").unwrap_or_else(|_| {
        if use_openrouter {
            "anthropic/claude-sonnet-4-5".to_string()
        } else {
            "claude-sonnet-4-6".to_string()
        }
    });

    let mut ctx = AgentContext {
        system_prompt: SYSTEM_PROMPT.to_string(),
        messages: Vec::new(),
        tools: all_tools(),
        api_key,
        model_id,
    };

    let max_turns: usize = std::env::var("PI_MAX_TURNS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(50);

    let (tx, mut rx) = mpsc::channel(256);
    let cancel = CancellationToken::new();

    // Spawn agent loop — channel keeps rx alive while agent runs
    let cancel2 = cancel.clone();
    let handle = tokio::spawn(async move {
        agent::r#loop::run(input.prompt, &mut ctx, provider, tx, cancel2, max_turns).await
    });

    // Emit events as NDJSON to stdout
    let mut turn: usize = 0;
    while let Some(event) = rx.recv().await {
        let line = match event {
            AgentEvent::AgentStart => json!({"type": "agent_start"}),
            AgentEvent::TurnStart => {
                turn += 1;
                json!({"type": "turn_start", "turn": turn})
            }
            AgentEvent::TurnEnd => json!({"type": "turn_end", "turn": turn}),
            AgentEvent::StreamChunk(text) => json!({"type": "stream_chunk", "text": text}),
            AgentEvent::ToolExecStart { id, name, args } => {
                json!({"type": "tool_call", "id": id, "name": name, "args": args})
            }
            AgentEvent::ToolExecUpdate { id, partial } => {
                json!({"type": "tool_update", "id": id, "partial": partial})
            }
            AgentEvent::ToolExecEnd {
                id,
                name,
                is_error,
                content,
            } => {
                json!({"type": "tool_result", "id": id, "name": name, "is_error": is_error, "content": content})
            }
            AgentEvent::AgentEnd => {
                json!({"type": "agent_end", "stop_reason": "end_turn", "turns": turn})
            }
            AgentEvent::Error(msg) => json!({"type": "error", "message": msg}),
        };
        println!("{line}");
    }

    handle.await??;
    Ok(())
}
