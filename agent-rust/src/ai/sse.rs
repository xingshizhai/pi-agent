/// Stateful SSE chunk parser.
/// Feed raw bytes from the HTTP response; get back (event_type, data) pairs.
/// Handles partial chunks that split across event boundaries.
pub struct SseParser {
    buffer: String,
}

impl Default for SseParser {
    fn default() -> Self {
        Self { buffer: String::new() }
    }
}

impl SseParser {
    pub fn new() -> Self {
        Self::default()
    }

    /// Push a raw text chunk; returns any complete (event_type, data) pairs.
    /// Filters out data == "[DONE]" (OpenAI stream-end sentinel).
    pub fn push(&mut self, chunk: &str) -> Vec<(Option<String>, String)> {
        self.buffer.push_str(chunk);
        let mut events = Vec::new();

        loop {
            match self.buffer.find("\n\n") {
                None => break,
                Some(pos) => {
                    let block = self.buffer[..pos].to_string();
                    self.buffer = self.buffer[pos + 2..].to_string();

                    let mut event_type: Option<String> = None;
                    let mut data = String::new();

                    for line in block.lines() {
                        if let Some(val) = line.strip_prefix("event: ") {
                            event_type = Some(val.trim().to_string());
                        } else if let Some(val) = line.strip_prefix("data: ") {
                            data = val.to_string();
                        }
                    }

                    if !data.is_empty() && data != "[DONE]" {
                        events.push((event_type, data));
                    }
                }
            }
        }
        events
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_single_event() {
        let mut p = SseParser::new();
        let events = p.push("event: ping\ndata: {\"type\":\"ping\"}\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].0.as_deref(), Some("ping"));
        assert_eq!(events[0].1, r#"{"type":"ping"}"#);
    }

    #[test]
    fn handles_split_chunks() {
        let mut p = SseParser::new();
        let e1 = p.push("event: text\ndat");
        assert!(e1.is_empty(), "no complete event yet");
        let e2 = p.push("a: hello\n\n");
        assert_eq!(e2.len(), 1);
        assert_eq!(e2[0].1, "hello");
    }

    #[test]
    fn filters_done_sentinel() {
        let mut p = SseParser::new();
        let events = p.push("data: [DONE]\n\n");
        assert!(events.is_empty(), "should filter [DONE]");
    }

    #[test]
    fn multiple_events_in_one_chunk() {
        let mut p = SseParser::new();
        let chunk = "event: a\ndata: 1\n\nevent: b\ndata: 2\n\n";
        let events = p.push(chunk);
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].1, "1");
        assert_eq!(events[1].1, "2");
    }

    #[test]
    fn no_event_type_is_none() {
        let mut p = SseParser::new();
        let events = p.push("data: just data\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].0, None);
        assert_eq!(events[0].1, "just data");
    }

    #[test]
    fn empty_data_block_ignored() {
        let mut p = SseParser::new();
        let events = p.push("event: ping\n\n");
        assert!(events.is_empty(), "block with no data line should be ignored");
    }

    #[test]
    fn state_persists_across_pushes() {
        let mut p = SseParser::new();
        p.push("event: foo\ndata: par");
        let events = p.push("tial\n\n");
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].1, "partial");
    }
}
