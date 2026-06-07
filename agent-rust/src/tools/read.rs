use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct ReadTool;

const MAX_LINES: usize = 2000;
const MAX_BYTES: usize = 200 * 1024;

#[async_trait]
impl Tool for ReadTool {
    fn name(&self) -> &str { "read" }
    fn description(&self) -> &str {
        "Read file contents with 1-indexed line numbers. \
         offset=start line (1-indexed), limit=max lines. \
         Returns: 'N\\tcontent\\n' per line."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":   {"type": "string"},
                "offset": {"type": "number", "description": "Start line (1-indexed, default 1)"},
                "limit":  {"type": "number", "description": "Max lines (default 2000)"}
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
        let path = match args["path"].as_str() {
            Some(p) => p.to_string(),
            None => return ToolResult::err("missing 'path' argument"),
        };
        let offset = args["offset"].as_u64().unwrap_or(1).max(1) as usize;
        let limit  = args["limit"].as_u64().map(|n| n as usize).unwrap_or(MAX_LINES);

        let content = match tokio::fs::read_to_string(&path).await {
            Ok(c)  => c,
            Err(e) => return ToolResult::err(format!("cannot read {path}: {e}")),
        };

        let all_lines: Vec<&str> = content.lines().collect();
        let total = all_lines.len();

        // offset is 1-indexed; convert to 0-indexed start
        let start = (offset - 1).min(total);
        let end   = (start + limit).min(total).min(start + MAX_LINES);

        let mut output = String::new();
        let mut bytes  = 0usize;
        let mut actual_end = start;

        for (i, line) in all_lines[start..end].iter().enumerate() {
            let formatted = format!("{}\t{}\n", start + i + 1, line);
            bytes += formatted.len();
            if bytes > MAX_BYTES {
                output.push_str("[...truncated at 200KB limit...]\n");
                break;
            }
            output.push_str(&formatted);
            actual_end = start + i + 1;
        }

        if actual_end < total {
            output.push_str(&format!(
                "[Showing lines {}-{} of {}. Use offset={} to continue.]\n",
                start + 1, actual_end, total, actual_end + 1
            ));
        }

        ToolResult::ok(output)
    }
}
