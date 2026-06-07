package headless

import (
	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/ai/anthropic"
	openaiProvider "github.com/pi-agent/agent-go/internal/ai/openai"
)

func buildRealProvider(providerName, _ string) ai.Provider {
	if providerName == "openai" {
		return openaiProvider.New()
	}
	return anthropic.New()
}
