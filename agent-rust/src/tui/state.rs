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
        }
    }

    pub fn apply_agent_event(&mut self, event: AgentEvent) {
        match event {
            AgentEvent::AgentStart => {
                self.is_streaming = true;
                self.stream_buf.clear();
                self.scroll_offset = 0;
            }
            AgentEvent::AgentEnd => {
                self.is_streaming = false;
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
            AgentEvent::ToolExecStart { name, args, .. } => {
                let summary = args["path"]
                    .as_str()
                    .or_else(|| args["command"].as_str())
                    .map(|s| s.chars().take(60).collect::<String>())
                    .unwrap_or_else(|| args.to_string().chars().take(60).collect());
                self.messages.push(ChatMessage {
                    role: "tool".into(),
                    content: format!("[{name}] {summary}"),
                    is_error: false,
                });
            }
            AgentEvent::ToolExecEnd { is_error, content, .. } => {
                if is_error {
                    self.messages.push(ChatMessage {
                        role: "tool".into(),
                        content: format!("[error] {}", content.chars().take(200).collect::<String>()),
                        is_error: true,
                    });
                }
            }
            AgentEvent::Error(e) => {
                self.messages.push(ChatMessage {
                    role: "tool".into(),
                    content: format!("[error] {e}"),
                    is_error: true,
                });
            }
            _ => {}
        }
    }
}
