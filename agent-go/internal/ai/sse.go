package ai

import (
	"bufio"
	"io"
	"strings"
)

// SSEEvent represents a single Server-Sent Event.
type SSEEvent struct {
	Event string
	Data  string
}

// ParseSSE reads an SSE stream from r and sends events on the returned channel.
// The channel is closed when r is exhausted or returns an error.
// Each event with a non-empty Data field is sent; comment lines (":") are skipped.
func ParseSSE(r io.Reader) <-chan SSEEvent {
	ch := make(chan SSEEvent, 32)
	go func() {
		defer close(ch)
		scanner := bufio.NewScanner(r)
		// Allow large lines (tool call arguments can be large).
		buf := make([]byte, 0, 64*1024)
		scanner.Buffer(buf, 512*1024)

		var event, data strings.Builder
		for scanner.Scan() {
			line := scanner.Text()

			if line == "" {
				// Blank line = dispatch event.
				d := strings.TrimSpace(data.String())
				if d != "" {
					ch <- SSEEvent{Event: strings.TrimSpace(event.String()), Data: d}
				}
				event.Reset()
				data.Reset()
				continue
			}

			if strings.HasPrefix(line, ":") {
				// Comment line – ignore.
				continue
			}

			if strings.HasPrefix(line, "event:") {
				event.Reset()
				event.WriteString(strings.TrimSpace(strings.TrimPrefix(line, "event:")))
				continue
			}

			if strings.HasPrefix(line, "data:") {
				if data.Len() > 0 {
					data.WriteByte('\n')
				}
				data.WriteString(strings.TrimPrefix(line, "data:"))
				// Trim single leading space per SSE spec.
				if data.Len() > 0 {
					s := data.String()
					if s[0] == ' ' {
						data.Reset()
						data.WriteString(s[1:])
					}
				}
			}
		}
		// Flush final event if stream ends without trailing blank line.
		if d := strings.TrimSpace(data.String()); d != "" {
			ch <- SSEEvent{Event: strings.TrimSpace(event.String()), Data: d}
		}
	}()
	return ch
}
