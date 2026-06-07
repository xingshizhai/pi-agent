package session

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/pi-agent/agent-go/internal/ai"
)

// Manager handles reading and writing session files (.pi NDJSON format).
type Manager struct {
	dir string
}

// New creates a Manager rooted at dir. If dir is empty, ~/.pi/sessions is used.
func New(dir string) (*Manager, error) {
	if dir == "" {
		home, err := os.UserHomeDir()
		if err != nil {
			return nil, err
		}
		dir = filepath.Join(home, ".pi", "sessions")
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, err
	}
	return &Manager{dir: dir}, nil
}

func (m *Manager) sessionPath(id string) string {
	return filepath.Join(m.dir, id+".pi")
}

// NewSession creates a new session file and returns its Header.
func (m *Manager) NewSession(cwd string) (*Header, error) {
	id := newID()
	hdr := Header{
		Type:      "session",
		Version:   3,
		ID:        id,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
		CWD:       cwd,
	}
	f, err := os.OpenFile(m.sessionPath(id), os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	if err := enc.Encode(hdr); err != nil {
		return nil, err
	}
	return &hdr, nil
}

// AppendMessage appends a message entry to a session file.
func (m *Manager) AppendMessage(sessionID string, prevID *string, msg ai.Message) (string, error) {
	id := newID()
	entry := MessageEntry{
		EntryBase: EntryBase{
			Type:      "message",
			ID:        id,
			ParentID:  prevID,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
		},
		Message: msg,
	}
	return id, m.appendEntry(sessionID, entry)
}

// AppendModelChange appends a model change entry.
func (m *Manager) AppendModelChange(sessionID string, prevID *string, provider, modelID string) (string, error) {
	id := newID()
	entry := ModelChangeEntry{
		EntryBase: EntryBase{
			Type:      "model_change",
			ID:        id,
			ParentID:  prevID,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
		},
		Provider: provider,
		ModelID:  modelID,
	}
	return id, m.appendEntry(sessionID, entry)
}

func (m *Manager) appendEntry(sessionID string, entry any) error {
	f, err := os.OpenFile(m.sessionPath(sessionID), os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return fmt.Errorf("session: open %s: %w", sessionID, err)
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	return enc.Encode(entry)
}

// Load reads a session file and reconstructs the message history.
func (m *Manager) Load(id string) (*LoadedSession, error) {
	f, err := os.Open(m.sessionPath(id))
	if err != nil {
		return nil, fmt.Errorf("session: load %s: %w", id, err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 64*1024), 4*1024*1024)

	// First line: header.
	if !scanner.Scan() {
		return nil, fmt.Errorf("session: empty file %s", id)
	}
	var hdr Header
	if err := json.Unmarshal(scanner.Bytes(), &hdr); err != nil {
		return nil, fmt.Errorf("session: parse header: %w", err)
	}

	loaded := &LoadedSession{Header: hdr}

	// Find last compaction to determine which messages to skip.
	// We do a two-pass approach: collect all entries, then apply compaction.
	type rawEntry struct {
		entryType string
		raw       []byte
	}
	var entries []rawEntry

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}
		var base struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(line, &base); err != nil {
			continue
		}
		cp := make([]byte, len(line))
		copy(cp, line)
		entries = append(entries, rawEntry{entryType: base.Type, raw: cp})
	}

	// Find the last compaction entry.
	lastCompactionIdx := -1
	var lastCompaction CompactionEntry
	for i, e := range entries {
		if e.entryType == "compaction" {
			if err := json.Unmarshal(e.raw, &lastCompaction); err == nil {
				lastCompactionIdx = i
			}
		}
	}

	// Build message list from relevant entries.
	skipUntilID := ""
	if lastCompactionIdx >= 0 {
		skipUntilID = lastCompaction.FirstKeptEntryID
		// Inject compaction summary as a synthetic user message.
		loaded.Messages = append(loaded.Messages, ai.Message{
			Role:      ai.RoleUser,
			Content:   []ai.ContentBlock{ai.NewTextBlock("[Previous context summary]\n" + lastCompaction.Summary)},
			Timestamp: 0,
		})
	}

	skipping := skipUntilID != ""
	for _, e := range entries {
		switch e.entryType {
		case "message":
			var me MessageEntry
			if err := json.Unmarshal(e.raw, &me); err != nil {
				continue
			}
			if skipping {
				if me.ID == skipUntilID {
					skipping = false
				} else {
					continue
				}
			}
			loaded.Messages = append(loaded.Messages, me.Message)

		case "model_change":
			var mc ModelChangeEntry
			if err := json.Unmarshal(e.raw, &mc); err == nil {
				loaded.Provider = mc.Provider
				loaded.ModelID = mc.ModelID
			}
		}
	}

	return loaded, nil
}

// List returns metadata for all sessions, sorted by most recent first.
func (m *Manager) List() ([]Meta, error) {
	entries, err := os.ReadDir(m.dir)
	if err != nil {
		return nil, err
	}
	var metas []Meta
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".pi") {
			continue
		}
		id := strings.TrimSuffix(e.Name(), ".pi")
		meta, err := m.loadMeta(id)
		if err != nil {
			continue
		}
		metas = append(metas, meta)
	}
	sort.Slice(metas, func(i, j int) bool {
		return metas[i].Timestamp > metas[j].Timestamp
	})
	return metas, nil
}

func (m *Manager) loadMeta(id string) (Meta, error) {
	f, err := os.Open(m.sessionPath(id))
	if err != nil {
		return Meta{}, err
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 4096), 65536)
	if !scanner.Scan() {
		return Meta{}, fmt.Errorf("empty")
	}
	var hdr Header
	if err := json.Unmarshal(scanner.Bytes(), &hdr); err != nil {
		return Meta{}, err
	}

	// Find first user message for title.
	title := ""
	for scanner.Scan() && title == "" {
		var base struct {
			Type    string     `json:"type"`
			Message ai.Message `json:"message"`
		}
		if err := json.Unmarshal(scanner.Bytes(), &base); err != nil {
			continue
		}
		if base.Type == "message" && base.Message.Role == ai.RoleUser {
			for _, c := range base.Message.Content {
				if t, ok := c.AsText(); ok && t.Text != "" {
					r := []rune(t.Text)
					if len(r) > 60 {
						r = r[:60]
					}
					title = string(r)
					break
				}
			}
		}
	}

	return Meta{ID: id, Timestamp: hdr.Timestamp, CWD: hdr.CWD, Title: title}, nil
}

// Delete removes a session file.
func (m *Manager) Delete(id string) error {
	return os.Remove(m.sessionPath(id))
}

// newID returns a time-sortable pseudo-UUID (timestamp-based).
func newID() string {
	return fmt.Sprintf("%016x", time.Now().UnixNano())
}
