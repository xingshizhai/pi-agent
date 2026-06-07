package tui

import "github.com/pi-agent/agent-go/internal/ai"

// providerFactory is set by the application to construct providers.
var providerFactory func(provider, apiKey string) ai.Provider

// SetProviderFactory registers the function used to build AI providers.
// Must be called before Run.
func SetProviderFactory(f func(provider, apiKey string) ai.Provider) {
	providerFactory = f
}
