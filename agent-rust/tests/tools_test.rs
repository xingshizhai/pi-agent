use pi_agent::tools::Tool;
use tokio_util::sync::CancellationToken;

// ---------- read tests ----------

mod read_tests {
    use super::*;
    use pi_agent::tools::read::ReadTool;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[tokio::test]
    async fn read_returns_numbered_lines() {
        let mut f = NamedTempFile::new().unwrap();
        writeln!(f, "line one").unwrap();
        writeln!(f, "line two").unwrap();
        let path = f.path().to_str().unwrap().to_string();

        let result = ReadTool.execute("id", serde_json::json!({"path": path}), CancellationToken::new(), None).await;
        assert!(!result.is_error, "unexpected error: {}", result.content);
        assert!(result.content.contains("1\tline one"), "content: {}", result.content);
        assert!(result.content.contains("2\tline two"), "content: {}", result.content);
    }

    #[tokio::test]
    async fn read_with_offset_and_limit() {
        let mut f = NamedTempFile::new().unwrap();
        for i in 1..=10 {
            writeln!(f, "line {i}").unwrap();
        }
        let path = f.path().to_str().unwrap().to_string();

        let result = ReadTool.execute("id", serde_json::json!({"path": path, "offset": 3, "limit": 2}), CancellationToken::new(), None).await;
        assert!(!result.is_error);
        assert!(result.content.contains("3\tline 3"),  "content: {}", result.content);
        assert!(result.content.contains("4\tline 4"),  "content: {}", result.content);
        assert!(!result.content.contains("5\tline 5"), "should not have line 5");
    }

    #[tokio::test]
    async fn read_missing_file_is_error() {
        let result = ReadTool.execute("id", serde_json::json!({"path": "/no/such/file.txt"}), CancellationToken::new(), None).await;
        assert!(result.is_error);
    }

    #[tokio::test]
    async fn read_shows_continuation_hint_when_limited() {
        let mut f = NamedTempFile::new().unwrap();
        for i in 1..=5 {
            writeln!(f, "line {i}").unwrap();
        }
        let path = f.path().to_str().unwrap().to_string();

        let result = ReadTool.execute("id", serde_json::json!({"path": path, "limit": 2}), CancellationToken::new(), None).await;
        assert!(!result.is_error);
        assert!(result.content.contains("Showing lines"), "should have continuation hint: {}", result.content);
        assert!(result.content.contains("offset="), "should have offset hint: {}", result.content);
    }
}

// ---------- write tests ----------

mod write_tests {
    use super::*;
    use pi_agent::tools::write::WriteTool;
    use tempfile::TempDir;

    #[tokio::test]
    async fn write_creates_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.txt").to_str().unwrap().to_string();

        let result = WriteTool.execute("id", serde_json::json!({"path": path.clone(), "content": "hello"}), CancellationToken::new(), None).await;
        assert!(!result.is_error, "error: {}", result.content);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "hello");
    }

    #[tokio::test]
    async fn write_creates_parent_dirs() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("sub/dir/test.txt").to_str().unwrap().to_string();

        let result = WriteTool.execute("id", serde_json::json!({"path": path.clone(), "content": "hi"}), CancellationToken::new(), None).await;
        assert!(!result.is_error, "error: {}", result.content);
        assert_eq!(std::fs::read_to_string(&path).unwrap(), "hi");
    }
}
