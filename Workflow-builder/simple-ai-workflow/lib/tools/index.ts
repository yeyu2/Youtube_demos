import type { Tool } from "ai";
import { wikipediaQueryTool } from "@/lib/tools/wikipedia-query";
import { braveSearchTool } from "@/lib/tools/brave-search";
import { wrapToolWithDelay } from "@/lib/tools/tool-wrapper";

export const WORKFLOW_TOOL_DESCRIPTIONS: Record<string, string> = {
	"wikipedia-query": "Search Wikipedia articles or get article summaries",
	"brave-search": "Search the web for current information and news",
	"pinecone-search": "Search knowledge base using semantic similarity",
};

export const WORKFLOW_TOOLS = Object.keys(WORKFLOW_TOOL_DESCRIPTIONS) as WorkflowToolId[];

export type WorkflowToolId = keyof typeof WORKFLOW_TOOL_DESCRIPTIONS;

// Lazy-load Pinecone only on server-side to avoid fs module in client
let pineconeToolCache: Tool | null = null;

export const getWorkflowTools = () => {
	// Only initialize Pinecone tool on server-side (when this is actually called)
	if (!pineconeToolCache && typeof window === "undefined") {
		try {
			// Dynamic import to avoid loading on client
			const { pineconeSearchTool } = require("@/lib/tools/pinecone-search");
			pineconeToolCache = pineconeSearchTool();
		} catch (error) {
			console.warn("Pinecone tool not available:", error);
		}
	}

	const tools: Record<string, Tool> = {
		"wikipedia-query": wrapToolWithDelay("wikipedia-query", wikipediaQueryTool()),
		"brave-search": wrapToolWithDelay("brave-search", braveSearchTool()),
	};

	// Add Pinecone tool if available
	if (pineconeToolCache) {
		tools["pinecone-search"] = pineconeToolCache;
	}

	return tools;
};
