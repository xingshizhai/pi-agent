use async_trait::async_trait;
use tokio_util::sync::CancellationToken;

use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct LsTool;

#[async_trait]
impl Tool for LsTool {
    fn name(&self) -> &str { "ls" }
    fn description(&self) -> &str {
        "List directory contents (non-recursive). Returns name, type, size per entry."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to list"}
            },
            "required": ["path"]
        })
    }

    async fn execute(
        &self,
        _id: &str,
        args: serde_json::Value,
        _cancel: CancellationToken,
        _on_update: Option<&UpdateFn>,
    ) -> ToolResult {
        let path = args["path"].as_str().unwrap_or(".").to_string();

        let mut dir = match tokio::fs::read_dir(&path).await {
            Ok(d)  => d,
            Err(e) => return ToolResult::err(format!("cannot ls '{path}': {e}")),
        };

        let mut lines: Vec<String> = Vec::new();

        while let Ok(Some(entry)) = dir.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            let (kind, size) = match entry.metadata().await {
                Ok(m) => {
                    let k = if m.is_dir() { "dir" } else { "file" };
                    (k, m.len())
                }
                Err(_) => ("unknown", 0u64),
            };
            lines.push(format!("{name}\t{kind}\t{size}"));
        }

        lines.sort();

        if lines.is_empty() {
            ToolResult::ok("(empty directory)")
        } else {
            ToolResult::ok(lines.join("\n"))
        }
    }
}
