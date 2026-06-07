package tests

import (
	"testing"
	"time"

	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/session"
)

func TestSessionManager_NewAndLoad(t *testing.T) {
	mgr, err := session.New(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}

	hdr, err := mgr.NewSession("/tmp/myproject")
	if err != nil {
		t.Fatal(err)
	}
	if hdr.ID == "" {
		t.Error("expected non-empty session ID")
	}
	if hdr.CWD != "/tmp/myproject" {
		t.Errorf("unexpected cwd: %q", hdr.CWD)
	}

	// Append two messages.
	msg1 := ai.Message{
		Role:      ai.RoleUser,
		Content:   []ai.ContentBlock{ai.NewTextBlock("hello")},
		Timestamp: time.Now().UnixMilli(),
	}
	id1, err := mgr.AppendMessage(hdr.ID, nil, msg1)
	if err != nil {
		t.Fatal(err)
	}

	msg2 := ai.Message{
		Role:      ai.RoleAssistant,
		Content:   []ai.ContentBlock{ai.NewTextBlock("world")},
		Timestamp: time.Now().UnixMilli(),
	}
	_, err = mgr.AppendMessage(hdr.ID, &id1, msg2)
	if err != nil {
		t.Fatal(err)
	}

	// Load and verify.
	loaded, err := mgr.Load(hdr.ID)
	if err != nil {
		t.Fatal(err)
	}
	if len(loaded.Messages) != 2 {
		t.Fatalf("expected 2 messages, got %d", len(loaded.Messages))
	}

	tc0, ok := loaded.Messages[0].Content[0].AsText()
	if !ok || tc0.Text != "hello" {
		t.Errorf("unexpected first message: %v", loaded.Messages[0])
	}
	tc1, ok := loaded.Messages[1].Content[0].AsText()
	if !ok || tc1.Text != "world" {
		t.Errorf("unexpected second message: %v", loaded.Messages[1])
	}
}

func TestSessionManager_List(t *testing.T) {
	mgr, err := session.New(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}

	// Create 3 sessions.
	for i := 0; i < 3; i++ {
		hdr, err := mgr.NewSession("/tmp/proj")
		if err != nil {
			t.Fatal(err)
		}
		msg := ai.Message{
			Role:    ai.RoleUser,
			Content: []ai.ContentBlock{ai.NewTextBlock("message")},
		}
		_, _ = mgr.AppendMessage(hdr.ID, nil, msg)
	}

	metas, err := mgr.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(metas) != 3 {
		t.Errorf("expected 3 sessions, got %d", len(metas))
	}
}

func TestSessionManager_Delete(t *testing.T) {
	mgr, err := session.New(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	hdr, _ := mgr.NewSession("/tmp")
	if err := mgr.Delete(hdr.ID); err != nil {
		t.Fatal(err)
	}
	metas, _ := mgr.List()
	if len(metas) != 0 {
		t.Errorf("expected 0 sessions after delete, got %d", len(metas))
	}
}
