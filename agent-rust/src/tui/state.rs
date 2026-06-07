use std::collections::HashMap;
use std::time::Instant;
use crate::agent::AgentEvent;

#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
    pub is_error: bool,
}

#[derive(Debug)]
pub struct AppState {
    pub messages: Vec<ChatMessage>,
    pub input_buf: String,
    pub is_streaming: bool,
    pub stream_buf: String,
    pub scroll_offset: u16,
    pub status_model: String,
    pub quit: bool,
    pub send_requested: bool,

    /// Active tool executions: tool_id → display summary
    pub active_tools: HashMap<String, String>,

    /// Input history and navigation.
    pub input_history: Vec<String>,
    pub history_idx: Option<usize>,
    pub saved_draft: String,

    /// Token statistics (accumulated across turns).
    pub input_tokens: u64,
    pub output_tokens: u64,

    /// Timing.
    pub run_start: Option<Instant>,
    pub last_latency_ms: u64,
}

impl AppState {
    pub fn new(model_name: &str) -> Self {
        Self {
            messages: Vec::new(),
            input_buf: String::new(),
            is_streaming: false,
            stream_buf: String::new(),
            scroll_offset: 0,
            status_model: model_name.to_string(),
            quit: false,
            send_requested: false,
            active_tools: HashMap::new(),
            input_history: Vec::new(),
            history_idx: None,
            saved_draft: String::new(),
            input_tokens: 0,
            output_tokens: 0,
            run_start: None,
            last_latency_ms: 0,
        }
    }

    /// Push text to input history (dedup consecutive identical entries).
    pub fn push_history(&mut self, text: String) {
        if self.input_history.last().map(|s| s.as_str()) != Some(text.as_str()) {
            self.input_history.push(text);
        }
        self.history_idx = None;
    }

    pub fn apply_agent_event(&mut self, event: AgentEvent) {
        match event {
            AgentEvent::AgentStart => {
                self.is_streaming = true;
                self.stream_buf.clear();
                self.scroll_offset = 0;
                self.active_tools.clear();
                self.run_start = Some(Instant::now());
            }
            AgentEvent::AgentEnd => {
                self.is_streaming = false;
                self.active_tools.clear();
                if let Some(start) = self.run_start.take() {
                    self.last_latency_ms = start.elapsed().as_millis() as u64;
                }
                if !self.stream_buf.is_empty() {
                    self.messages.push(ChatMessage {
                        role: "assistant".into(),
                        content: std::mem::take(&mut self.stream_buf),
                        is_error: false,
                    });
                }
            }
            AgentEvent::StreamChunk(chunk) => {
                self.stream_buf.push_str(&chunk);
            }
            AgentEvent::ToolExecStart { id, name, args } => {
                let summary = args["path"]
                    .as_str()
                    .or_else(|| args["command"].as_str())
                    .or_else(|| args["pattern"].as_str())
                    .map(|s| s.chars().take(60).collect::<String>())
                    .unwrap_or_else(|| args.to_string().chars().take(60).collect());
                self.active_tools.insert(id, format!("{name}  {summary}"));
            }
            AgentEvent::ToolExecEnd { id, name, is_error, content } => {
                self.active_tools.remove(&id);
                let summary: String = content
                    .lines()
                    .collect::<Vec<_>>()
                    .join(" ")
                    .chars()
                    .take(120)
                    .collect();
                let icon = if is_error { "✗" } else { "✓" };
                self.messages.push(ChatMessage {
                    role: "tool".into(),
                    content: format!("{icon} [{name}] {summary}"),
                    is_error,
                });
            }
            AgentEvent::Error(e) => {
                self.active_tools.clear();
                self.is_streaming = false;
                self.messages.push(ChatMessage {
                    role: "tool".into(),
                    content: format!("✗ [error] {e}"),
                    is_error: true,
                });
            }
            _ => {}
        }
    }
}
