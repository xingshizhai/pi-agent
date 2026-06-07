package ai

import "context"

// StreamOptions configures a single LLM stream call.
type StreamOptions struct {
	APIKey    string
	MaxTokens int // 0 = use provider default (8192)
}

// Provider is the interface every LLM backend must implement.
type Provider interface {
	// Stream sends the context to the LLM and returns a channel of StreamEvents.
	// The channel is closed after a Done or Error event.
	// Callers must drain the channel even on cancellation.
	Stream(ctx context.Context, llmCtx Context, opts StreamOptions) (<-chan StreamEvent, error)
}
