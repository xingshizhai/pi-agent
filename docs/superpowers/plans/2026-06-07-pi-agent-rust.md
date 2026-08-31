# Pi Agent (Rust) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a full terminal coding agent in Rust that lets users drive an LLM to read/write/edit files and run shell commands.

**Architecture:** Five layers (AI provider → agent loop → tools → session → TUI), all communicating via typed channels. The Anthropic/OpenAI providers stream SSE into a `mpsc::Receiver<StreamEvent>`; the agent loop drives the state machine; the TUI subscribes to `AgentEvent` via another channel.

**Tech Stack:** tokio 1 (full), reqwest 0.12 (stream+json), ratatui 0.29, crossterm 0.28 (event-stream), serde/serde_json, async-trait, anyhow, uuid, chrono, walkdir, regex, glob, dirs

---

## Prerequisites

Rust must be installed for the current user:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
rustc --version  # must be ≥ 1.80
```

---

## File Map

```
agent-rust/
├── Cargo.toml
├── src/
│   ├── main.rs                    # CLI entry: parse args, set up TUI
│   ├── ai/
│   │   ├── mod.rs
│   │   ├── types.rs               # Message, Role, MessageContent, StreamEvent, ToolDefinition
│   │   ├── provider.rs            # Provider trait
│   │   ├── sse.rs                 # SSE chunk → (event_type, data) pairs
│   │   ├── anthropic.rs           # Anthropic provider (SSE state machine + message conversion)
│   │   └── openai.rs              # OpenAI provider
│   ├── agent/
│   │   ├── mod.rs
│   │   ├── types.rs               # AgentContext, AgentEvent, ToolCall, ToolCallResult
│   │   ├── loop.rs                # run() — core state machine
│   │   └── executor.rs            # execute_parallel()
│   ├── tools/
│   │   ├── mod.rs                 # Tool trait, ToolResult
│   │   ├── read.rs
│   │   ├── write.rs
│   │   ├── edit.rs
│   │   ├── bash.rs
│   │   ├── find.rs
│   │   ├── grep.rs
│   │   └── ls.rs
│   ├── session/
│   │   ├── mod.rs
│   │   ├── types.rs               # SessionHeader, SessionEntry
│   │   └── manager.rs             # SessionManager
│   ├── tui/
│   │   ├── mod.rs
│   │   ├── app.rs                 # async run() — main event loop
│   │   ├── state.rs               # AppState
│   │   ├── render.rs              # ratatui render functions
│   │   └── events.rs              # handle_key + handle_agent_event
│   └── utils/
│       ├── mod.rs
│       ├── ansi.rs                # strip ANSI escape codes
│       └── truncate.rs            # truncate output to byte limit
└── tests/
    ├── sse_test.rs
    ├── tools_test.rs
    └── session_test.rs
```

---

## Task 1: Project Skeleton

**Files:** Create `agent-rust/Cargo.toml` and all module stub files.

- [ ] **Step 1: Create Cargo.toml**

```toml
[package]
name = "pi-agent"
version = "0.1.0"
edition = "2021"

[[bin]]
name = "pi"
path = "src/main.rs"

[dependencies]
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["stream", "json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
anyhow = "1"
async-trait = "0.1"
uuid = { version = "1", features = ["v4"] }
chrono = { version = "0.4", features = ["serde"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter"] }
futures-util = "0.3"
ratatui = "0.29"
crossterm = { version = "0.28", features = ["event-stream"] }
walkdir = "2"
regex = "1"
glob = "0.3"
dirs = "5"
tokio-util = { version = "0.7", features = ["sync"] }

[dev-dependencies]
tokio-test = "0.4"
```

- [ ] **Step 2: Create stub source files**

```bash
cd agent-rust
mkdir -p src/{ai,agent,tools,session,tui,utils} tests

# Create all stub files
for f in \
  src/main.rs \
  src/ai/mod.rs src/ai/types.rs src/ai/provider.rs src/ai/sse.rs \
  src/ai/anthropic.rs src/ai/openai.rs \
  src/agent/mod.rs src/agent/types.rs src/agent/loop.rs src/agent/executor.rs \
  src/tools/mod.rs src/tools/read.rs src/tools/write.rs src/tools/edit.rs \
  src/tools/bash.rs src/tools/find.rs src/tools/grep.rs src/tools/ls.rs \
  src/session/mod.rs src/session/types.rs src/session/manager.rs \
  src/tui/mod.rs src/tui/app.rs src/tui/state.rs src/tui/render.rs src/tui/events.rs \
  src/utils/mod.rs src/utils/ansi.rs src/utils/truncate.rs \
  tests/sse_test.rs tests/tools_test.rs tests/session_test.rs; do
  echo "// TODO" > $f
done
```

- [ ] **Step 3: Add minimal main.rs so it compiles**

`src/main.rs`:
```rust
fn main() {
    println!("pi-agent");
}
```

- [ ] **Step 4: Verify compile**

```bash
cd agent-rust
cargo check
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add agent-rust/
git commit -m "feat(rust): project skeleton with Cargo.toml and module stubs"
```

---

## Task 2: Utils (ANSI stripping + output truncation)

**Files:** `src/utils/mod.rs`, `src/utils/ansi.rs`, `src/utils/truncate.rs`

- [ ] **Step 1: Write failing tests**

`src/utils/ansi.rs`:
```rust
pub fn strip_ansi(s: &str) -> String {
    // TODO
    s.to_string()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strips_color_codes() {
        assert_eq!(strip_ansi("\x1b[31mhello\x1b[0m"), "hello");
    }
    #[test]
    fn strips_cursor_moves() {
        assert_eq!(strip_ansi("\x1b[2Jhello"), "hello");
    }
    #[test]
    fn passthrough_plain() {
        assert_eq!(strip_ansi("hello world"), "hello world");
    }
}
```

- [ ] **Step 2: Run — expect failures**

```bash
cd agent-rust && cargo test utils::ansi::tests
```

- [ ] **Step 3: Implement strip_ansi**

Replace the `strip_ansi` body:
```rust
pub fn strip_ansi(s: &str) -> String {
    let mut result = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            if chars.peek() == Some(&'[') {
                chars.next(); // consume '['
                // consume until a letter
                for c2 in chars.by_ref() {
                    if c2.is_ascii_alphabetic() {
                        break;
                    }
                }
            }
        } else {
            result.push(c);
        }
    }
    result
}
```

- [ ] **Step 4: Write and implement truncate**

`src/utils/truncate.rs`:
```rust
const MAX_BYTES: usize = 200 * 1024; // 200 KB

pub fn truncate_output(s: &str) -> String {
    if s.len() <= MAX_BYTES {
        return s.to_string();
    }
    // keep the tail (most recent output is more useful)
    let tail = &s[s.len() - MAX_BYTES..];
    format!("[...output truncated, showing last 200KB...]\n{tail}")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn short_passthrough() {
        assert_eq!(truncate_output("hello"), "hello");
    }
    #[test]
    fn long_gets_truncated() {
        let big = "x".repeat(MAX_BYTES + 100);
        let result = truncate_output(&big);
        assert!(result.contains("truncated"));
        assert!(result.len() < big.len());
    }
}
```

- [ ] **Step 5: Wire up mod.rs**

`src/utils/mod.rs`:
```rust
pub mod ansi;
pub mod truncate;
```

`src/main.rs` (add to verify compile):
```rust
mod utils;
fn main() { println!("pi-agent"); }
```

- [ ] **Step 6: Run all utils tests**

```bash
cd agent-rust && cargo test utils
```
Expected: 5 tests pass.

- [ ] **Step 7: Commit**

```bash
git add agent-rust/src/utils/ agent-rust/src/main.rs
git commit -m "feat(rust): utils — ANSI stripping and output truncation"
```

---

## Task 3: AI Types

**Files:** `src/ai/types.rs`, `src/ai/mod.rs`

- [ ] **Step 1: Write serialization tests first**

Add to `src/ai/types.rs`:
```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Role {
    User,
    Assistant,
    ToolResult,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum MessageContent {
    Text { text: String },
    ToolCall {
        id: String,
        name: String,
        arguments: serde_json::Value,
    },
    ToolResult {
        tool_call_id: String,
        tool_name: String,
        content: String,
        #[serde(default)]
        is_error: bool,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: Role,
    pub content: Vec<MessageContent>,
    pub timestamp: i64,
}

#[derive(Debug, Clone)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub schema: serde_json::Value,  // JSON Schema object
}

#[derive(Debug, Clone)]
pub struct StreamOptions {
    pub api_key: String,
    pub max_tokens: u32,
}

impl Default for StreamOptions {
    fn default() -> Self {
        Self { api_key: String::new(), max_tokens: 8192 }
    }
}

/// Events emitted by a provider's streaming response.
#[derive(Debug)]
pub enum StreamEvent {
    TextDelta(String),
    ToolCall { id: String, name: String, arguments: serde_json::Value },
    Done { stop_reason: String },
    Error(anyhow::Error),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_text_content() {
        let c = MessageContent::Text { text: "hello".into() };
        let json = serde_json::to_string(&c).unwrap();
        assert!(json.contains(r#""type":"text""#));
        let back: MessageContent = serde_json::from_str(&json).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn roundtrip_tool_call() {
        let c = MessageContent::ToolCall {
            id: "call_1".into(),
            name: "read".into(),
            arguments: serde_json::json!({"path": "src/main.rs"}),
        };
        let json = serde_json::to_string(&c).unwrap();
        assert!(json.contains(r#""type":"tool_call""#));
        let back: MessageContent = serde_json::from_str(&json).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn role_serializes_snake_case() {
        assert_eq!(serde_json::to_string(&Role::ToolResult).unwrap(), r#""tool_result""#);
    }
}
```

- [ ] **Step 2: Run tests**

```bash
cd agent-rust && cargo test ai::types
```
Expected: 3 tests pass.

- [ ] **Step 3: Wire mod.rs**

`src/ai/mod.rs`:
```rust
pub mod types;
pub mod provider;
pub mod sse;
pub mod anthropic;
pub mod openai;

pub use types::*;
```

Update `src/main.rs`:
```rust
mod utils;
mod ai;
fn main() { println!("pi-agent"); }
```

- [ ] **Step 4: Commit**

```bash
git add agent-rust/src/ai/ agent-rust/src/main.rs
git commit -m "feat(rust): AI types with serde serialization"
```

---

## Task 4: SSE Parser

**Files:** `src/ai/sse.rs`, `tests/sse_test.rs`

- [ ] **Step 1: Write the SSE parser with inline tests**

`src/ai/sse.rs`:
```rust
/// Stateful SSE chunk parser.
/// Feed raw bytes from the HTTP response; get back (event_type, data) pairs.
pub struct SseParser {
    buffer: String,
}

impl Default for SseParser {
    fn default() -> Self { Self { buffer: String::new() } }
}

impl SseParser {
    pub fn new() -> Self { Self::default() }

    /// Push a raw text chunk; returns any complete (event_type, data) pairs.
    /// data == "[DONE]" is filtered out (signals end of OpenAI stream).
    pub fn push(&mut self, chunk: &str) -> Vec<(Option<String>, String)> {
        self.buffer.push_str(chunk);
        let mut events = Vec::new();

        loop {
            match self.buffer.find("\n\n") {
                None => break,
                Some(pos) => {
                    let block = self.buffer[..pos].to_string();
                    self.buffer = self.buffer[pos + 2..].to_string();

                    let mut event_type: Option<String> = None;
                    let mut data = String::new();

                    for line in block.lines() {
                        if let Some(val) = line.strip_prefix("event: ") {
                            event_type = Some(val.trim().to_string());
                        } else if let Some(val) = line.strip_prefix("data: ") {
                            data = val.to_string();
                        }
                    }

                    if !data.is_empty() && data != "[DONE]" {
                        events.push((event_type, data));
                    }
                }
            }
        }
        events
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_single_event() {
        let mut p = SseParser::new();
        let events = p.push("event: ping\ndata: {\"type\":\"ping\"}\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].0.as_deref(), Some("ping"));
        assert_eq!(events[0].1, r#"{"type":"ping"}"#);
    }

    #[test]
    fn handles_split_chunks() {
        let mut p = SseParser::new();
        let e1 = p.push("event: text\ndat");
        assert!(e1.is_empty(), "no complete event yet");
        let e2 = p.push("a: hello\n\n");
        assert_eq!(e2.len(), 1);
        assert_eq!(e2[0].1, "hello");
    }

    #[test]
    fn filters_done_sentinel() {
        let mut p = SseParser::new();
        let events = p.push("data: [DONE]\n\n");
        assert!(events.is_empty());
    }

    #[test]
    fn multiple_events_in_one_chunk() {
        let mut p = SseParser::new();
        let chunk = "event: a\ndata: 1\n\nevent: b\ndata: 2\n\n";
        let events = p.push(chunk);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].1, "1");
        assert_eq!(events[1].1, "2");
    }

    #[test]
    fn no_event_type_is_none() {
        let mut p = SseParser::new();
        let events = p.push("data: just data\n\n");
        assert_eq!(events[0].0, None);
    }
}
```

- [ ] **Step 2: Run tests**

```bash
cd agent-rust && cargo test ai::sse
```
Expected: 5 tests pass.

- [ ] **Step 3: Commit**

```bash
git add agent-rust/src/ai/sse.rs
git commit -m "feat(rust): SSE parser with chunk-boundary handling"
```

---

## Task 5: Provider Trait + Anthropic Implementation

**Files:** `src/ai/provider.rs`, `src/ai/anthropic.rs`

- [ ] **Step 1: Define Provider trait**

`src/ai/provider.rs`:
```rust
use async_trait::async_trait;
use tokio::sync::mpsc;
use crate::ai::types::{Message, ToolDefinition, StreamOptions, StreamEvent};

#[async_trait]
pub trait Provider: Send + Sync {
    async fn stream(
        &self,
        messages: &[Message],
        system_prompt: &str,
        tools: &[ToolDefinition],
        opts: StreamOptions,
    ) -> anyhow::Result<mpsc::Receiver<StreamEvent>>;
}
```

- [ ] **Step 2: Implement Anthropic message conversion (with tests)**

`src/ai/anthropic.rs`:
```rust
use anyhow::Result;
use async_trait::async_trait;
use futures_util::StreamExt;
use reqwest::Client;
use serde_json::{json, Value};
use tokio::sync::mpsc;

use crate::ai::{
    provider::Provider,
    sse::SseParser,
    types::{Message, MessageContent, Role, StreamEvent, StreamOptions, ToolDefinition},
};

pub struct AnthropicProvider {
    client: Client,
}

impl AnthropicProvider {
    pub fn new() -> Self {
        Self { client: Client::new() }
    }
}

/// Convert our internal Message list to Anthropic's wire format.
/// Key rules:
///   - ToolResult messages are merged into a single "user" message as tool_result blocks
///   - AssistantMessage ToolCall content → type:"tool_use" with "input" field
pub fn convert_messages(messages: &[Message]) -> Vec<Value> {
    let mut result: Vec<Value> = Vec::new();
    let mut pending_tool_results: Vec<Value> = Vec::new();

    for msg in messages {
        match msg.role {
            Role::ToolResult => {
                for content in &msg.content {
                    if let MessageContent::ToolResult { tool_call_id, content: text, is_error, .. } = content {
                        pending_tool_results.push(json!({
                            "type": "tool_result",
                            "tool_use_id": tool_call_id,
                            "content": [{"type": "text", "text": text}],
                            "is_error": is_error,
                        }));
                    }
                }
            }
            _ => {
                if !pending_tool_results.is_empty() {
                    result.push(json!({
                        "role": "user",
                        "content": pending_tool_results.drain(..).collect::<Vec<_>>(),
                    }));
                }
                let content_blocks: Vec<Value> = msg.content.iter().map(|c| match c {
                    MessageContent::Text { text } => json!({"type": "text", "text": text}),
                    MessageContent::ToolCall { id, name, arguments } => json!({
                        "type": "tool_use",
                        "id": id,
                        "name": name,
                        "input": arguments,
                    }),
                    MessageContent::ToolResult { .. } => unreachable!(),
                }).collect();

                let role = match msg.role {
                    Role::User => "user",
                    Role::Assistant => "assistant",
                    Role::ToolResult => unreachable!(),
                };
                result.push(json!({ "role": role, "content": content_blocks }));
            }
        }
    }

    // flush remaining tool results
    if !pending_tool_results.is_empty() {
        result.push(json!({ "role": "user", "content": pending_tool_results }));
    }

    result
}

/// Convert our ToolDefinition list to Anthropic's tool format.
pub fn convert_tools(tools: &[ToolDefinition]) -> Vec<Value> {
    tools.iter().map(|t| json!({
        "name": t.name,
        "description": t.description,
        "input_schema": t.schema,
    })).collect()
}

/// State machine that processes Anthropic SSE events into StreamEvents.
#[derive(Default)]
struct StreamState {
    current_type: Option<String>,  // "text" or "tool_use"
    tool_id: Option<String>,
    tool_name: Option<String>,
    tool_args_buf: String,
}

impl StreamState {
    fn process(&mut self, event_type: Option<&str>, data: &str) -> Option<StreamEvent> {
        let v: Value = serde_json::from_str(data).ok()?;
        let msg_type = v["type"].as_str()?;

        match msg_type {
            "content_block_start" => {
                let cb = &v["content_block"];
                let block_type = cb["type"].as_str().unwrap_or("text");
                self.current_type = Some(block_type.to_string());
                if block_type == "tool_use" {
                    self.tool_id = cb["id"].as_str().map(String::from);
                    self.tool_name = cb["name"].as_str().map(String::from);
                    self.tool_args_buf.clear();
                }
                None
            }
            "content_block_delta" => {
                let delta = &v["delta"];
                match delta["type"].as_str()? {
                    "text_delta" => {
                        Some(StreamEvent::TextDelta(delta["text"].as_str().unwrap_or("").to_string()))
                    }
                    "input_json_delta" => {
                        self.tool_args_buf.push_str(delta["partial_json"].as_str().unwrap_or(""));
                        None
                    }
                    _ => None,
                }
            }
            "content_block_stop" => {
                if self.current_type.as_deref() == Some("tool_use") {
                    let args: Value = serde_json::from_str(&self.tool_args_buf)
                        .unwrap_or(Value::Object(serde_json::Map::new()));
                    let evt = StreamEvent::ToolCall {
                        id: self.tool_id.take().unwrap_or_default(),
                        name: self.tool_name.take().unwrap_or_default(),
                        arguments: args,
                    };
                    self.tool_args_buf.clear();
                    self.current_type = None;
                    Some(evt)
                } else {
                    self.current_type = None;
                    None
                }
            }
            "message_stop" => Some(StreamEvent::Done { stop_reason: "stop".to_string() }),
            "message_delta" => {
                let stop_reason = v["delta"]["stop_reason"]
                    .as_str()
                    .unwrap_or("stop")
                    .to_string();
                // message_stop follows, but if stop_reason is not "tool_use" we could end here
                None  // let message_stop handle Done
            }
            _ => None,
        }
    }
}

#[async_trait]
impl Provider for AnthropicProvider {
    async fn stream(
        &self,
        messages: &[Message],
        system_prompt: &str,
        tools: &[ToolDefinition],
        opts: StreamOptions,
    ) -> Result<mpsc::Receiver<StreamEvent>> {
        let body = json!({
            "model": "claude-sonnet-4-6",
            "max_tokens": opts.max_tokens,
            "system": system_prompt,
            "messages": convert_messages(messages),
            "tools": convert_tools(tools),
            "stream": true,
        });

        let response = self.client
            .post("https://api.anthropic.com/v1/messages")
            .header("x-api-key", &opts.api_key)
            .header("anthropic-version", "2023-06-01")
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("Anthropic API error {}: {}", status, body));
        }

        let (tx, rx) = mpsc::channel(256);

        tokio::spawn(async move {
            let mut byte_stream = response.bytes_stream();
            let mut parser = SseParser::new();
            let mut state = StreamState::default();

            while let Some(chunk) = byte_stream.next().await {
                match chunk {
                    Ok(bytes) => {
                        let text = String::from_utf8_lossy(&bytes);
                        for (event_type, data) in parser.push(&text) {
                            if let Some(evt) = state.process(event_type.as_deref(), &data) {
                                let is_done = matches!(evt, StreamEvent::Done { .. });
                                if tx.send(evt).await.is_err() { return; }
                                if is_done { return; }
                            }
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(StreamEvent::Error(e.into())).await;
                        return;
                    }
                }
            }
            let _ = tx.send(StreamEvent::Done { stop_reason: "stop".to_string() }).await;
        });

        Ok(rx)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ai::types::{Message, MessageContent, Role};

    fn user_msg(text: &str) -> Message {
        Message {
            role: Role::User,
            content: vec![MessageContent::Text { text: text.into() }],
            timestamp: 0,
        }
    }

    fn tool_result_msg(id: &str, content: &str) -> Message {
        Message {
            role: Role::ToolResult,
            content: vec![MessageContent::ToolResult {
                tool_call_id: id.into(),
                tool_name: "read".into(),
                content: content.into(),
                is_error: false,
            }],
            timestamp: 0,
        }
    }

    #[test]
    fn user_message_converts() {
        let msgs = vec![user_msg("hello")];
        let result = convert_messages(&msgs);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["role"], "user");
    }

    #[test]
    fn tool_results_merged_into_user() {
        let msgs = vec![
            tool_result_msg("call_1", "file contents"),
            tool_result_msg("call_2", "other contents"),
        ];
        let result = convert_messages(&msgs);
        // Two tool results become ONE user message with two tool_result blocks
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["role"], "user");
        assert_eq!(result[0]["content"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn tool_result_after_user_message() {
        let msgs = vec![user_msg("hi"), tool_result_msg("c1", "out")];
        let result = convert_messages(&msgs);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0]["role"], "user");
        assert_eq!(result[1]["role"], "user"); // tool results flushed as user
        assert_eq!(result[1]["content"][0]["type"], "tool_result");
    }

    #[test]
    fn stream_state_text_delta() {
        let mut s = StreamState::default();
        // simulate content_block_start for text
        s.process(Some("content_block_start"), r#"{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}"#);
        let evt = s.process(Some("content_block_delta"), r#"{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}"#);
        assert!(matches!(evt, Some(StreamEvent::TextDelta(t)) if t == "Hello"));
    }

    #[test]
    fn stream_state_tool_call() {
        let mut s = StreamState::default();
        s.process(Some("content_block_start"), r#"{"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"tc_1","name":"read","input":{}}}"#);
        s.process(Some("content_block_delta"), r#"{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"path\":"}}"#);
        s.process(Some("content_block_delta"), r#"{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\"src/main.rs\"}"}}"#);
        let evt = s.process(Some("content_block_stop"), r#"{"type":"content_block_stop","index":1}"#);
        assert!(matches!(evt, Some(StreamEvent::ToolCall { name, .. }) if name == "read"));
    }
}
```

- [ ] **Step 3: Run tests**

```bash
cd agent-rust && cargo test ai::anthropic
```
Expected: 5 tests pass.

- [ ] **Step 4: Commit**

```bash
git add agent-rust/src/ai/
git commit -m "feat(rust): AI provider trait + Anthropic SSE implementation"
```

---

## Task 6: Tool Trait

**Files:** `src/tools/mod.rs`

- [ ] **Step 1: Define Tool trait and ToolResult**

`src/tools/mod.rs`:
```rust
use async_trait::async_trait;
use tokio_util::sync::CancellationToken;

pub mod read;
pub mod write;
pub mod edit;
pub mod bash;
pub mod find;
pub mod grep;
pub mod ls;

#[derive(Debug, Clone)]
pub struct ToolResult {
    pub content: String,
    pub is_error: bool,
    pub terminate: bool,
}

impl ToolResult {
    pub fn ok(content: impl Into<String>) -> Self {
        Self { content: content.into(), is_error: false, terminate: false }
    }
    pub fn err(content: impl Into<String>) -> Self {
        Self { content: content.into(), is_error: true, terminate: false }
    }
}

pub type UpdateFn = Box<dyn Fn(&str) + Send + Sync>;

#[async_trait]
pub trait Tool: Send + Sync {
    fn name(&self) -> &str;
    fn description(&self) -> &str;
    fn schema(&self) -> serde_json::Value;

    async fn execute(
        &self,
        id: &str,
        args: serde_json::Value,
        cancel: CancellationToken,
        on_update: Option<&UpdateFn>,
    ) -> ToolResult;
}

/// Build the map of all built-in tools.
pub fn all_tools() -> std::collections::HashMap<String, std::sync::Arc<dyn Tool>> {
    use std::sync::Arc;
    let mut map: std::collections::HashMap<String, Arc<dyn Tool>> = std::collections::HashMap::new();
    map.insert("read".into(),  Arc::new(read::ReadTool));
    map.insert("write".into(), Arc::new(write::WriteTool));
    map.insert("edit".into(),  Arc::new(edit::EditTool));
    map.insert("bash".into(),  Arc::new(bash::BashTool));
    map.insert("find".into(),  Arc::new(find::FindTool));
    map.insert("grep".into(),  Arc::new(grep::GrepTool));
    map.insert("ls".into(),    Arc::new(ls::LsTool));
    map
}
```

- [ ] **Step 2: Add stub impls so it compiles**

`src/tools/read.rs` (and repeat pattern for write, edit, bash, find, grep, ls):
```rust
use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct ReadTool;

#[async_trait]
impl Tool for ReadTool {
    fn name(&self) -> &str { "read" }
    fn description(&self) -> &str { "Read the contents of a file." }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":   {"type": "string"},
                "offset": {"type": "number"},
                "limit":  {"type": "number"}
            },
            "required": ["path"]
        })
    }
    async fn execute(&self, _id: &str, _args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        ToolResult::err("not implemented")
    }
}
```

Do the same stub for write.rs, edit.rs, bash.rs, find.rs, grep.rs, ls.rs (change struct name and `name()`).

- [ ] **Step 3: Wire into main.rs**

```rust
mod utils;
mod ai;
mod tools;
fn main() { println!("pi-agent"); }
```

- [ ] **Step 4: cargo check**

```bash
cd agent-rust && cargo check
```

- [ ] **Step 5: Commit**

```bash
git add agent-rust/src/tools/
git commit -m "feat(rust): Tool trait + stubs for all 7 built-in tools"
```

---

## Task 7: read + write Tools

**Files:** `src/tools/read.rs`, `src/tools/write.rs`

- [ ] **Step 1: Write tests for read**

Add to `tests/tools_test.rs`:
```rust
use pi_agent::tools::{Tool, ToolResult};
use pi_agent::tools::read::ReadTool;
use tokio_util::sync::CancellationToken;
use std::io::Write;
use tempfile::NamedTempFile;

// need to add tempfile to dev-dependencies: tempfile = "3"

#[tokio::test]
async fn read_returns_numbered_lines() {
    let mut f = NamedTempFile::new().unwrap();
    writeln!(f, "line one").unwrap();
    writeln!(f, "line two").unwrap();
    let path = f.path().to_str().unwrap().to_string();

    let result = ReadTool.execute("id", serde_json::json!({"path": path}), CancellationToken::new(), None).await;
    assert!(!result.is_error);
    assert!(result.content.contains("1\tline one"));
    assert!(result.content.contains("2\tline two"));
}

#[tokio::test]
async fn read_with_offset_and_limit() {
    let mut f = NamedTempFile::new().unwrap();
    for i in 1..=10 { writeln!(f, "line {i}").unwrap(); }
    let path = f.path().to_str().unwrap().to_string();

    let result = ReadTool.execute("id", serde_json::json!({"path": path, "offset": 3, "limit": 2}), CancellationToken::new(), None).await;
    assert!(!result.is_error);
    assert!(result.content.contains("3\tline 3"));
    assert!(result.content.contains("4\tline 4"));
    assert!(!result.content.contains("5\t"));
}

#[tokio::test]
async fn read_missing_file_is_error() {
    let result = ReadTool.execute("id", serde_json::json!({"path": "/no/such/file.txt"}), CancellationToken::new(), None).await;
    assert!(result.is_error);
}
```

Add to `Cargo.toml` dev-dependencies:
```toml
[dev-dependencies]
tokio-test = "0.4"
tempfile = "3"
```

Also add `name = "pi-agent"` to the lib section or make the module public. Add `src/lib.rs`:
```rust
pub mod utils;
pub mod ai;
pub mod tools;
pub mod agent;
pub mod session;
pub mod tui;
```

And update `Cargo.toml`:
```toml
[lib]
name = "pi_agent"
path = "src/lib.rs"
```

- [ ] **Step 2: Implement read tool**

Replace `src/tools/read.rs`:
```rust
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
        "Read the contents of a file. Returns lines with 1-indexed line numbers as prefix. \
         Use offset (1-indexed) and limit to page through large files."
    }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":   {"type": "string", "description": "Path to file (relative or absolute)"},
                "offset": {"type": "number", "description": "Line number to start from (1-indexed)"},
                "limit":  {"type": "number", "description": "Max lines to read"}
            },
            "required": ["path"]
        })
    }

    async fn execute(&self, _id: &str, args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        let path = match args["path"].as_str() {
            Some(p) => p.to_string(),
            None => return ToolResult::err("missing 'path' argument"),
        };
        let offset = args["offset"].as_u64().unwrap_or(1).max(1) as usize;
        let limit = args["limit"].as_u64().map(|n| n as usize).unwrap_or(MAX_LINES);

        let content = match tokio::fs::read_to_string(&path).await {
            Ok(c) => c,
            Err(e) => return ToolResult::err(format!("cannot read {path}: {e}")),
        };

        let total_lines: Vec<&str> = content.lines().collect();
        let total = total_lines.len();

        let start = (offset - 1).min(total);  // 0-indexed
        let end = (start + limit).min(total);
        let end = end.min(start + MAX_LINES);

        let mut output = String::new();
        let mut bytes = 0usize;

        for (i, line) in total_lines[start..end].iter().enumerate() {
            let formatted = format!("{}\t{}\n", start + i + 1, line);
            bytes += formatted.len();
            if bytes > MAX_BYTES {
                output.push_str(&format!("[...truncated at 200KB limit...]\n"));
                break;
            }
            output.push_str(&formatted);
        }

        if end < total {
            output.push_str(&format!(
                "[Showing lines {}-{} of {}. Use offset={} to continue.]\n",
                start + 1, end, total, end + 1
            ));
        }

        ToolResult::ok(output)
    }
}
```

- [ ] **Step 3: Implement write tool**

`src/tools/write.rs`:
```rust
use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};
use std::path::Path;

pub struct WriteTool;

#[async_trait]
impl Tool for WriteTool {
    fn name(&self) -> &str { "write" }
    fn description(&self) -> &str { "Write content to a file, creating parent directories as needed." }
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

    async fn execute(&self, _id: &str, args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        let path = match args["path"].as_str() {
            Some(p) => p.to_string(),
            None => return ToolResult::err("missing 'path'"),
        };
        let content = match args["content"].as_str() {
            Some(c) => c.to_string(),
            None => return ToolResult::err("missing 'content'"),
        };

        if let Some(parent) = Path::new(&path).parent() {
            if let Err(e) = tokio::fs::create_dir_all(parent).await {
                return ToolResult::err(format!("cannot create dirs: {e}"));
            }
        }

        match tokio::fs::write(&path, content).await {
            Ok(_) => ToolResult::ok(format!("wrote {path}")),
            Err(e) => ToolResult::err(format!("cannot write {path}: {e}")),
        }
    }
}
```

- [ ] **Step 4: Run tests**

```bash
cd agent-rust && cargo test tools_test
```
Expected: 3 read tests pass.

- [ ] **Step 5: Commit**

```bash
git add agent-rust/src/tools/read.rs agent-rust/src/tools/write.rs agent-rust/src/lib.rs agent-rust/Cargo.toml agent-rust/tests/
git commit -m "feat(rust): read and write tools with tests"
```

---

## Task 8: edit Tool

**Files:** `src/tools/edit.rs`

- [ ] **Step 1: Write tests**

Add to `tests/tools_test.rs`:
```rust
use pi_agent::tools::edit::EditTool;

#[tokio::test]
async fn edit_replaces_text() {
    let mut f = NamedTempFile::new().unwrap();
    write!(f, "hello world\nfoo bar\n").unwrap();
    let path = f.path().to_str().unwrap().to_string();

    let result = EditTool.execute("id", serde_json::json!({
        "path": path,
        "edits": [{"oldText": "hello world", "newText": "goodbye world"}]
    }), CancellationToken::new(), None).await;

    assert!(!result.is_error, "got error: {}", result.content);
    let updated = std::fs::read_to_string(&path).unwrap();
    assert!(updated.contains("goodbye world"));
    assert!(!updated.contains("hello world"));
}

#[tokio::test]
async fn edit_fails_on_duplicate_old_text() {
    let mut f = NamedTempFile::new().unwrap();
    write!(f, "foo\nfoo\n").unwrap();
    let path = f.path().to_str().unwrap().to_string();

    let result = EditTool.execute("id", serde_json::json!({
        "path": path,
        "edits": [{"oldText": "foo", "newText": "bar"}]
    }), CancellationToken::new(), None).await;

    assert!(result.is_error);
    assert!(result.content.contains("2 times"));
}

#[tokio::test]
async fn edit_fails_when_old_text_not_found() {
    let mut f = NamedTempFile::new().unwrap();
    write!(f, "hello\n").unwrap();
    let path = f.path().to_str().unwrap().to_string();

    let result = EditTool.execute("id", serde_json::json!({
        "path": path,
        "edits": [{"oldText": "nonexistent", "newText": "x"}]
    }), CancellationToken::new(), None).await;

    assert!(result.is_error);
    assert!(result.content.contains("not found"));
}

#[tokio::test]
async fn edit_multiple_edits_applied() {
    let mut f = NamedTempFile::new().unwrap();
    write!(f, "alpha\nbeta\ngamma\n").unwrap();
    let path = f.path().to_str().unwrap().to_string();

    let result = EditTool.execute("id", serde_json::json!({
        "path": path,
        "edits": [
            {"oldText": "alpha", "newText": "ALPHA"},
            {"oldText": "gamma", "newText": "GAMMA"}
        ]
    }), CancellationToken::new(), None).await;

    assert!(!result.is_error);
    let updated = std::fs::read_to_string(&path).unwrap();
    assert!(updated.contains("ALPHA"));
    assert!(updated.contains("GAMMA"));
    assert!(updated.contains("beta"));
}
```

- [ ] **Step 2: Implement edit tool**

`src/tools/edit.rs`:
```rust
use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct EditTool;

#[async_trait]
impl Tool for EditTool {
    fn name(&self) -> &str { "edit" }
    fn description(&self) -> &str {
        "Edit a file by replacing exact text strings. Each oldText must appear exactly once."
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
                            "oldText": {"type": "string", "description": "Must be unique in the file"},
                            "newText": {"type": "string"}
                        },
                        "required": ["oldText", "newText"]
                    }
                }
            },
            "required": ["path", "edits"]
        })
    }

    async fn execute(&self, _id: &str, args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        let path = match args["path"].as_str() {
            Some(p) => p.to_string(),
            None => return ToolResult::err("missing 'path'"),
        };

        let edits = match args["edits"].as_array() {
            Some(e) => e.clone(),
            None => return ToolResult::err("missing 'edits' array"),
        };

        let original = match tokio::fs::read_to_string(&path).await {
            Ok(c) => c,
            Err(e) => return ToolResult::err(format!("cannot read {path}: {e}")),
        };

        // Validate all edits against original
        for edit in &edits {
            let old = match edit["oldText"].as_str() {
                Some(s) => s,
                None => return ToolResult::err("edit missing 'oldText'"),
            };
            let count = original.matches(old).count();
            if count == 0 {
                return ToolResult::err(format!("oldText not found: {:?}", truncate_str(old, 80)));
            }
            if count > 1 {
                return ToolResult::err(format!(
                    "oldText appears {} times (must be unique): {:?}",
                    count, truncate_str(old, 80)
                ));
            }
        }

        // Apply all edits
        let mut content = original.clone();
        for edit in &edits {
            let old = edit["oldText"].as_str().unwrap();
            let new = edit["newText"].as_str().unwrap_or("");
            content = content.replacen(old, new, 1);
        }

        if let Err(e) = tokio::fs::write(&path, &content).await {
            return ToolResult::err(format!("cannot write {path}: {e}"));
        }

        ToolResult::ok(format!("edited {} ({} edits applied)", path, edits.len()))
    }
}

fn truncate_str(s: &str, max: usize) -> &str {
    if s.len() <= max { s } else { &s[..max] }
}
```

- [ ] **Step 3: Run tests**

```bash
cd agent-rust && cargo test edit
```
Expected: 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add agent-rust/src/tools/edit.rs agent-rust/tests/tools_test.rs
git commit -m "feat(rust): edit tool with uniqueness validation"
```

---

## Task 9: bash Tool

**Files:** `src/tools/bash.rs`

- [ ] **Step 1: Write tests**

Add to `tests/tools_test.rs`:
```rust
use pi_agent::tools::bash::BashTool;

#[tokio::test]
async fn bash_runs_command() {
    let result = BashTool.execute("id", serde_json::json!({"command": "echo hello"}), CancellationToken::new(), None).await;
    assert!(!result.is_error);
    assert!(result.content.trim().ends_with("hello"));
}

#[tokio::test]
async fn bash_captures_stderr() {
    let result = BashTool.execute("id", serde_json::json!({"command": "echo err >&2"}), CancellationToken::new(), None).await;
    assert!(!result.is_error);
    assert!(result.content.contains("err"));
}

#[tokio::test]
async fn bash_nonzero_exit_is_error() {
    let result = BashTool.execute("id", serde_json::json!({"command": "exit 1"}), CancellationToken::new(), None).await;
    assert!(result.is_error);
}

#[tokio::test]
async fn bash_timeout_kills_process() {
    let start = std::time::Instant::now();
    let result = BashTool.execute("id", serde_json::json!({"command": "sleep 10", "timeout": 0.2}), CancellationToken::new(), None).await;
    assert!(start.elapsed().as_secs_f64() < 2.0, "should have timed out quickly");
    assert!(result.is_error);
    assert!(result.content.contains("timed out"));
}
```

- [ ] **Step 2: Implement bash tool**

`src/tools/bash.rs`:
```rust
use async_trait::async_trait;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;
use tokio_util::sync::CancellationToken;
use std::process::Stdio;
use std::time::Duration;
use crate::tools::{Tool, ToolResult, UpdateFn};
use crate::utils::{ansi::strip_ansi, truncate::truncate_output};

pub struct BashTool;

#[async_trait]
impl Tool for BashTool {
    fn name(&self) -> &str { "bash" }
    fn description(&self) -> &str { "Run a shell command. timeout is in seconds (no default = unlimited)." }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "number", "description": "Timeout in seconds (optional, no default)"}
            },
            "required": ["command"]
        })
    }

    async fn execute(&self, _id: &str, args: serde_json::Value, cancel: CancellationToken, on_update: Option<&UpdateFn>) -> ToolResult {
        let command = match args["command"].as_str() {
            Some(c) => c.to_string(),
            None => return ToolResult::err("missing 'command'"),
        };
        let timeout_secs = args["timeout"].as_f64();

        let mut child = match Command::new("bash")
            .arg("-c")
            .arg(&command)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => return ToolResult::err(format!("failed to spawn: {e}")),
        };

        let stdout = child.stdout.take().unwrap();
        let stderr = child.stderr.take().unwrap();

        // Merge stdout and stderr via a task each, collecting into a Vec<String>
        let (out_tx, mut out_rx) = tokio::sync::mpsc::channel::<String>(256);
        let err_tx = out_tx.clone();

        tokio::spawn(async move {
            let mut reader = BufReader::new(stdout).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                if out_tx.send(line).await.is_err() { break; }
            }
        });
        tokio::spawn(async move {
            let mut reader = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                if err_tx.send(line).await.is_err() { break; }
            }
        });

        let mut output_lines: Vec<String> = Vec::new();

        let result = async {
            loop {
                tokio::select! {
                    line = out_rx.recv() => {
                        match line {
                            Some(l) => {
                                let clean = strip_ansi(&l);
                                if let Some(f) = on_update { f(&clean); }
                                output_lines.push(clean);
                            }
                            None => break,
                        }
                    }
                    _ = cancel.cancelled() => {
                        return Err("cancelled".to_string());
                    }
                }
            }
            Ok(())
        };

        let run_result = if let Some(secs) = timeout_secs {
            let dur = Duration::from_secs_f64(secs);
            tokio::select! {
                r = result => r,
                _ = tokio::time::sleep(dur) => {
                    let _ = child.kill().await;
                    Err(format!("command timed out after {secs}s"))
                }
            }
        } else {
            result.await
        };

        let status = child.wait().await;
        let raw_output = output_lines.join("\n");
        let output = truncate_output(&raw_output);

        match run_result {
            Err(e) => ToolResult { content: format!("{e}\n{output}"), is_error: true, terminate: false },
            Ok(_) => {
                let is_error = !status.map(|s| s.success()).unwrap_or(false);
                ToolResult { content: output, is_error, terminate: false }
            }
        }
    }
}
```

- [ ] **Step 3: Run tests**

```bash
cd agent-rust && cargo test bash
```
Expected: 4 tests pass (timeout test may take ~0.5s).

- [ ] **Step 4: Commit**

```bash
git add agent-rust/src/tools/bash.rs
git commit -m "feat(rust): bash tool with timeout and cancellation"
```

---

## Task 10: find + grep + ls Tools

**Files:** `src/tools/find.rs`, `src/tools/grep.rs`, `src/tools/ls.rs`

- [ ] **Step 1: Implement find**

`src/tools/find.rs`:
```rust
use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use walkdir::WalkDir;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct FindTool;

#[async_trait]
impl Tool for FindTool {
    fn name(&self) -> &str { "find" }
    fn description(&self) -> &str { "Find files/dirs matching a glob pattern." }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "pattern": {"type": "string"},
                "type":    {"type": "string", "enum": ["file", "dir", "any"]}
            },
            "required": ["path", "pattern"]
        })
    }

    async fn execute(&self, _id: &str, args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        let root = args["path"].as_str().unwrap_or(".").to_string();
        let pattern = match args["pattern"].as_str() {
            Some(p) => p.to_string(),
            None => return ToolResult::err("missing 'pattern'"),
        };
        let filter_type = args["type"].as_str().unwrap_or("any").to_string();

        let glob_pat = match glob::Pattern::new(&pattern) {
            Ok(p) => p,
            Err(e) => return ToolResult::err(format!("invalid pattern: {e}")),
        };

        let mut matches: Vec<String> = Vec::new();
        for entry in WalkDir::new(&root).into_iter().filter_map(|e| e.ok()) {
            let is_dir = entry.file_type().is_dir();
            let matches_type = match filter_type.as_str() {
                "file" => !is_dir,
                "dir"  => is_dir,
                _      => true,
            };
            if matches_type && glob_pat.matches(entry.file_name().to_str().unwrap_or("")) {
                if let Ok(rel) = entry.path().strip_prefix(&root) {
                    matches.push(rel.display().to_string());
                }
            }
        }

        if matches.is_empty() {
            ToolResult::ok("(no matches)")
        } else {
            ToolResult::ok(matches.join("\n"))
        }
    }
}
```

- [ ] **Step 2: Implement grep**

`src/tools/grep.rs`:
```rust
use async_trait::async_trait;
use regex::RegexBuilder;
use tokio_util::sync::CancellationToken;
use walkdir::WalkDir;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct GrepTool;

#[async_trait]
impl Tool for GrepTool {
    fn name(&self) -> &str { "grep" }
    fn description(&self) -> &str { "Search for a regex pattern in files." }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path":        {"type": "string"},
                "pattern":     {"type": "string"},
                "recursive":   {"type": "boolean"},
                "ignore_case": {"type": "boolean"}
            },
            "required": ["path", "pattern"]
        })
    }

    async fn execute(&self, _id: &str, args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        let path = args["path"].as_str().unwrap_or(".").to_string();
        let pattern_str = match args["pattern"].as_str() {
            Some(p) => p,
            None => return ToolResult::err("missing 'pattern'"),
        };
        let recursive = args["recursive"].as_bool().unwrap_or(true);
        let ignore_case = args["ignore_case"].as_bool().unwrap_or(false);

        let re = match RegexBuilder::new(pattern_str).case_insensitive(ignore_case).build() {
            Ok(r) => r,
            Err(e) => return ToolResult::err(format!("invalid regex: {e}")),
        };

        let mut results: Vec<String> = Vec::new();

        let paths: Vec<_> = if recursive {
            WalkDir::new(&path).into_iter()
                .filter_map(|e| e.ok())
                .filter(|e| e.file_type().is_file())
                .map(|e| e.path().to_path_buf())
                .collect()
        } else {
            vec![std::path::PathBuf::from(&path)]
        };

        for file_path in &paths {
            let content = match std::fs::read_to_string(file_path) {
                Ok(c) => c,
                Err(_) => continue,  // skip binary files
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
```

- [ ] **Step 3: Implement ls**

`src/tools/ls.rs`:
```rust
use async_trait::async_trait;
use tokio_util::sync::CancellationToken;
use crate::tools::{Tool, ToolResult, UpdateFn};

pub struct LsTool;

#[async_trait]
impl Tool for LsTool {
    fn name(&self) -> &str { "ls" }
    fn description(&self) -> &str { "List directory contents (non-recursive)." }
    fn schema(&self) -> serde_json::Value {
        serde_json::json!({
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        })
    }

    async fn execute(&self, _id: &str, args: serde_json::Value, _cancel: CancellationToken, _on_update: Option<&UpdateFn>) -> ToolResult {
        let path = args["path"].as_str().unwrap_or(".").to_string();

        let mut entries = match tokio::fs::read_dir(&path).await {
            Ok(e) => e,
            Err(e) => return ToolResult::err(format!("cannot ls {path}: {e}")),
        };

        let mut lines: Vec<String> = Vec::new();
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            let meta = entry.metadata().await;
            let (kind, size) = match meta {
                Ok(m) => {
                    let k = if m.is_dir() { "dir" } else { "file" };
                    (k, m.len())
                }
                Err(_) => ("unknown", 0),
            };
            lines.push(format!("{}\t{}\t{}", name, kind, size));
        }
        lines.sort();

        ToolResult::ok(lines.join("\n"))
    }
}
```

- [ ] **Step 4: cargo test**

```bash
cd agent-rust && cargo check
```

- [ ] **Step 5: Commit**

```bash
git add agent-rust/src/tools/
git commit -m "feat(rust): find, grep, ls tools"
```

---

## Task 11: Agent Types + Loop

**Files:** `src/agent/types.rs`, `src/agent/mod.rs`, `src/agent/loop.rs`, `src/agent/executor.rs`

- [ ] **Step 1: Define agent types**

`src/agent/types.rs`:
```rust
use std::collections::HashMap;
use std::sync::Arc;
use crate::ai::types::{Message, ToolDefinition};
use crate::tools::{Tool, ToolResult};

#[derive(Debug, Clone)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: serde_json::Value,
}

#[derive(Debug)]
pub struct ToolCallResult {
    pub call_id: String,
    pub tool_name: String,
    pub result: ToolResult,
}

#[derive(Debug, Clone)]
pub enum AgentEvent {
    AgentStart,
    AgentEnd,
    TurnStart,
    TurnEnd,
    StreamChunk(String),
    ToolExecStart { id: String, name: String, args: serde_json::Value },
    ToolExecUpdate { id: String, partial: String },
    ToolExecEnd { id: String, name: String, is_error: bool, content: String },
    Error(String),
}

pub struct AgentContext {
    pub system_prompt: String,
    pub messages: Vec<Message>,
    pub tools: HashMap<String, Arc<dyn Tool>>,
    pub api_key: String,
    pub model_id: String,
}

impl AgentContext {
    pub fn tool_definitions(&self) -> Vec<ToolDefinition> {
        self.tools.values().map(|t| ToolDefinition {
            name: t.name().to_string(),
            description: t.description().to_string(),
            schema: t.schema(),
        }).collect()
    }
}
```

- [ ] **Step 2: Wire mod.rs**

`src/agent/mod.rs`:
```rust
pub mod types;
pub mod r#loop;
pub mod executor;

pub use types::*;
```

- [ ] **Step 3: Implement parallel executor**

`src/agent/executor.rs`:
```rust
use std::collections::HashMap;
use std::sync::Arc;
use tokio::task::JoinSet;
use tokio_util::sync::CancellationToken;
use tokio::sync::mpsc;

use crate::agent::types::{AgentEvent, ToolCall, ToolCallResult};
use crate::tools::Tool;

pub async fn execute_parallel(
    calls: Vec<ToolCall>,
    tools: &HashMap<String, Arc<dyn Tool>>,
    event_tx: &mpsc::Sender<AgentEvent>,
    cancel: CancellationToken,
) -> Vec<ToolCallResult> {
    let mut set = JoinSet::new();

    for call in calls {
        let tool = match tools.get(&call.name) {
            Some(t) => Arc::clone(t),
            None => {
                let _ = event_tx.send(AgentEvent::ToolExecEnd {
                    id: call.id.clone(),
                    name: call.name.clone(),
                    is_error: true,
                    content: format!("unknown tool: {}", call.name),
                }).await;
                continue;
            }
        };

        let tx = event_tx.clone();
        let cancel = cancel.clone();
        let call_id = call.id.clone();
        let tool_name = call.name.clone();
        let args = call.arguments.clone();

        let _ = tx.send(AgentEvent::ToolExecStart {
            id: call_id.clone(),
            name: tool_name.clone(),
            args: args.clone(),
        }).await;

        set.spawn(async move {
            let tx2 = tx.clone();
            let cid = call_id.clone();
            let on_update: crate::tools::UpdateFn = Box::new(move |partial: &str| {
                let _ = tx2.try_send(AgentEvent::ToolExecUpdate {
                    id: cid.clone(),
                    partial: partial.to_string(),
                });
            });

            let result = tool.execute(&call_id, args, cancel, Some(&on_update)).await;

            let _ = tx.send(AgentEvent::ToolExecEnd {
                id: call_id.clone(),
                name: tool_name.clone(),
                is_error: result.is_error,
                content: result.content.clone(),
            }).await;

            ToolCallResult { call_id, tool_name, result }
        });
    }

    let mut results = Vec::new();
    while let Some(Ok(r)) = set.join_next().await {
        results.push(r);
    }
    results
}
```

- [ ] **Step 4: Implement agent loop**

`src/agent/loop.rs`:
```rust
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use chrono::Utc;

use crate::agent::{executor, AgentContext, AgentEvent};
use crate::ai::{
    provider::Provider,
    types::{Message, MessageContent, Role, StreamEvent, StreamOptions},
};
use std::sync::Arc;

pub async fn run(
    user_msg: String,
    ctx: &mut AgentContext,
    provider: Arc<dyn Provider>,
    event_tx: mpsc::Sender<AgentEvent>,
    cancel: CancellationToken,
    max_turns: usize,
) -> anyhow::Result<()> {
    ctx.messages.push(Message {
        role: Role::User,
        content: vec![MessageContent::Text { text: user_msg }],
        timestamp: Utc::now().timestamp_millis(),
    });

    let _ = event_tx.send(AgentEvent::AgentStart).await;

    for _turn in 0..max_turns {
        let _ = event_tx.send(AgentEvent::TurnStart).await;

        let opts = StreamOptions {
            api_key: ctx.api_key.clone(),
            max_tokens: 8192,
        };

        let mut rx = provider.stream(
            &ctx.messages,
            &ctx.system_prompt,
            &ctx.tool_definitions(),
            opts,
        ).await?;

        let mut tool_calls = Vec::new();
        let mut text_buf = String::new();

        loop {
            tokio::select! {
                evt = rx.recv() => {
                    match evt {
                        Some(StreamEvent::TextDelta(delta)) => {
                            text_buf.push_str(&delta);
                            let _ = event_tx.send(AgentEvent::StreamChunk(delta)).await;
                        }
                        Some(StreamEvent::ToolCall { id, name, arguments }) => {
                            tool_calls.push(crate::agent::ToolCall { id, name, arguments });
                        }
                        Some(StreamEvent::Done { .. }) | None => break,
                        Some(StreamEvent::Error(e)) => {
                            let _ = event_tx.send(AgentEvent::Error(e.to_string())).await;
                            let _ = event_tx.send(AgentEvent::AgentEnd).await;
                            return Ok(());
                        }
                    }
                }
                _ = cancel.cancelled() => {
                    let _ = event_tx.send(AgentEvent::AgentEnd).await;
                    return Ok(());
                }
            }
        }

        // Build assistant message
        let mut content = Vec::new();
        if !text_buf.is_empty() {
            content.push(MessageContent::Text { text: text_buf });
        }
        for tc in &tool_calls {
            content.push(MessageContent::ToolCall {
                id: tc.id.clone(),
                name: tc.name.clone(),
                arguments: tc.arguments.clone(),
            });
        }
        ctx.messages.push(Message {
            role: Role::Assistant,
            content,
            timestamp: Utc::now().timestamp_millis(),
        });

        if tool_calls.is_empty() {
            let _ = event_tx.send(AgentEvent::TurnEnd).await;
            break;
        }

        let results = executor::execute_parallel(
            tool_calls,
            &ctx.tools,
            &event_tx,
            cancel.clone(),
        ).await;

        for r in results {
            ctx.messages.push(Message {
                role: Role::ToolResult,
                content: vec![MessageContent::ToolResult {
                    tool_call_id: r.call_id,
                    tool_name: r.tool_name,
                    content: r.result.content,
                    is_error: r.result.is_error,
                }],
                timestamp: Utc::now().timestamp_millis(),
            });
        }

        let _ = event_tx.send(AgentEvent::TurnEnd).await;
    }

    let _ = event_tx.send(AgentEvent::AgentEnd).await;
    Ok(())
}
```

- [ ] **Step 5: cargo check**

```bash
cd agent-rust && cargo check
```

- [ ] **Step 6: Commit**

```bash
git add agent-rust/src/agent/
git commit -m "feat(rust): agent loop with parallel tool execution"
```

---

## Task 12: Session Manager

**Files:** `src/session/types.rs`, `src/session/manager.rs`, `src/session/mod.rs`

- [ ] **Step 1: Write a test**

Add to `tests/session_test.rs`:
```rust
use pi_agent::session::manager::SessionManager;
use tempfile::TempDir;

#[tokio::test]
async fn create_and_load_session() {
    let dir = TempDir::new().unwrap();
    let mgr = SessionManager::new(dir.path().to_path_buf());

    let header = mgr.new_session("/tmp").await.unwrap();
    assert_eq!(header.version, 3);

    let sessions = mgr.list().await.unwrap();
    assert_eq!(sessions.len(), 1);
    assert_eq!(sessions[0].id, header.id);
}
```

- [ ] **Step 2: Implement session types**

`src/session/types.rs`:
```rust
use serde::{Deserialize, Serialize};
use crate::ai::types::Message;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionHeader {
    #[serde(rename = "type")]
    pub kind: String,       // "session"
    pub version: u32,       // 3
    pub id: String,
    pub timestamp: String,  // ISO8601
    pub cwd: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum SessionEntry {
    Message {
        id: String,
        #[serde(rename = "parentId")]
        parent_id: Option<String>,
        timestamp: String,
        message: Message,
    },
    ModelChange {
        id: String,
        #[serde(rename = "parentId")]
        parent_id: Option<String>,
        timestamp: String,
        provider: String,
        #[serde(rename = "modelId")]
        model_id: String,
    },
    Compaction {
        id: String,
        #[serde(rename = "parentId")]
        parent_id: Option<String>,
        timestamp: String,
        summary: String,
        #[serde(rename = "firstKeptEntryId")]
        first_kept_entry_id: String,
        #[serde(rename = "tokensBefore")]
        tokens_before: u64,
    },
}

#[derive(Debug, Clone)]
pub struct SessionMeta {
    pub id: String,
    pub cwd: String,
    pub created_at: String,
}

#[derive(Debug)]
pub struct LoadedSession {
    pub header: SessionHeader,
    pub messages: Vec<Message>,
}
```

- [ ] **Step 3: Implement SessionManager**

`src/session/manager.rs`:
```rust
use std::path::PathBuf;
use anyhow::Result;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use chrono::Utc;
use uuid::Uuid;

use crate::session::types::{LoadedSession, SessionEntry, SessionHeader, SessionMeta};
use crate::ai::types::{Message, Role, MessageContent};

pub struct SessionManager {
    dir: PathBuf,
}

impl SessionManager {
    pub fn new(dir: PathBuf) -> Self {
        Self { dir }
    }

    pub fn default_dir() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".pi")
            .join("sessions")
    }

    fn session_path(&self, id: &str) -> PathBuf {
        self.dir.join(format!("{id}.pi"))
    }

    pub async fn new_session(&self, cwd: &str) -> Result<SessionHeader> {
        tokio::fs::create_dir_all(&self.dir).await?;
        let header = SessionHeader {
            kind: "session".into(),
            version: 3,
            id: Uuid::new_v4().to_string(),
            timestamp: Utc::now().to_rfc3339(),
            cwd: cwd.to_string(),
        };
        let mut file = tokio::fs::OpenOptions::new()
            .create(true).append(true)
            .open(self.session_path(&header.id))
            .await?;
        let mut line = serde_json::to_string(&header)?;
        line.push('\n');
        file.write_all(line.as_bytes()).await?;
        Ok(header)
    }

    pub async fn append_entry(&self, session_id: &str, entry: &SessionEntry) -> Result<()> {
        let mut file = tokio::fs::OpenOptions::new()
            .append(true)
            .open(self.session_path(session_id))
            .await?;
        let mut line = serde_json::to_string(entry)?;
        line.push('\n');
        file.write_all(line.as_bytes()).await?;
        Ok(())
    }

    pub async fn load(&self, id: &str) -> Result<LoadedSession> {
        let file = tokio::fs::File::open(self.session_path(id)).await?;
        let mut lines = BufReader::new(file).lines();

        let first = lines.next_line().await?.ok_or_else(|| anyhow::anyhow!("empty session file"))?;
        let header: SessionHeader = serde_json::from_str(&first)?;

        let mut entries: Vec<SessionEntry> = Vec::new();
        while let Ok(Some(line)) = lines.next_line().await {
            if line.trim().is_empty() { continue; }
            if let Ok(entry) = serde_json::from_str::<SessionEntry>(&line) {
                entries.push(entry);
            }
        }

        // Find last compaction — discard entries before firstKeptEntryId
        let first_kept_id = entries.iter().rev().find_map(|e| {
            if let SessionEntry::Compaction { first_kept_entry_id, .. } = e {
                Some(first_kept_entry_id.clone())
            } else { None }
        });

        let messages: Vec<Message> = if let Some(fkid) = first_kept_id {
            let start = entries.iter().position(|e| {
                matches!(e, SessionEntry::Message { id, .. } if id == &fkid)
            }).unwrap_or(0);
            entries[start..].iter().filter_map(|e| {
                if let SessionEntry::Message { message, .. } = e { Some(message.clone()) } else { None }
            }).collect()
        } else {
            entries.iter().filter_map(|e| {
                if let SessionEntry::Message { message, .. } = e { Some(message.clone()) } else { None }
            }).collect()
        };

        Ok(LoadedSession { header, messages })
    }

    pub async fn list(&self) -> Result<Vec<SessionMeta>> {
        if !self.dir.exists() { return Ok(vec![]); }
        let mut entries = tokio::fs::read_dir(&self.dir).await?;
        let mut metas = Vec::new();
        while let Ok(Some(entry)) = entries.next_entry().await {
            let name = entry.file_name().to_string_lossy().to_string();
            if !name.ends_with(".pi") { continue; }
            let id = name.trim_end_matches(".pi").to_string();
            if let Ok(session) = self.load(&id).await {
                metas.push(SessionMeta {
                    id: session.header.id,
                    cwd: session.header.cwd,
                    created_at: session.header.timestamp,
                });
            }
        }
        Ok(metas)
    }

    pub async fn delete(&self, id: &str) -> Result<()> {
        tokio::fs::remove_file(self.session_path(id)).await?;
        Ok(())
    }
}
```

- [ ] **Step 4: Wire mod.rs**

`src/session/mod.rs`:
```rust
pub mod types;
pub mod manager;
pub use types::*;
```

- [ ] **Step 5: Run session tests**

```bash
cd agent-rust && cargo test session
```

- [ ] **Step 6: Commit**

```bash
git add agent-rust/src/session/ agent-rust/tests/session_test.rs
git commit -m "feat(rust): session manager with NDJSON append-only format"
```

---

## Task 13: TUI State + Render

**Files:** `src/tui/state.rs`, `src/tui/render.rs`, `src/tui/mod.rs`

- [ ] **Step 1: Define AppState**

`src/tui/state.rs`:
```rust
use crate::agent::AgentEvent;

#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub role: String,   // "user", "assistant", "tool"
    pub content: String,
    pub is_error: bool,
}

#[derive(Debug, Default)]
pub struct AppState {
    pub messages: Vec<ChatMessage>,
    pub input_buf: String,
    pub input_cursor: usize,
    pub is_streaming: bool,
    pub stream_buf: String,
    pub scroll_offset: u16,
    pub status_model: String,
    pub status_tokens: u32,
    pub quit: bool,
    pub send_requested: bool,
}

impl AppState {
    pub fn new(model_name: &str) -> Self {
        Self {
            status_model: model_name.to_string(),
            ..Default::default()
        }
    }

    pub fn apply_agent_event(&mut self, event: AgentEvent) {
        match event {
            AgentEvent::AgentStart => { self.is_streaming = true; self.stream_buf.clear(); }
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
            AgentEvent::StreamChunk(chunk) => { self.stream_buf.push_str(&chunk); }
            AgentEvent::ToolExecStart { name, args, .. } => {
                let summary = format!("[{}] {}", name, summarize_args(&args));
                self.messages.push(ChatMessage { role: "tool".into(), content: summary, is_error: false });
            }
            AgentEvent::ToolExecEnd { is_error, content, .. } => {
                if is_error {
                    self.messages.push(ChatMessage { role: "tool".into(), content: format!("[error] {content}"), is_error: true });
                }
            }
            AgentEvent::Error(e) => {
                self.messages.push(ChatMessage { role: "tool".into(), content: format!("[error] {e}"), is_error: true });
            }
            _ => {}
        }
    }
}

fn summarize_args(args: &serde_json::Value) -> String {
    if let Some(path) = args["path"].as_str() {
        return path.to_string();
    }
    if let Some(cmd) = args["command"].as_str() {
        let s: String = cmd.chars().take(60).collect();
        return s;
    }
    args.to_string().chars().take(80).collect()
}
```

- [ ] **Step 2: Implement render**

`src/tui/render.rs`:
```rust
use ratatui::{
    layout::{Constraint, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Wrap},
    Frame,
};
use crate::tui::state::AppState;

pub fn render(f: &mut Frame, state: &AppState) {
    let chunks = Layout::vertical([
        Constraint::Min(1),
        Constraint::Length(5),
        Constraint::Length(1),
    ]).split(f.area());

    render_chat(f, state, chunks[0]);
    render_input(f, state, chunks[1]);
    render_status(f, state, chunks[2]);
}

fn render_chat(f: &mut Frame, state: &AppState, area: ratatui::layout::Rect) {
    let mut lines: Vec<Line> = Vec::new();

    for msg in &state.messages {
        let (prefix_style, text_style) = match msg.role.as_str() {
            "user"      => (Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD), Style::default()),
            "assistant" => (Style::default().fg(Color::Green).add_modifier(Modifier::BOLD), Style::default()),
            "tool"      => (Style::default().fg(Color::Yellow), Style::default().fg(Color::DarkGray)),
            _           => (Style::default(), Style::default()),
        };

        let prefix = match msg.role.as_str() {
            "user"      => "You: ",
            "assistant" => "Assistant: ",
            "tool"      => "",
            _           => "",
        };

        lines.push(Line::from(vec![
            Span::styled(prefix, prefix_style),
            Span::styled(&msg.content, if msg.is_error { Style::default().fg(Color::Red) } else { text_style }),
        ]));
        lines.push(Line::from(""));
    }

    // Show currently streaming text
    if state.is_streaming && !state.stream_buf.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("Assistant: ", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
            Span::raw(&state.stream_buf),
            Span::styled("▊", Style::default().fg(Color::Green)),
        ]));
    }

    let total_lines = lines.len() as u16;
    let visible = area.height.saturating_sub(2);
    let scroll = if total_lines > visible {
        total_lines - visible
    } else {
        0
    };
    let scroll = scroll.saturating_sub(state.scroll_offset);

    let widget = Paragraph::new(Text::from(lines))
        .block(Block::default().borders(Borders::ALL).title("Pi Agent"))
        .wrap(Wrap { trim: false })
        .scroll((scroll, 0));

    f.render_widget(widget, area);
}

fn render_input(f: &mut Frame, state: &AppState, area: ratatui::layout::Rect) {
    let title = if state.is_streaming { "Input (streaming...)" } else { "Input (Ctrl+Enter to send)" };
    let content = format!("{}", &state.input_buf);
    let widget = Paragraph::new(content)
        .block(Block::default().borders(Borders::ALL).title(title))
        .wrap(Wrap { trim: false });
    f.render_widget(widget, area);
}

fn render_status(f: &mut Frame, state: &AppState, area: ratatui::layout::Rect) {
    let status = format!(" {} ", state.status_model);
    let widget = Paragraph::new(status)
        .style(Style::default().bg(Color::DarkGray).fg(Color::White));
    f.render_widget(widget, area);
}
```

- [ ] **Step 3: Wire tui/mod.rs**

`src/tui/mod.rs`:
```rust
pub mod state;
pub mod render;
pub mod events;
pub mod app;
```

- [ ] **Step 4: cargo check**

```bash
cd agent-rust && cargo check
```

- [ ] **Step 5: Commit**

```bash
git add agent-rust/src/tui/
git commit -m "feat(rust): TUI state and ratatui render layout"
```

---

## Task 14: TUI Events + App Loop

**Files:** `src/tui/events.rs`, `src/tui/app.rs`

- [ ] **Step 1: Implement key event handler**

`src/tui/events.rs`:
```rust
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use crate::tui::state::AppState;

pub fn handle_key(state: &mut AppState, key: KeyEvent) {
    if state.is_streaming {
        // Only Ctrl+C allowed while streaming
        if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
            // Cancellation is signalled via cancel token, handled in app.rs
            state.quit = false; // marker: app.rs checks is_streaming + ctrl+c
        }
        return;
    }

    match key.code {
        KeyCode::Enter if key.modifiers.contains(KeyModifiers::CONTROL) => {
            if !state.input_buf.trim().is_empty() {
                state.send_requested = true;
            }
        }
        KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            if state.input_buf.is_empty() {
                state.quit = true;
            } else {
                state.input_buf.clear();
                state.input_cursor = 0;
            }
        }
        KeyCode::Char('l') if key.modifiers.contains(KeyModifiers::CONTROL) => {
            state.messages.clear();
        }
        KeyCode::PageUp => {
            state.scroll_offset = state.scroll_offset.saturating_add(5);
        }
        KeyCode::PageDown => {
            state.scroll_offset = state.scroll_offset.saturating_sub(5);
        }
        KeyCode::Backspace => {
            if !state.input_buf.is_empty() {
                state.input_buf.pop();
            }
        }
        KeyCode::Char(c) => {
            state.input_buf.push(c);
        }
        KeyCode::Enter => {
            state.input_buf.push('\n');
        }
        _ => {}
    }
}
```

- [ ] **Step 2: Implement app loop**

`src/tui/app.rs`:
```rust
use std::sync::Arc;
use anyhow::Result;
use crossterm::event::{Event, EventStream};
use futures_util::StreamExt;
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

use crate::agent::{self, AgentContext};
use crate::ai::provider::Provider;
use crate::session::manager::SessionManager;
use crate::tui::{events::handle_key, render::render, state::{AppState, ChatMessage}};

pub async fn run(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    mut ctx: AgentContext,
    provider: Arc<dyn Provider>,
    session_mgr: Arc<SessionManager>,
    max_turns: usize,
) -> Result<()> {
    let model_name = ctx.model_id.clone();
    let mut state = AppState::new(&model_name);
    let mut event_stream = EventStream::new();
    let mut agent_rx: Option<mpsc::Receiver<crate::agent::AgentEvent>> = None;
    let mut cancel = CancellationToken::new();

    loop {
        terminal.draw(|f| render(f, &state))?;

        tokio::select! {
            Some(Ok(evt)) = event_stream.next() => {
                if let Event::Key(key) = evt {
                    let was_streaming = state.is_streaming;

                    // Check Ctrl+C while streaming → cancel
                    if was_streaming {
                        use crossterm::event::{KeyCode, KeyModifiers};
                        if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL) {
                            cancel.cancel();
                            cancel = CancellationToken::new();
                        }
                        continue;
                    }

                    handle_key(&mut state, key);

                    if state.quit { break; }

                    if state.send_requested {
                        state.send_requested = false;
                        let user_input = std::mem::take(&mut state.input_buf);
                        state.messages.push(ChatMessage {
                            role: "user".into(),
                            content: user_input.clone(),
                            is_error: false,
                        });
                        state.scroll_offset = 0;

                        let (tx, rx) = mpsc::channel(256);
                        agent_rx = Some(rx);

                        let p = Arc::clone(&provider);
                        let cancel_clone = cancel.clone();
                        let mut ctx_snapshot = AgentContext {
                            system_prompt: ctx.system_prompt.clone(),
                            messages: ctx.messages.clone(),
                            tools: ctx.tools.clone(),
                            api_key: ctx.api_key.clone(),
                            model_id: ctx.model_id.clone(),
                        };

                        tokio::spawn(async move {
                            let _ = agent::r#loop::run(
                                user_input,
                                &mut ctx_snapshot,
                                p,
                                tx,
                                cancel_clone,
                                max_turns,
                            ).await;
                        });
                    }
                }
            }

            Some(agent_evt) = async {
                if let Some(rx) = &mut agent_rx {
                    rx.recv().await
                } else {
                    std::future::pending().await
                }
            } => {
                state.apply_agent_event(agent_evt);
            }

            else => { break; }
        }
    }

    Ok(())
}
```

- [ ] **Step 3: cargo check**

```bash
cd agent-rust && cargo check
```
Fix any type errors.

- [ ] **Step 4: Commit**

```bash
git add agent-rust/src/tui/
git commit -m "feat(rust): TUI events and async app loop"
```

---

## Task 15: main.rs CLI Entry

**Files:** `src/main.rs`

- [ ] **Step 1: Implement main.rs**

`src/main.rs`:
```rust
mod utils;
mod ai;
mod agent;
mod tools;
mod session;
mod tui;

use std::sync::Arc;
use anyhow::Result;
use crossterm::{
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use ai::anthropic::AnthropicProvider;
use agent::AgentContext;
use session::manager::SessionManager;
use tools::all_tools;

const SYSTEM_PROMPT: &str = "You are a coding assistant. Use the provided tools to read, write, and edit files, \
and run shell commands to complete programming tasks. Be concise and work methodically.";

#[tokio::main]
async fn main() -> Result<()> {
    let api_key = std::env::var("ANTHROPIC_API_KEY")
        .or_else(|_| std::env::var("OPENAI_API_KEY"))
        .unwrap_or_default();

    if api_key.is_empty() {
        eprintln!("Error: set ANTHROPIC_API_KEY environment variable");
        std::process::exit(1);
    }

    let max_turns: usize = std::env::var("PI_MAX_TURNS")
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(50);

    let session_dir = std::env::var("PI_SESSION_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|_| SessionManager::default_dir());

    let cwd = std::env::current_dir()
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| ".".into());

    let session_mgr = Arc::new(SessionManager::new(session_dir));
    let _session_header = session_mgr.new_session(&cwd).await?;

    let ctx = AgentContext {
        system_prompt: SYSTEM_PROMPT.to_string(),
        messages: Vec::new(),
        tools: all_tools(),
        api_key: api_key.clone(),
        model_id: "claude-sonnet-4-6".to_string(),
    };

    let provider: Arc<dyn ai::provider::Provider> = Arc::new(AnthropicProvider::new());

    // Set up terminal
    enable_raw_mode()?;
    let mut stdout = std::io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result = tui::app::run(&mut terminal, ctx, provider, session_mgr, max_turns).await;

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;

    result
}
```

- [ ] **Step 2: Build**

```bash
cd agent-rust && cargo build 2>&1 | head -50
```
Fix any errors.

- [ ] **Step 3: Smoke test (requires ANTHROPIC_API_KEY)**

```bash
cd agent-rust
ANTHROPIC_API_KEY=sk-ant-... cargo run
# Type: "what is 2+2?" then Ctrl+Enter
# Expected: TUI opens, assistant replies
# Press Ctrl+C then Ctrl+C to quit
```

- [ ] **Step 4: Commit**

```bash
git add agent-rust/src/main.rs
git commit -m "feat(rust): main.rs CLI entry — wire everything together"
```

---

## Task 16: OpenAI Provider

**Files:** `src/ai/openai.rs`

- [ ] **Step 1: Implement OpenAI provider**

`src/ai/openai.rs`:
```rust
use anyhow::Result;
use async_trait::async_trait;
use futures_util::StreamExt;
use reqwest::Client;
use serde_json::{json, Value};
use tokio::sync::mpsc;

use crate::ai::{
    provider::Provider,
    sse::SseParser,
    types::{Message, MessageContent, Role, StreamEvent, StreamOptions, ToolDefinition},
};

pub struct OpenAIProvider {
    client: Client,
    base_url: String,
}

impl OpenAIProvider {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
            base_url: "https://api.openai.com/v1".to_string(),
        }
    }
}

fn convert_messages_openai(messages: &[Message]) -> Vec<Value> {
    let mut result: Vec<Value> = Vec::new();
    let mut pending_tool: Vec<Value> = Vec::new();

    for msg in messages {
        match msg.role {
            Role::ToolResult => {
                for c in &msg.content {
                    if let MessageContent::ToolResult { tool_call_id, content, is_error, .. } = c {
                        pending_tool.push(json!({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": content,
                        }));
                    }
                }
            }
            _ => {
                result.extend(pending_tool.drain(..));
                let role = match msg.role { Role::User => "user", Role::Assistant => "assistant", _ => unreachable!() };
                let content: Vec<Value> = msg.content.iter().filter_map(|c| match c {
                    MessageContent::Text { text } => Some(json!({"type": "text", "text": text})),
                    MessageContent::ToolCall { id, name, arguments } => None, // tools go into tool_calls field
                    _ => None,
                }).collect();
                let tool_calls: Vec<Value> = msg.content.iter().filter_map(|c| match c {
                    MessageContent::ToolCall { id, name, arguments } => Some(json!({
                        "id": id,
                        "type": "function",
                        "function": { "name": name, "arguments": arguments.to_string() }
                    })),
                    _ => None,
                }).collect();

                let mut obj = json!({ "role": role, "content": content });
                if !tool_calls.is_empty() {
                    obj["tool_calls"] = json!(tool_calls);
                }
                result.push(obj);
            }
        }
    }
    result.extend(pending_tool.drain(..));
    result
}

fn convert_tools_openai(tools: &[ToolDefinition]) -> Vec<Value> {
    tools.iter().map(|t| json!({
        "type": "function",
        "function": {
            "name": t.name,
            "description": t.description,
            "parameters": t.schema,
        }
    })).collect()
}

#[async_trait]
impl Provider for OpenAIProvider {
    async fn stream(
        &self,
        messages: &[Message],
        system_prompt: &str,
        tools: &[ToolDefinition],
        opts: StreamOptions,
    ) -> Result<mpsc::Receiver<StreamEvent>> {
        let mut all_messages = vec![json!({"role": "system", "content": system_prompt})];
        all_messages.extend(convert_messages_openai(messages));

        let body = json!({
            "model": "gpt-4o",
            "messages": all_messages,
            "tools": convert_tools_openai(tools),
            "stream": true,
            "stream_options": {"include_usage": true},
        });

        let response = self.client
            .post(format!("{}/chat/completions", self.base_url))
            .header("Authorization", format!("Bearer {}", opts.api_key))
            .header("content-type", "application/json")
            .json(&body)
            .send()
            .await?;

        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(anyhow::anyhow!("OpenAI API error {}: {}", status, body));
        }

        let (tx, rx) = mpsc::channel(256);

        tokio::spawn(async move {
            let mut byte_stream = response.bytes_stream();
            let mut parser = SseParser::new();
            // Per-tool accumulator: index → (id, name, args_buf)
            let mut tool_map: std::collections::HashMap<u64, (String, String, String)> = std::collections::HashMap::new();

            while let Some(chunk) = byte_stream.next().await {
                match chunk {
                    Ok(bytes) => {
                        let text = String::from_utf8_lossy(&bytes);
                        for (_evt, data) in parser.push(&text) {
                            let v: Value = match serde_json::from_str(&data) { Ok(v) => v, Err(_) => continue };

                            if let Some(choices) = v["choices"].as_array() {
                                for choice in choices {
                                    let delta = &choice["delta"];
                                    // text delta
                                    if let Some(content) = delta["content"].as_str() {
                                        if !content.is_empty() {
                                            if tx.send(StreamEvent::TextDelta(content.to_string())).await.is_err() { return; }
                                        }
                                    }
                                    // tool calls
                                    if let Some(tcs) = delta["tool_calls"].as_array() {
                                        for tc in tcs {
                                            let idx = tc["index"].as_u64().unwrap_or(0);
                                            let entry = tool_map.entry(idx).or_insert_with(|| (String::new(), String::new(), String::new()));
                                            if let Some(id) = tc["id"].as_str() { entry.0 = id.to_string(); }
                                            if let Some(name) = tc["function"]["name"].as_str() { entry.1 = name.to_string(); }
                                            if let Some(args) = tc["function"]["arguments"].as_str() { entry.2.push_str(args); }
                                        }
                                    }
                                    // finish
                                    if let Some(reason) = choice["finish_reason"].as_str() {
                                        if reason == "tool_calls" {
                                            for (_, (id, name, args_str)) in tool_map.drain() {
                                                let arguments = serde_json::from_str(&args_str).unwrap_or(Value::Object(Default::default()));
                                                if tx.send(StreamEvent::ToolCall { id, name, arguments }).await.is_err() { return; }
                                            }
                                        }
                                        if reason == "stop" || reason == "tool_calls" {
                                            let _ = tx.send(StreamEvent::Done { stop_reason: reason.to_string() }).await;
                                            return;
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        let _ = tx.send(StreamEvent::Error(e.into())).await;
                        return;
                    }
                }
            }
            let _ = tx.send(StreamEvent::Done { stop_reason: "stop".into() }).await;
        });

        Ok(rx)
    }
}
```

- [ ] **Step 2: cargo check**

```bash
cd agent-rust && cargo check
```

- [ ] **Step 3: Commit**

```bash
git add agent-rust/src/ai/openai.rs
git commit -m "feat(rust): OpenAI provider with SSE streaming"
```

---

## Task 17: Final Build + Acceptance Tests

- [ ] **Step 1: Release build**

```bash
cd agent-rust && cargo build --release 2>&1
```
Expected: produces `target/release/pi`.

- [ ] **Step 2: Run all unit tests**

```bash
cd agent-rust && cargo test
```
Expected: all pass.

- [ ] **Step 3: Verify acceptance criteria**

```bash
# Binary exists
ls -lh target/release/pi

# Starts with valid key
ANTHROPIC_API_KEY=sk-ant-... ./target/release/pi
# → TUI opens
# Type: "list files in current directory using the ls tool"
# Ctrl+Enter → LLM calls ls tool, shows result
# Type: /exit or empty + Ctrl+C twice → exits cleanly
```

- [ ] **Step 4: Final commit**

```bash
git add agent-rust/
git commit -m "feat(rust): pi-agent MVP complete — Anthropic + OpenAI, 7 tools, TUI, session persistence"
```

---

## Self-Review Against Spec

**Coverage check (docs/architecture.md):**
- [x] AI layer: Anthropic SSE — Task 5
- [x] AI layer: OpenAI SSE — Task 16
- [x] Agent loop state machine — Task 11
- [x] Tools: read/write/edit/bash/find/grep/ls — Tasks 7-10
- [x] Session NDJSON append-only + compaction load — Task 12
- [x] TUI streaming render — Task 13
- [x] Ctrl+C cancellation via CancellationToken — Task 14
- [x] Parallel tool execution — Task 11 (executor.rs)
- [x] edit tool: `edits[]` array, uniqueness check — Task 8
- [x] bash timeout in seconds — Task 9
- [x] read offset 1-indexed + line number prefix — Task 7

**Gaps:** OpenAI message format has a subtle issue — when the assistant message has tool calls in `content`, the `tool_calls` field is separate in OpenAI's format. The conversion in Task 16 handles this but should be verified against actual API responses.

**Type consistency:** `AgentContext.tools` is `HashMap<String, Arc<dyn Tool>>` — used consistently in loop.rs and executor.rs. `ToolCall` struct defined in agent/types.rs — used in executor.rs and loop.rs. `StreamOptions` defined in ai/types.rs — used in provider.rs, anthropic.rs, openai.rs.
