use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct EditTool;

#[async_trait]
impl Tool for EditTool {
    fn name(&self) -> &str { "edit" }
    fn description(&self) -> &str {
        "Edit a file by replacing exact text strings. \
         Each oldText must appear exactly once in the file. \
         All edits are validated before any writes."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldText": {
                                "type": "string",
                                "description": "Exact text to replace — must appear exactly once"
                            },
                            "newText": {"type": "string"}
                        },
                        "required": ["oldText", "newText"]
                    }
                }
            },
            "required": ["path", "edits"]
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

        let edits = match args["edits"].as_array() {
            Some(e) => e.clone(),
            None    => return ToolResult::err("missing 'edits' array"),
        };

        if edits.is_empty() {
            return ToolResult::err("'edits' array is empty");
        }

        let original = match tokio::fs::read_to_string(&path).await {
            Ok(c)  => c,
            Err(e) => return ToolResult::err(format!("cannot read {path}: {e}")),
        };

        // Validate ALL edits against the original before writing anything
        for edit in &edits {
            let old = match edit["oldText"].as_str() {
                Some(s) => s,
                None    => return ToolResult::err("edit missing 'oldText'"),
            };
            if edit["newText"].as_str().is_none() {
                return ToolResult::err("edit missing 'newText'");
            }

            let count = original.matches(old).count();
            if count == 0 {
                return ToolResult::err(format!(
                    "oldText not found in file: {:?}",
                    truncate_str(old, 80)
                ));
            }
            if count > 1 {
                return ToolResult::err(format!(
                    "oldText appears {} times (must be unique): {:?}",
                    count,
                    truncate_str(old, 80)
                ));
            }
        }

        // All validated — apply edits sequentially to the content
        let mut content = original;
        for edit in &edits {
            let old = edit["oldText"].as_str().unwrap();
            let new = edit["newText"].as_str().unwrap();
            // replacen(old, new, 1) since we know it appears exactly once
            content = content.replacen(old, new, 1);
        }

        if let Err(e) = tokio::fs::write(&path, &content).await {
            return ToolResult::err(format!("cannot write {path}: {e}"));
        }

        ToolResult::ok(format!("{} edit(s) applied to {}", edits.len(), path))
    }
}

fn truncate_str(s: &str, max: usize) -> &str {
    if s.len() <= max { s } else { &s[..max] }
}
