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

impl Default for AnthropicProvider {
    fn default() -> Self {
        Self { client: Client::new() }
    }
}

impl AnthropicProvider {
    pub fn new() -> Self {
        Self::default()
    }
}

/// Convert our internal Message list to Anthropic's wire format.
///
/// Rules (from Anthropic API spec):
/// - ToolResult messages are merged into a single user message as tool_result content blocks
/// - AssistantMessage ToolCall content → type:"tool_use" with "input" field
/// - Consecutive ToolResult messages become one user message (not separate ones)
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
                // Flush any accumulated tool results as a user message first
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
                    MessageContent::ToolResult { .. } => unreachable!("ToolResult in non-ToolResult message"),
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

    // Flush any remaining tool results
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
/// Must maintain state across events because tool call arguments arrive in fragments.
#[derive(Default)]
struct AnthropicStreamState {
    current_block_type: Option<String>,  // "text" or "tool_use"
    tool_id: Option<String>,
    tool_name: Option<String>,
    tool_args_buf: String,  // accumulates input_json_delta fragments
}

impl AnthropicStreamState {
    /// Process one SSE event. Returns Some(StreamEvent) if a complete event is ready.
    fn process(&mut self, _event_type: Option<&str>, data: &str) -> Option<StreamEvent> {
        let v: Value = serde_json::from_str(data).ok()?;
        let msg_type = v["type"].as_str()?;

        match msg_type {
            "content_block_start" => {
                let cb = &v["content_block"];
                let block_type = cb["type"].as_str().unwrap_or("text");
                self.current_block_type = Some(block_type.to_string());
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
                    "text_delta" => Some(StreamEvent::TextDelta(
                        delta["text"].as_str().unwrap_or("").to_string()
                    )),
                    "input_json_delta" => {
                        // Accumulate tool argument fragments
                        self.tool_args_buf.push_str(
                            delta["partial_json"].as_str().unwrap_or("")
                        );
                        None
                    }
                    _ => None,
                }
            }
            "content_block_stop" => {
                if self.current_block_type.as_deref() == Some("tool_use") {
                    // Parse the accumulated JSON arguments
                    let args: Value = serde_json::from_str(&self.tool_args_buf)
                        .unwrap_or(Value::Object(serde_json::Map::new()));
                    let evt = StreamEvent::ToolCall {
                        id: self.tool_id.take().unwrap_or_default(),
                        name: self.tool_name.take().unwrap_or_default(),
                        arguments: args,
                    };
                    self.tool_args_buf.clear();
                    self.current_block_type = None;
                    Some(evt)
                } else {
                    self.current_block_type = None;
                    None
                }
            }
            "message_stop" => Some(StreamEvent::Done {
                stop_reason: "stop".to_string(),
            }),
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
            let mut state = AnthropicStreamState::default();

            while let Some(chunk) = byte_stream.next().await {
                match chunk {
                    Ok(bytes) => {
                        let text = String::from_utf8_lossy(&bytes);
                        for (event_type, data) in parser.push(&text) {
                            if let Some(evt) = state.process(event_type.as_deref(), &data) {
                                let is_done = matches!(evt, StreamEvent::Done { .. });
                                if tx.send(evt).await.is_err() {
                                    return; // receiver was dropped
                                }
                                if is_done {
                                    return;
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
            // Stream ended without message_stop — send Done anyway
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

    fn assistant_msg_with_tool(call_id: &str, tool_name: &str, args: Value) -> Message {
        Message {
            role: Role::Assistant,
            content: vec![MessageContent::ToolCall {
                id: call_id.into(),
                name: tool_name.into(),
                arguments: args,
            }],
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
        assert_eq!(result[0]["content"][0]["type"], "text");
        assert_eq!(result[0]["content"][0]["text"], "hello");
    }

    #[test]
    fn assistant_tool_call_converts() {
        let msgs = vec![assistant_msg_with_tool("c1", "read", json!({"path": "foo.rs"}))];
        let result = convert_messages(&msgs);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["role"], "assistant");
        assert_eq!(result[0]["content"][0]["type"], "tool_use");
        assert_eq!(result[0]["content"][0]["id"], "c1");
        assert_eq!(result[0]["content"][0]["name"], "read");
        assert_eq!(result[0]["content"][0]["input"]["path"], "foo.rs");
    }

    #[test]
    fn two_tool_results_merged_into_one_user_message() {
        let msgs = vec![
            tool_result_msg("c1", "file one"),
            tool_result_msg("c2", "file two"),
        ];
        let result = convert_messages(&msgs);
        // Two consecutive tool results → ONE user message with two tool_result blocks
        assert_eq!(result.len(), 1, "expected 1 message, got: {result:?}");
        assert_eq!(result[0]["role"], "user");
        let content = result[0]["content"].as_array().unwrap();
        assert_eq!(content.len(), 2);
        assert_eq!(content[0]["type"], "tool_result");
        assert_eq!(content[1]["type"], "tool_result");
    }

    #[test]
    fn tool_result_after_user_flushed_correctly() {
        let msgs = vec![user_msg("hi"), tool_result_msg("c1", "out")];
        let result = convert_messages(&msgs);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0]["role"], "user");
        assert_eq!(result[0]["content"][0]["type"], "text");
        assert_eq!(result[1]["role"], "user");
        assert_eq!(result[1]["content"][0]["type"], "tool_result");
    }

    #[test]
    fn stream_state_text_delta() {
        let mut s = AnthropicStreamState::default();
        // Simulate content_block_start for text
        s.process(
            Some("content_block_start"),
            r#"{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}"#,
        );
        let evt = s.process(
            Some("content_block_delta"),
            r#"{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}"#,
        );
        assert!(matches!(evt, Some(StreamEvent::TextDelta(ref t)) if t == "Hello"), "got: {evt:?}");
    }

    #[test]
    fn stream_state_tool_call_assembled_from_fragments() {
        let mut s = AnthropicStreamState::default();
        // Start tool block
        s.process(
            Some("content_block_start"),
            r#"{"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"tc_1","name":"read","input":{}}}"#,
        );
        // First fragment
        s.process(
            Some("content_block_delta"),
            r#"{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"path\":"}}"#,
        );
        // Second fragment
        s.process(
            Some("content_block_delta"),
            r#"{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"\"src/main.rs\"}"}}"#,
        );
        // Stop → emit ToolCall
        let evt = s.process(
            Some("content_block_stop"),
            r#"{"type":"content_block_stop","index":1}"#,
        );
        match evt {
            Some(StreamEvent::ToolCall { id, name, arguments }) => {
                assert_eq!(id, "tc_1");
                assert_eq!(name, "read");
                assert_eq!(arguments["path"], "src/main.rs");
            }
            other => panic!("expected ToolCall, got: {other:?}"),
        }
    }

    #[test]
    fn stream_state_message_stop_emits_done() {
        let mut s = AnthropicStreamState::default();
        let evt = s.process(Some("message_stop"), r#"{"type":"message_stop"}"#);
        assert!(matches!(evt, Some(StreamEvent::Done { .. })));
    }
}
