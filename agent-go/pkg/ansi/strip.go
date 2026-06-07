package ansi

import "regexp"

var ansiEscape = regexp.MustCompile(`\x1b\[[0-9;]*[mGKHFABCDEFJns]|\x1b\][^\x07]*\x07|\x1b[()][AB012]|\x1b[=>]|\r`)

// Strip removes ANSI escape sequences and carriage returns from s.
func Strip(s string) string {
	return ansiEscape.ReplaceAllString(s, "")
}
