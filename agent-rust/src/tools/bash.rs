use async_trait::async_trait;
use std::process::Stdio;
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio_util::sync::CancellationToken;

use crate::tools::{Tool, ToolResult, UpdateFn};
use crate::utils::{ansi::strip_ansi, truncate::truncate_output};

pub struct BashTool;

#[async_trait]
impl Tool for BashTool {
    fn name(&self) -> &str { "bash" }
    fn description(&self) -> &str {
        "Run a shell command. stdout and stderr are merged. \
         timeout is in seconds (optional, no default = unlimited)."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (optional, no default)"
                }
            },
            "required": ["command"]
        })
    }

    async fn execute(
        &self,
        _id: &str,
        args: serde_json::Value,
        cancel: CancellationToken,
        on_update: Option<&UpdateFn>,
    ) -> ToolResult {
        let command = match args["command"].as_str() {
            Some(c) => c.to_string(),
            None    => return ToolResult::err("missing 'command'"),
        };
        let timeout_secs = args["timeout"].as_f64();

        let mut child = match Command::new("bash")
            .arg("-c")
            .arg(&command)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c)  => c,
            Err(e) => return ToolResult::err(format!("failed to spawn process: {e}")),
        };

        let stdout = child.stdout.take().expect("piped stdout");
        let stderr = child.stderr.take().expect("piped stderr");

        // Channel to merge stdout+stderr lines in order
        let (line_tx, mut line_rx) = tokio::sync::mpsc::channel::<String>(256);
        let tx2 = line_tx.clone();

        tokio::spawn(async move {
            let mut reader = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                if line_tx.send(line).await.is_err() { break; }
            }
        });
        tokio::spawn(async move {
            let mut reader = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                if tx2.send(line).await.is_err() { break; }
            }
        });

        let mut all_lines: Vec<String> = Vec::new();
        let mut timed_out = false;
        let mut cancelled = false;

        // Collect output with optional timeout and cancellation
        let collect = async {
            loop {
                tokio::select! {
                    line = line_rx.recv() => {
                        match line {
                            Some(l) => {
                                let clean = strip_ansi(&l);
                                if let Some(f) = on_update { f(&clean); }
                                all_lines.push(clean);
                            }
                            None => break,  // both senders dropped (process done)
                        }
                    }
                    _ = cancel.cancelled() => {
                        cancelled = true;
                        break;
                    }
                }
            }
        };

        if let Some(secs) = timeout_secs {
            tokio::select! {
                _ = collect => {}
                _ = tokio::time::sleep(Duration::from_secs_f64(secs)) => {
                    timed_out = true;
                }
            }
        } else {
            collect.await;
        }

        // Kill the process if we timed out or were cancelled
        if timed_out || cancelled {
            let _ = child.kill().await;
        }

        let status = child.wait().await;
        let raw = all_lines.join("\n");
        let output = truncate_output(&raw);

        if timed_out {
            let msg = format!(
                "command timed out after {}s\n{}",
                timeout_secs.unwrap_or(0.0),
                output
            );
            return ToolResult { content: msg, is_error: true, terminate: false };
        }

        if cancelled {
            return ToolResult {
                content: format!("cancelled\n{output}"),
                is_error: true,
                terminate: false,
            };
        }

        let is_error = !status.map(|s| s.success()).unwrap_or(false);
        ToolResult { content: output, is_error, terminate: false }
    }
}
