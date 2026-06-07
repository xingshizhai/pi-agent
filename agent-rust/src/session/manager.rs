use std::path::PathBuf;
use anyhow::Result;
use chrono::Utc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use uuid::Uuid;

use crate::session::types::{LoadedSession, SessionEntry, SessionHeader, SessionMeta};
use crate::ai::types::Message;

pub struct SessionManager {
    dir: PathBuf,
}

impl SessionManager {
    pub fn new(dir: PathBuf) -> Self {
        Self { dir }
    }

    /// Default session directory: ~/.pi/sessions
    pub fn default_dir() -> PathBuf {
        dirs::home_dir()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(".pi")
            .join("sessions")
    }

    fn session_path(&self, id: &str) -> PathBuf {
        self.dir.join(format!("{id}.pi"))
    }

    /// Create a new session file with the header as the first line.
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
            .create(true)
            .append(true)
            .open(self.session_path(&header.id))
            .await?;
        let line = format!("{}\n", serde_json::to_string(&header)?);
        file.write_all(line.as_bytes()).await?;
        Ok(header)
    }

    /// Append one entry (one JSON line) to an existing session file.
    pub async fn append_entry(&self, session_id: &str, entry: &SessionEntry) -> Result<()> {
        let mut file = tokio::fs::OpenOptions::new()
            .append(true)
            .open(self.session_path(session_id))
            .await?;
        let line = format!("{}\n", serde_json::to_string(entry)?);
        file.write_all(line.as_bytes()).await?;
        Ok(())
    }

    /// Load a session file and reconstruct the message history.
    ///
    /// If a Compaction entry exists, only messages from firstKeptEntryId onwards are returned.
    pub async fn load(&self, id: &str) -> Result<LoadedSession> {
        let file = tokio::fs::File::open(self.session_path(id)).await?;
        let mut lines = BufReader::new(file).lines();

        // First line must be the header
        let first = lines
            .next_line()
            .await?
            .ok_or_else(|| anyhow::anyhow!("session file is empty"))?;
        let header: SessionHeader = serde_json::from_str(&first)
            .map_err(|e| anyhow::anyhow!("bad session header: {e}: {first}"))?;

        // Read all remaining entries
        let mut entries: Vec<SessionEntry> = Vec::new();
        while let Ok(Some(line)) = lines.next_line().await {
            let line = line.trim();
            if line.is_empty() { continue; }
            if let Ok(entry) = serde_json::from_str::<SessionEntry>(line) {
                entries.push(entry);
            }
        }

        // Find the last Compaction to determine the oldest message to include
        let first_kept_id: Option<String> = entries.iter().rev().find_map(|e| {
            if let SessionEntry::Compaction { first_kept_entry_id, .. } = e {
                Some(first_kept_entry_id.clone())
            } else {
                None
            }
        });

        let messages: Vec<Message> = if let Some(fkid) = first_kept_id {
            // Find the position of firstKeptEntryId and start from there
            let start = entries.iter().position(|e| {
                if let SessionEntry::Message { id, .. } = e {
                    id == &fkid
                } else {
                    false
                }
            }).unwrap_or(0);
            entries[start..].iter().filter_map(|e| {
                if let SessionEntry::Message { message, .. } = e {
                    Some(message.clone())
                } else {
                    None
                }
            }).collect()
        } else {
            entries.iter().filter_map(|e| {
                if let SessionEntry::Message { message, .. } = e {
                    Some(message.clone())
                } else {
                    None
                }
            }).collect()
        };

        Ok(LoadedSession { header, messages })
    }

    /// List all sessions in the directory.
    pub async fn list(&self) -> Result<Vec<SessionMeta>> {
        if !self.dir.exists() {
            return Ok(vec![]);
        }
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

    /// Delete a session file.
    pub async fn delete(&self, id: &str) -> Result<()> {
        tokio::fs::remove_file(self.session_path(id)).await?;
        Ok(())
    }
}
