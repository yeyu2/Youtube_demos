import type { Tool } from "ai";

/**
 * Configuration for tool call delays
 * Helps prevent hitting API rate limits
 */
export const TOOL_DELAY_CONFIG = {
	// Delay in milliseconds between tool calls
	"wikipedia-query": 500, // 0.5 seconds between Wikipedia API calls
	"brave-search": 1000, // 1 second between Brave Search API calls (stricter rate limit)
} as const;

type ToolId = keyof typeof TOOL_DELAY_CONFIG;

// Track last call time and queue for each tool
const lastCallTimes: Map<string, number> = new Map();
const callQueues: Map<string, Promise<any>> = new Map();

/**
 * Wraps a tool to add rate limiting delays
 * Prevents hitting API rate limits when making multiple tool calls
 * Uses a queue to ensure calls are truly sequential, even when LLM makes parallel calls
 */
export function wrapToolWithDelay<T extends Tool>(
	toolId: ToolId,
	tool: T,
): T {
	const delayMs = TOOL_DELAY_CONFIG[toolId];

	if (!delayMs || !tool.execute) {
		return tool; // No delay needed or no execute function
	}

	const originalExecute = tool.execute.bind(tool);

	return {
		...tool,
		execute: async (params: any, context: any) => {
			// Get the current queue for this tool, or create a resolved promise
			const currentQueue = callQueues.get(toolId) || Promise.resolve();

			// Chain this call onto the queue
			const thisCall = currentQueue.then(async () => {
				const now = Date.now();
				const lastCall = lastCallTimes.get(toolId) || 0;
				const timeSinceLastCall = now - lastCall;

				// If we called this tool recently, wait before calling again
				if (timeSinceLastCall < delayMs) {
					const waitTime = delayMs - timeSinceLastCall;
					console.log(
						`[${toolId}] Rate limit protection: waiting ${waitTime}ms before next call`,
					);
					await new Promise((resolve) =>
						setTimeout(resolve, waitTime),
					);
				}

				// Update last call time BEFORE executing
				lastCallTimes.set(toolId, Date.now());

				// Execute the actual tool
				return originalExecute(params, context);
			});

			// Update the queue
			callQueues.set(toolId, thisCall);

			// Return the result
			return thisCall;
		},
	} as T;
}

