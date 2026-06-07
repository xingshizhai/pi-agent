use anyhow::Result;
use async_trait::async_trait;
use std::sync::Mutex;
use std::collections::VecDeque;
use tokio::sync::mpsc;
use serde_json::Value;

use crate::ai::{
    provider::Provider,
    types::{Message, ToolDefinition, StreamOptions, StreamEvent},
};

#[derive(Debug, Clone)]
pub struct MockToolCall {
    pub id: String,
    pub name: String,
    pub args: Value,
}

#[derive(Debug, Clone)]
pub struct MockTurn {
    pub tool_calls: Vec<MockToolCall>,
    pub text: Option<String>,
    pub stop_reason: String,
}

pub struct MockProvider {
    turns: Mutex<VecDeque<MockTurn>>,
}

impl MockProvider {
    pub fn new(turns: Vec<MockTurn>) -> Self {
        Self { turns: Mutex::new(turns.into()) }
    }
}

#[async_trait]
impl Provider for MockProvider {
    async fn stream(
        &self,
        _messages: &[Message],
        _system_prompt: &str,
        _tools: &[ToolDefinition],
        _opts: StreamOptions,
    ) -> Result<mpsc::Receiver<StreamEvent>> {
        let turn = {
            let mut q = self.turns.lock().unwrap();
            q.pop_front().unwrap_or(MockTurn {
                tool_calls: vec![],
                text: None,
                stop_reason: "end_turn".to_string(),
            })
        };

        let (tx, rx) = mpsc::channel(64);
        tokio::spawn(async move {
            if let Some(text) = turn.text {
                let _ = tx.send(StreamEvent::TextDelta(text)).await;
            }
            for tc in turn.tool_calls {
                let _ = tx.send(StreamEvent::ToolCall {
                    id: tc.id,
                    name: tc.name,
                    arguments: tc.args,
                }).await;
            }
            let _ = tx.send(StreamEvent::Done { stop_reason: turn.stop_reason }).await;
        });

        Ok(rx)
    }
}
