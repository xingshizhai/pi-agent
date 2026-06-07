use async_trait::async_trait;
use std::collections::HashMap;
use std::sync::Arc;
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

/// Build the registry of all built-in tools.
pub fn all_tools() -> HashMap<String, Arc<dyn Tool>> {
    let mut map: HashMap<String, Arc<dyn Tool>> = HashMap::new();
    map.insert("read".into(),  Arc::new(read::ReadTool));
    map.insert("write".into(), Arc::new(write::WriteTool));
    map.insert("edit".into(),  Arc::new(edit::EditTool));
    map.insert("bash".into(),  Arc::new(bash::BashTool));
    map.insert("find".into(),  Arc::new(find::FindTool));
    map.insert("grep".into(),  Arc::new(grep::GrepTool));
    map.insert("ls".into(),    Arc::new(ls::LsTool));
    map
}
