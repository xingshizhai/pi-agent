use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct FindTool;

#[async_trait]
impl Tool for FindTool {
    fn name(&self) -> &str { "find" }
    fn description(&self) -> &str {
        "Find files matching a glob pattern."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Directory to search in"},
                "pattern": {"type": "string", "description": "Glob pattern to match"}
            },
            "required": ["path", "pattern"]
        })
    }
    async fn execute(&self, _id: &str, _args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        ToolResult::err("not implemented yet")
    }
}
