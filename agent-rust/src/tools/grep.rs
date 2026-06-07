use async_trait::async_trait;
use regex::RegexBuilder;
use tokio_util::sync::CancellationToken;
use walkdir::WalkDir;

use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct GrepTool;

#[async_trait]
impl Tool for GrepTool {
    fn name(&self) -> &str { "grep" }
    fn description(&self) -> &str {
        "Search for a regex pattern in a file or directory tree. \
         Returns matching lines as 'file:line_number:content'."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "pattern":     {"type": "string", "description": "Regex pattern"},
                "recursive":   {"type": "boolean", "description": "Search subdirectories (default true)"},
                "ignore_case": {"type": "boolean", "description": "Case-insensitive (default false)"}
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
        let search_path = args["path"].as_str().unwrap_or(".").to_string();
        let pattern_str = match args["pattern"].as_str() {
            Some(p) => p,
            None    => return ToolResult::err("missing 'pattern'"),
        };
        let recursive   = args["recursive"].as_bool().unwrap_or(true);
        let ignore_case = args["ignore_case"].as_bool().unwrap_or(false);

        let re = match RegexBuilder::new(pattern_str)
            .case_insensitive(ignore_case)
            .build()
        {
            Ok(r)  => r,
            Err(e) => return ToolResult::err(format!("invalid regex: {e}")),
        };

        // Collect files to search
        let path_obj = std::path::Path::new(&search_path);
        let files: Vec<std::path::PathBuf> = if path_obj.is_file() {
            vec![path_obj.to_path_buf()]
        } else if recursive {
            WalkDir::new(&search_path)
                .into_iter()
                .filter_map(|e| e.ok())
                .filter(|e| e.file_type().is_file())
                .map(|e| e.path().to_path_buf())
                .collect()
        } else {
            // Non-recursive: only direct children files
            match std::fs::read_dir(&search_path) {
                Ok(entries) => entries
                    .filter_map(|e| e.ok())
                    .filter(|e| e.path().is_file())
                    .map(|e| e.path())
                    .collect(),
                Err(e) => return ToolResult::err(format!("cannot read dir: {e}")),
            }
        };

        let mut results: Vec<String> = Vec::new();

        for file_path in &files {
            let content = match std::fs::read_to_string(file_path) {
                Ok(c)  => c,
                Err(_) => continue,  // skip binary/unreadable files
            };
            for (i, line) in content.lines().enumerate() {
                if re.is_match(line) {
                    results.push(format!("{}:{}:{}", file_path.display(), i + 1, line));
                }
            }
        }

        if results.is_empty() {
            ToolResult::ok("(no matches)")
        } else {
            ToolResult::ok(results.join("\n"))
        }
    }
}
