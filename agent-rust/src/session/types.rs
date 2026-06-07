use serde::{Deserialize, Serialize};
use crate::ai::types::Message;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionHeader {
    #[serde(rename = "type")]
    pub kind: String,          // always "session"
    pub version: u32,          // always 3
    pub id: String,
    pub timestamp: String,     // ISO8601
    pub cwd: String,
}

/// One entry per line after the header.
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
