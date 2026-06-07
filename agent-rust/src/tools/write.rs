use async_trait::async_trait;
use std::path::Path;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct WriteTool;

#[async_trait]
impl Tool for WriteTool {
    fn name(&self) -> &str { "write" }
    fn description(&self) -> &str {
        "Write content to a file, creating parent directories as needed."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        })
    }

    async fn execute(
        &self,
        _id: &str,
        args: serde_json::Value,
        _cancel: CancellationToken,
        _on_update: Option<&UpdateFn>,
    ) -> ToolResult {
        let path = match args["path"].as_str() {
            Some(p) => p.to_string(),
            None    => return ToolResult::err("missing 'path'"),
        };
        let content = match args["content"].as_str() {
            Some(c) => c.to_string(),
            None    => return ToolResult::err("missing 'content'"),
        };

        if let Some(parent) = Path::new(&path).parent() {
            if !parent.as_os_str().is_empty() {
                if let Err(e) = tokio::fs::create_dir_all(parent).await {
                    return ToolResult::err(format!("cannot create dirs: {e}"));
                }
            }
        }

        match tokio::fs::write(&path, content).await {
            Ok(_)  => ToolResult::ok(format!("wrote {path}")),
            Err(e) => ToolResult::err(format!("cannot write {path}: {e}")),
        }
    }
}
