use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct ReadTool;

#[async_trait]
impl Tool for ReadTool {
    fn name(&self) -> &str { "read" }
    fn description(&self) -> &str {
        "Read file contents with line numbers. offset=1-indexed start line, limit=max lines."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "File path"},
                "offset": {"type": "number", "description": "Start line (1-indexed)"},
                "limit":  {"type": "number", "description": "Max lines to read"}
            },
            "required": ["path"]
        })
    }
    async fn execute(&self, _id: &str, _args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        ToolResult::err("not implemented yet")
    }
}
