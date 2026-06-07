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
    pub schema: serde_json::Value,
}

#[derive(Debug, Clone)]
pub struct StreamOptions {
    pub api_key: String,
    pub max_tokens: u32,
}

impl Default for StreamOptions {
    fn default() -> Self {
        Self {
            api_key: String::new(),
            max_tokens: 8192,
        }
    }
}

/// Events emitted by a provider's streaming response, sent over mpsc channel.
#[derive(Debug)]
pub enum StreamEvent {
    TextDelta(String),
    ToolCall {
        id: String,
        name: String,
        arguments: serde_json::Value,
    },
    Done {
        stop_reason: String,
    },
    Error(anyhow::Error),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_text_content() {
        let c = MessageContent::Text { text: "hello".into() };
        let json = serde_json::to_string(&c).unwrap();
        assert!(json.contains(r#""type":"text""#), "json: {json}");
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
        assert!(json.contains(r#""type":"tool_call""#), "json: {json}");
        let back: MessageContent = serde_json::from_str(&json).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn roundtrip_tool_result() {
        let c = MessageContent::ToolResult {
            tool_call_id: "c1".into(),
            tool_name: "read".into(),
            content: "file contents".into(),
            is_error: false,
        };
        let json = serde_json::to_string(&c).unwrap();
        assert!(json.contains(r#""type":"tool_result""#), "json: {json}");
        let back: MessageContent = serde_json::from_str(&json).unwrap();
        assert_eq!(c, back);
    }

    #[test]
    fn role_serializes_snake_case() {
        assert_eq!(
            serde_json::to_string(&Role::ToolResult).unwrap(),
            r#""tool_result""#
        );
        assert_eq!(
            serde_json::to_string(&Role::User).unwrap(),
            r#""user""#
        );
    }

    #[test]
    fn message_roundtrip() {
        let msg = Message {
            role: Role::User,
            content: vec![MessageContent::Text { text: "hello".into() }],
            timestamp: 1234567890,
        };
        let json = serde_json::to_string(&msg).unwrap();
        let back: Message = serde_json::from_str(&json).unwrap();
        assert_eq!(back.role, Role::User);
        assert_eq!(back.timestamp, 1234567890);
    }
}
