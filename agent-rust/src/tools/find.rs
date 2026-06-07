use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use walkdir::WalkDir;

use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct FindTool;

#[async_trait]
impl Tool for FindTool {
    fn name(&self) -> &str { "find" }
    fn description(&self) -> &str {
        "Find files or directories matching a glob pattern under a path."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Directory to search"},
                "pattern": {"type": "string", "description": "Filename glob (e.g. '*.rs')"},
                "type":    {
                    "type": "string",
                    "enum": ["file", "dir", "any"],
                    "description": "Filter by entry type (default: any)"
                }
            },
            "required": ["path", "pattern"]
        })
    }

    async fn execute(
        &self,
        _id: &str,
        args: serde_json::Value,
        _cancel: CancellationToken,
        _on_update: Option<&UpdateFn>,
    ) -> ToolResult {
        let root = args["path"].as_str().unwrap_or(".").to_string();
        let pattern_str = match args["pattern"].as_str() {
            Some(p) => p.to_string(),
            None    => return ToolResult::err("missing 'pattern'"),
        };
        let filter_type = args["type"].as_str().unwrap_or("any").to_string();

        let glob_pat = match glob::Pattern::new(&pattern_str) {
            Ok(p)  => p,
            Err(e) => return ToolResult::err(format!("invalid glob pattern: {e}")),
        };

        let mut matches: Vec<String> = Vec::new();

        for entry in WalkDir::new(&root).into_iter().filter_map(|e| e.ok()) {
            let is_dir = entry.file_type().is_dir();
            let matches_type = match filter_type.as_str() {
                "file" => !is_dir,
                "dir"  => is_dir,
                _      => true,
            };

            let file_name = entry.file_name().to_str().unwrap_or("");
            if matches_type && glob_pat.matches(file_name) {
                // Return path relative to root
                let rel = entry.path()
                    .strip_prefix(&root)
                    .unwrap_or(entry.path())
                    .display()
                    .to_string();
                if !rel.is_empty() {
                    matches.push(rel);
                }
            }
        }

        matches.sort();

        if matches.is_empty() {
            ToolResult::ok("(no matches)")
        } else {
            ToolResult::ok(matches.join("\n"))
        }
    }
}
