package session

import "github.com/pi-agent/agent-go/internal/ai"

// Header is the first line of every .pi session file.
type Header struct {
	Type      string `json:"type"`      // always "session"
	Version   int    `json:"version"`   // 3
	ID        string `json:"id"`
	Timestamp string `json:"timestamp"` // RFC3339
	CWD       string `json:"cwd"`
}

// EntryBase holds fields common to all session entries.
type EntryBase struct {
	Type      string  `json:"type"`
	ID        string  `json:"id"`
	ParentID  *string `json:"parentId"`
	Timestamp string  `json:"timestamp"`
}

// MessageEntry wraps an ai.Message as a session entry.
type MessageEntry struct {
	EntryBase
	Message ai.Message `json:"message"`
}

// ModelChangeEntry records a model switch.
type ModelChangeEntry struct {
	EntryBase
	Provider string `json:"provider"`
	ModelID  string `json:"modelId"`
}

// CompactionEntry records a compaction operation.
type CompactionEntry struct {
	EntryBase
	Summary          string `json:"summary"`
	FirstKeptEntryID string `json:"firstKeptEntryId"`
	TokensBefore     int    `json:"tokensBefore"`
}

// LoadedSession is the reconstructed session state after loading a .pi file.
type LoadedSession struct {
	Header   Header
	Messages []ai.Message
	ModelID  string
	Provider string
}

// Meta is a lightweight summary for listing sessions.
type Meta struct {
	ID        string
	Timestamp string
	CWD       string
	Title     string // first 60 chars of first user message
}
