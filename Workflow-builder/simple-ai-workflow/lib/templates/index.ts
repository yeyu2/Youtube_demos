import type {
	FlowEdge,
	FlowNode,
} from "@/lib/workflow/types";
import { CODE_ANALYSIS_WORKFLOW } from "./code-analysis-workflow";
//import { CUSTOMER_SUPPORT_WORKFLOW } from "./customer-support-workflow";
import { WIKIPEDIA_RESEARCH_WORKFLOW } from "./wikipedia-research-workflow";

export type WorkflowTemplate = {
	id: string;
	name: string;
	description: string;
	category: string;
	nodes: FlowNode[];
	edges: FlowEdge[];
	suggestions: string[];
};

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
	{
		id: "empty",
		name: "Empty Canvas",
		description: "Start with a blank workflow - build your own from scratch",
		category: "Custom",
		nodes: [
			{
				id: "start-node",
				type: "start",
				position: { x: 100, y: 200 },
				data: {
					sourceType: { type: "text" },
				},
				measured: { width: 163, height: 58 },
				selected: false,
				dragging: false,
			},
			{
				id: "end-node",
				type: "end",
				position: { x: 500, y: 200 },
				data: {},
				measured: { width: 181, height: 58 },
				selected: false,
				dragging: false,
			},
		],
		edges: [
			{
				id: "start-to-end",
				source: "start-node",
				target: "end-node",
				sourceHandle: "message",
				targetHandle: "input",
				type: "status",
				data: {},
			},
		],
		suggestions: [],
	},
	{
		id: "code-analysis",
		name: "Code Agent",
		description: "Intelligent routing to language-specific code experts",
		category: "Development",
		nodes: CODE_ANALYSIS_WORKFLOW.nodes,
		edges: CODE_ANALYSIS_WORKFLOW.edges,
		suggestions: [
			"Review this React component and suggest improvements",
			"Debug this Python function that's throwing an error",
			"Help me optimize this database query",
		],
	},
	{
		id: "wikipedia-research",
		name: "Wikipedia Agent",
		description:
			"Comprehensive research workflow using Wikipedia search and summary tools",
		category: "Research",
		nodes: WIKIPEDIA_RESEARCH_WORKFLOW.nodes,
		edges: WIKIPEDIA_RESEARCH_WORKFLOW.edges,
		suggestions: [
			"Research the history of artificial intelligence",
			"What are the key principles of quantum physics?",
			"Research the biography of Albert Einstein",
		],
	},
	
];

export function getTemplateById(id: string): WorkflowTemplate | undefined {
	return WORKFLOW_TEMPLATES.find((template) => template.id === id);
}

// Default to empty canvas for easy testing and customization
export const DEFAULT_TEMPLATE = WORKFLOW_TEMPLATES[0];
