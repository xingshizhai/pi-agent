package agent

import (
	"context"
	"sync"

	"github.com/pi-agent/agent-go/internal/ai"
	"github.com/pi-agent/agent-go/internal/tools"
)

type toolCallRequest struct {
	call ai.ToolCallContent
	tool tools.Tool
}

type toolCallOutcome struct {
	call   ai.ToolCallContent
	result tools.ToolResult
}

func executeTools(
	ctx context.Context,
	calls []ai.ToolCallContent,
	toolMap map[string]tools.Tool,
	mode ToolExecutionMode,
	emit func(AgentEvent),
) []toolCallOutcome {
	requests := make([]toolCallRequest, 0, len(calls))
	for _, call := range calls {
		t, ok := toolMap[call.Name]
		if !ok {
			requests = append(requests, toolCallRequest{call: call, tool: nil})
		} else {
			requests = append(requests, toolCallRequest{call: call, tool: t})
		}
	}

	outcomes := make([]toolCallOutcome, len(requests))

	if mode == ExecutionSequential {
		for i, req := range requests {
			outcomes[i] = runOne(ctx, req, emit)
		}
		return outcomes
	}

	// Parallel execution.
	var wg sync.WaitGroup
	wg.Add(len(requests))
	for i, req := range requests {
		i, req := i, req
		go func() {
			defer wg.Done()
			outcomes[i] = runOne(ctx, req, emit)
		}()
	}
	wg.Wait()
	return outcomes
}

func runOne(ctx context.Context, req toolCallRequest, emit func(AgentEvent)) toolCallOutcome {
	call := req.call

	emit(AgentEvent{
		Type: EventToolExecStart, ToolCallID: call.ID,
		ToolName: call.Name, ToolArgs: call.Arguments,
	})

	var result tools.ToolResult

	if req.tool == nil {
		result = tools.ToolResult{
			Content: "tool not found: " + call.Name,
			IsError: true,
		}
	} else {
		update := func(partial string) {
			emit(AgentEvent{
				Type: EventToolExecUpdate, ToolCallID: call.ID,
				ToolName: call.Name, PartialOutput: partial,
			})
		}
		var err error
		result, err = req.tool.Execute(ctx, call.ID, call.Arguments, update)
		if err != nil {
			result = tools.ToolResult{Content: err.Error(), IsError: true}
		}
	}

	emit(AgentEvent{
		Type: EventToolExecEnd, ToolCallID: call.ID,
		ToolName: call.Name, ToolResult: &result, IsError: result.IsError,
	})

	return toolCallOutcome{call: call, result: result}
}
