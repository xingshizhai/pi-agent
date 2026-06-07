use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct BashTool;

#[async_trait]
impl Tool for BashTool {
    fn name(&self) -> &str { "bash" }
    fn description(&self) -> &str {
        "Run a shell command."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"}
            },
            "required": ["command"]
        })
    }
    async fn execute(&self, _id: &str, _args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        ToolResult::err("not implemented yet")
    }
}
