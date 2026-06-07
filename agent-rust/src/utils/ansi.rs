/// Strip ANSI escape codes from a string (color codes, cursor moves, etc.)
pub fn strip_ansi(s: &str) -> String {
    let mut result = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c == '\x1b' {
            if chars.peek() == Some(&'[') {
                chars.next(); // consume '['
                // consume until a letter (the command character)
                for c2 in chars.by_ref() {
                    if c2.is_ascii_alphabetic() {
                        break;
                    }
                }
            }
            // if not '[', just skip the ESC character
        } else {
            result.push(c);
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_color_codes() {
        assert_eq!(strip_ansi("\x1b[31mhello\x1b[0m"), "hello");
    }

    #[test]
    fn strips_cursor_moves() {
        assert_eq!(strip_ansi("\x1b[2Jhello"), "hello");
    }

    #[test]
    fn passthrough_plain() {
        assert_eq!(strip_ansi("hello world"), "hello world");
    }

    #[test]
    fn strips_bold() {
        assert_eq!(strip_ansi("\x1b[1mbold\x1b[0m"), "bold");
    }

    #[test]
    fn empty_string() {
        assert_eq!(strip_ansi(""), "");
    }
}
