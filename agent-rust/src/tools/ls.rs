use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct LsTool;

#[async_trait]
impl Tool for LsTool {
    fn name(&self) -> &str { "ls" }
    fn description(&self) -> &str {
        "List directory contents."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list"}
            },
            "required": ["path"]
        })
    }
    async fn execute(&self, _id: &str, _args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        ToolResult::err("not implemented yet")
    }
}
