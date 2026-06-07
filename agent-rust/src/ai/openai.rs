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
                    if let MessageContent::ToolResult { tool_call_id, content, is_error: _, tool_name: _ } = c {
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
                let role = match msg.role {
                    Role::User => "user",
                    Role::Assistant => "assistant",
                    _ => unreachable!(),
                };
                let content: Vec<Value> = msg.content.iter().filter_map(|c| match c {
                    MessageContent::Text { text } => Some(json!({"type": "text", "text": text})),
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
            let mut tool_map: std::collections::HashMap<u64, (String, String, String)> = std::collections::HashMap::new();

            while let Some(chunk) = byte_stream.next().await {
                match chunk {
                    Ok(bytes) => {
                        let text = String::from_utf8_lossy(&bytes);
                        for (_evt, data) in parser.push(&text) {
                            let v: Value = match serde_json::from_str(&data) {
                                Ok(v) => v,
                                Err(_) => continue,
                            };

                            if let Some(choices) = v["choices"].as_array() {
                                for choice in choices {
                                    let delta = &choice["delta"];
                                    if let Some(content) = delta["content"].as_str() {
                                        if !content.is_empty() {
                                            if tx.send(StreamEvent::TextDelta(content.to_string())).await.is_err() {
                                                return;
                                            }
                                        }
                                    }
                                    if let Some(tcs) = delta["tool_calls"].as_array() {
                                        for tc in tcs {
                                            let idx = tc["index"].as_u64().unwrap_or(0);
                                            let entry = tool_map.entry(idx).or_insert_with(|| (String::new(), String::new(), String::new()));
                                            if let Some(id) = tc["id"].as_str() { entry.0 = id.to_string(); }
                                            if let Some(name) = tc["function"]["name"].as_str() { entry.1 = name.to_string(); }
                                            if let Some(args) = tc["function"]["arguments"].as_str() { entry.2.push_str(args); }
                                        }
                                    }
                                    if let Some(reason) = choice["finish_reason"].as_str() {
                                        if reason == "tool_calls" {
                                            for (_, (id, name, args_str)) in tool_map.drain() {
                                                let arguments = serde_json::from_str(&args_str)
                                                    .unwrap_or(Value::Object(Default::default()));
                                                if tx.send(StreamEvent::ToolCall { id, name, arguments }).await.is_err() {
                                                    return;
                                                }
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
