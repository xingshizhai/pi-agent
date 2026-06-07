use std::collections::HashMap;
use std::sync::Arc;
use crate::ai::types::{Message, ToolDefinition};
use crate::tools::Tool;

#[derive(Debug, Clone)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: serde_json::Value,
}

#[derive(Debug)]
pub struct ToolCallResult {
    pub call_id: String,
    pub tool_name: String,
    pub is_error: bool,
    pub content: String,
}

#[derive(Debug, Clone)]
pub enum AgentEvent {
    AgentStart,
    AgentEnd,
    TurnStart,
    TurnEnd,
    StreamChunk(String),
    ToolExecStart { id: String, name: String, args: serde_json::Value },
    ToolExecUpdate { id: String, partial: String },
    ToolExecEnd { id: String, name: String, is_error: bool, content: String },
    Error(String),
}

pub struct AgentContext {
    pub system_prompt: String,
    pub messages: Vec<Message>,
    pub tools: HashMap<String, Arc<dyn Tool>>,
    pub api_key: String,
    pub model_id: String,
}

impl AgentContext {
    pub fn tool_definitions(&self) -> Vec<ToolDefinition> {
        self.tools.values().map(|t| ToolDefinition {
            name: t.name().to_string(),
            description: t.description().to_string(),
            schema: t.schema(),
        }).collect()
    }
}
