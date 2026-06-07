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

// ---------- edit tests ----------

mod edit_tests {
    use super::*;
    use pi_agent::tools::edit::EditTool;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[tokio::test]
    async fn edit_replaces_text() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "hello world\nfoo bar\n").unwrap();
        let path = f.path().to_str().unwrap().to_string();

        let result = EditTool.execute("id", serde_json::json!({
            "path": path.clone(),
            "edits": [{"oldText": "hello world", "newText": "goodbye world"}]
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error, "got error: {}", result.content);
        let updated = std::fs::read_to_string(&path).unwrap();
        assert!(updated.contains("goodbye world"), "updated: {updated}");
        assert!(!updated.contains("hello world"), "should have replaced: {updated}");
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

        assert!(result.is_error, "should have failed");
        assert!(result.content.contains("2 times"), "msg: {}", result.content);
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
        assert!(result.content.contains("not found"), "msg: {}", result.content);
    }

    #[tokio::test]
    async fn edit_multiple_edits_applied() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "alpha\nbeta\ngamma\n").unwrap();
        let path = f.path().to_str().unwrap().to_string();

        let result = EditTool.execute("id", serde_json::json!({
            "path": path.clone(),
            "edits": [
                {"oldText": "alpha", "newText": "ALPHA"},
                {"oldText": "gamma", "newText": "GAMMA"}
            ]
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error, "error: {}", result.content);
        let updated = std::fs::read_to_string(&path).unwrap();
        assert!(updated.contains("ALPHA"), "updated: {updated}");
        assert!(updated.contains("GAMMA"), "updated: {updated}");
        assert!(updated.contains("beta"),  "beta should remain: {updated}");
        assert!(!updated.contains("alpha"), "alpha replaced: {updated}");
        assert!(!updated.contains("gamma"), "gamma replaced: {updated}");
    }

    #[tokio::test]
    async fn edit_empty_edits_is_error() {
        let mut f = NamedTempFile::new().unwrap();
        write!(f, "content\n").unwrap();
        let path = f.path().to_str().unwrap().to_string();

        let result = EditTool.execute("id", serde_json::json!({
            "path": path,
            "edits": []
        }), CancellationToken::new(), None).await;

        assert!(result.is_error);
    }
}

// ---------- bash tests ----------

mod bash_tests {
    use super::*;
    use pi_agent::tools::bash::BashTool;

    #[tokio::test]
    async fn bash_runs_simple_command() {
        let result = BashTool.execute(
            "id",
            serde_json::json!({"command": "echo hello"}),
            CancellationToken::new(),
            None,
        ).await;
        assert!(!result.is_error, "error: {}", result.content);
        assert!(result.content.trim().ends_with("hello"), "content: {}", result.content);
    }

    #[tokio::test]
    async fn bash_captures_stderr() {
        let result = BashTool.execute(
            "id",
            serde_json::json!({"command": "echo err_output >&2"}),
            CancellationToken::new(),
            None,
        ).await;
        assert!(!result.is_error, "error: {}", result.content);
        assert!(result.content.contains("err_output"), "content: {}", result.content);
    }

    #[tokio::test]
    async fn bash_nonzero_exit_is_error() {
        let result = BashTool.execute(
            "id",
            serde_json::json!({"command": "exit 1"}),
            CancellationToken::new(),
            None,
        ).await;
        assert!(result.is_error, "should be error for exit 1");
    }

    #[tokio::test]
    async fn bash_timeout_kills_process() {
        let start = std::time::Instant::now();
        let result = BashTool.execute(
            "id",
            serde_json::json!({"command": "sleep 30", "timeout": 0.3}),
            CancellationToken::new(),
            None,
        ).await;
        let elapsed = start.elapsed().as_secs_f64();
        assert!(elapsed < 5.0, "should timeout quickly, took {elapsed}s");
        assert!(result.is_error, "should be error on timeout");
        assert!(result.content.contains("timed out"), "msg: {}", result.content);
    }

    #[tokio::test]
    async fn bash_cancellation_stops_process() {
        let cancel = CancellationToken::new();
        let cancel2 = cancel.clone();

        // Cancel after a short delay
        tokio::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
            cancel2.cancel();
        });

        let start = std::time::Instant::now();
        let result = BashTool.execute(
            "id",
            serde_json::json!({"command": "sleep 30"}),
            cancel,
            None,
        ).await;
        let elapsed = start.elapsed().as_secs_f64();
        assert!(elapsed < 5.0, "should cancel quickly, took {elapsed}s");
        assert!(result.is_error, "should be error on cancel");
    }
}

// ---------- find tests ----------

mod find_tests {
    use super::*;
    use pi_agent::tools::find::FindTool;
    use tempfile::TempDir;
    use std::fs;

    #[tokio::test]
    async fn find_matches_files_by_glob() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("foo.rs"), "").unwrap();
        fs::write(dir.path().join("bar.txt"), "").unwrap();

        let result = FindTool.execute("id", serde_json::json!({
            "path": dir.path().to_str().unwrap(),
            "pattern": "*.rs"
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error);
        assert!(result.content.contains("foo.rs"), "content: {}", result.content);
        assert!(!result.content.contains("bar.txt"), "content: {}", result.content);
    }

    #[tokio::test]
    async fn find_no_matches_returns_message() {
        let dir = TempDir::new().unwrap();
        let result = FindTool.execute("id", serde_json::json!({
            "path": dir.path().to_str().unwrap(),
            "pattern": "*.xyz"
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error);
        assert!(result.content.contains("no matches"), "content: {}", result.content);
    }
}

// ---------- grep tests ----------

mod grep_tests {
    use super::*;
    use pi_agent::tools::grep::GrepTool;
    use std::io::Write;
    use tempfile::NamedTempFile;

    #[tokio::test]
    async fn grep_finds_pattern() {
        let mut f = NamedTempFile::new().unwrap();
        writeln!(f, "hello world").unwrap();
        writeln!(f, "foo bar").unwrap();
        writeln!(f, "hello again").unwrap();

        let result = GrepTool.execute("id", serde_json::json!({
            "path": f.path().to_str().unwrap(),
            "pattern": "hello"
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error);
        let lines: Vec<&str> = result.content.lines().collect();
        assert_eq!(lines.len(), 2, "content: {}", result.content);
        assert!(result.content.contains("hello world"), "content: {}", result.content);
        assert!(result.content.contains("hello again"), "content: {}", result.content);
    }

    #[tokio::test]
    async fn grep_case_insensitive() {
        let mut f = NamedTempFile::new().unwrap();
        writeln!(f, "Hello World").unwrap();

        let result = GrepTool.execute("id", serde_json::json!({
            "path": f.path().to_str().unwrap(),
            "pattern": "hello",
            "ignore_case": true
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error);
        assert!(result.content.contains("Hello World"), "content: {}", result.content);
    }
}

// ---------- ls tests ----------

mod ls_tests {
    use super::*;
    use pi_agent::tools::ls::LsTool;
    use tempfile::TempDir;
    use std::fs;

    #[tokio::test]
    async fn ls_lists_entries() {
        let dir = TempDir::new().unwrap();
        fs::write(dir.path().join("file.txt"), "hello").unwrap();
        fs::create_dir(dir.path().join("subdir")).unwrap();

        let result = LsTool.execute("id", serde_json::json!({
            "path": dir.path().to_str().unwrap()
        }), CancellationToken::new(), None).await;

        assert!(!result.is_error, "error: {}", result.content);
        assert!(result.content.contains("file.txt"), "content: {}", result.content);
        assert!(result.content.contains("subdir"),   "content: {}", result.content);
        assert!(result.content.contains("dir"),      "should show type: {}", result.content);
        assert!(result.content.contains("file"),     "should show type: {}", result.content);
    }

    #[tokio::test]
    async fn ls_nonexistent_is_error() {
        let result = LsTool.execute("id", serde_json::json!({
            "path": "/no/such/dir"
        }), CancellationToken::new(), None).await;
        assert!(result.is_error);
    }
}
