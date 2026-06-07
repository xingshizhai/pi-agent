use async_trait::async_trait;
use tokio::sync::mpsc;
use crate::ai::types::{Message, ToolDefinition, StreamOptions, StreamEvent};

#[async_trait]
pub trait Provider: Send + Sync {
    async fn stream(
        &self,
        messages: &[Message],
        system_prompt: &str,
        tools: &[ToolDefinition],
        opts: StreamOptions,
    ) -> anyhow::Result<mpsc::Receiver<StreamEvent>>;
}
