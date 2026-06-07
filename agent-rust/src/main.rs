mod utils;
mod ai;
mod agent;
mod tools;
mod session;
mod tui;
mod headless;

use std::sync::Arc;
use anyhow::Result;
use crossterm::{
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::backend::CrosstermBackend;
use ratatui::Terminal;

use ai::anthropic::AnthropicProvider;
use ai::openai::OpenAIProvider;
use agent::AgentContext;
use session::manager::SessionManager;
use tools::all_tools;

const SYSTEM_PROMPT: &str = "\
You are a coding assistant with access to file system tools. \
Use the read, write, edit, bash, find, grep, and ls tools to help complete programming tasks. \
Be concise, work methodically, and prefer small targeted edits over large rewrites.";

#[tokio::main]
async fn main() -> Result<()> {
    dotenvy::dotenv().ok();

    // Configure tracing to write to a file (not stderr, which would corrupt the TUI)
    let log_file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/pi-agent.log")
        .ok();
    if let Some(file) = log_file {
        tracing_subscriber::fmt()
            .with_writer(std::sync::Mutex::new(file))
            .with_env_filter(
                tracing_subscriber::EnvFilter::from_default_env()
                    .add_directive(tracing::Level::INFO.into()),
            )
            .init();
    }

    // Read config from environment — OpenRouter takes priority over Anthropic
    let (api_key, use_openrouter) =
        if let Ok(k) = std::env::var("OPENROUTER_API_KEY") {
            (k, true)
        } else if let Ok(k) = std::env::var("ANTHROPIC_API_KEY") {
            (k, false)
        } else {
            eprintln!("Error: set OPENROUTER_API_KEY or ANTHROPIC_API_KEY.");
            std::process::exit(1);
        };

    // Headless mode for automated testing
    if std::env::var("PI_HEADLESS").as_deref() == Ok("1") {
        return headless::run(api_key, use_openrouter).await;
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
        .unwrap_or_else(|_| ".".to_string());

    // Create a session
    let session_mgr = Arc::new(SessionManager::new(session_dir));
    let _session_header = session_mgr.new_session(&cwd).await
        .unwrap_or_else(|e| {
            tracing::warn!("could not create session: {e}");
            // Return a dummy header — not fatal
            session::types::SessionHeader {
                kind: "session".into(),
                version: 3,
                id: "local".into(),
                timestamp: String::new(),
                cwd: cwd.clone(),
            }
        });

    // Default model: claude-sonnet-4-6 for Anthropic/OpenRouter, overridable via PI_MODEL
    let default_model = if use_openrouter {
        "anthropic/claude-sonnet-4-5".to_string()
    } else {
        "claude-sonnet-4-6".to_string()
    };
    let model_id = std::env::var("PI_MODEL").unwrap_or(default_model);

    // Build agent context
    let ctx = AgentContext {
        system_prompt: SYSTEM_PROMPT.to_string(),
        messages: Vec::new(),
        tools: all_tools(),
        api_key: api_key.clone(),
        model_id,
    };

    let provider: Arc<dyn ai::provider::Provider> = if use_openrouter {
        Arc::new(OpenAIProvider::with_base_url("https://openrouter.ai/api/v1"))
    } else {
        Arc::new(AnthropicProvider::new())
    };

    // Set up terminal
    enable_raw_mode()?;
    let mut stdout = std::io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    terminal.clear()?;

    // Run TUI — restore terminal on exit (even on error)
    let result = tui::app::run(&mut terminal, ctx, provider, max_turns).await;

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    result
}
