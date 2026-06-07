use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct GrepTool;

#[async_trait]
impl Tool for GrepTool {
    fn name(&self) -> &str { "grep" }
    fn description(&self) -> &str {
        "Search for regex in files."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Directory or file to search"},
                "pattern": {"type": "string", "description": "Regex pattern to search for"}
            },
            "required": ["path", "pattern"]
        })
    }
    async fn execute(&self, _id: &str, _args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        ToolResult::err("not implemented yet")
    }
}
