use pi_agent::session::manager::SessionManager;
use pi_agent::session::types::SessionEntry;
use pi_agent::ai::types::{Message, MessageContent, Role};
use tempfile::TempDir;
use uuid::Uuid;
use chrono::Utc;

#[tokio::test]
async fn create_and_list_session() {
    let dir = TempDir::new().unwrap();
    let mgr = SessionManager::new(dir.path().to_path_buf());

    let header = mgr.new_session("/tmp/project").await.unwrap();
    assert_eq!(header.version, 3);
    assert_eq!(header.kind, "session");
    assert_eq!(header.cwd, "/tmp/project");

    let sessions = mgr.list().await.unwrap();
    assert_eq!(sessions.len(), 1);
    assert_eq!(sessions[0].id, header.id);
}

#[tokio::test]
async fn append_and_load_messages() {
    let dir = TempDir::new().unwrap();
    let mgr = SessionManager::new(dir.path().to_path_buf());

    let header = mgr.new_session("/tmp").await.unwrap();

    let msg = Message {
        role: Role::User,
        content: vec![MessageContent::Text { text: "hello".into() }],
        timestamp: 0,
    };

    let entry = SessionEntry::Message {
        id: Uuid::new_v4().to_string(),
        parent_id: None,
        timestamp: Utc::now().to_rfc3339(),
        message: msg.clone(),
    };

    mgr.append_entry(&header.id, &entry).await.unwrap();

    let loaded = mgr.load(&header.id).await.unwrap();
    assert_eq!(loaded.messages.len(), 1);
    assert_eq!(loaded.header.id, header.id);
    // Check the message content was preserved
    if let MessageContent::Text { text } = &loaded.messages[0].content[0] {
        assert_eq!(text, "hello");
    } else {
        panic!("expected Text content");
    }
}

#[tokio::test]
async fn delete_removes_session() {
    let dir = TempDir::new().unwrap();
    let mgr = SessionManager::new(dir.path().to_path_buf());

    let header = mgr.new_session("/tmp").await.unwrap();
    assert_eq!(mgr.list().await.unwrap().len(), 1);

    mgr.delete(&header.id).await.unwrap();
    assert_eq!(mgr.list().await.unwrap().len(), 0);
}

#[tokio::test]
async fn multiple_sessions_listed() {
    let dir = TempDir::new().unwrap();
    let mgr = SessionManager::new(dir.path().to_path_buf());

    mgr.new_session("/a").await.unwrap();
    mgr.new_session("/b").await.unwrap();
    mgr.new_session("/c").await.unwrap();

    let sessions = mgr.list().await.unwrap();
    assert_eq!(sessions.len(), 3);
}
