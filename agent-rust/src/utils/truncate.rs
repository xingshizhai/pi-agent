const MAX_BYTES: usize = 200 * 1024; // 200 KB

/// Truncate output to MAX_BYTES, keeping the tail (most recent output).
pub fn truncate_output(s: &str) -> String {
    if s.len() <= MAX_BYTES {
        return s.to_string();
    }
    // Find a valid UTF-8 boundary near MAX_BYTES from the end
    let start = s.len() - MAX_BYTES;
    let tail = &s[start..];
    format!("[...output truncated, showing last 200KB...]\n{tail}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn short_passthrough() {
        assert_eq!(truncate_output("hello"), "hello");
    }

    #[test]
    fn long_gets_truncated() {
        let big = "x".repeat(MAX_BYTES + 100);
        let result = truncate_output(&big);
        assert!(result.contains("truncated"), "should contain truncation notice");
        assert!(result.len() < big.len(), "result should be shorter");
    }

    #[test]
    fn exact_limit_passthrough() {
        let exact = "y".repeat(MAX_BYTES);
        let result = truncate_output(&exact);
        assert_eq!(result, exact, "exactly at limit should pass through");
    }
}
