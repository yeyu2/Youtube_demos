import { Panel } from "@xyflow/react";
import { AgentNodePanel } from "@/components/workflow/agent-node";
import { EndNodePanel } from "@/components/workflow/end-node";
import { IfElseNodePanel } from "@/components/workflow/if-else-node";
import { StartNodePanel } from "@/components/workflow/start-node";
import type { WorkflowToolId } from "@/lib/tools";
import type { FlowNode } from "@/lib/workflow/types";
import { useWorkflow } from "@/hooks/workflow/use-workflow";

export function NodeEditorPanel({
	nodeId,
	toolDescriptions,
}: {
	nodeId: FlowNode["id"];
	toolDescriptions: Record<WorkflowToolId, string>;
}) {
	const node = useWorkflow((state) => state.getNodeById(nodeId));
	if (!node) {
		return <NodeEditorPanelNotFound />;
	}

	if (node.type === "note") {
		return null;
	}

	return (
		<Panel
			position="top-right"
			className="bg-card p-4 rounded-lg shadow-md border w-96 max-h-[calc(100vh-5rem)] overflow-y-auto"
		>
			<h3 className="font-semibold text-sm mb-3 capitalize">
				{node.type} Node
			</h3>
			<NodeEditorContent
				node={node}
				toolDescriptions={toolDescriptions}
			/>
		</Panel>
	);
}

function NodeEditorContent({
	node,
	toolDescriptions,
}: {
	node: FlowNode;
	toolDescriptions: Record<WorkflowToolId, string>;
}) {
	switch (node.type) {
		case "agent":
			return (
				<AgentNodePanel
					node={node}
					toolDescriptions={toolDescriptions}
				/>
			);
		case "end":
			return <EndNodePanel node={node} />;
		case "if-else":
			return <IfElseNodePanel node={node} />;
		case "start":
			return <StartNodePanel node={node} />;
	}
}

function NodeEditorPanelNotFound() {
	return (
		<Panel
			position="top-right"
			className="bg-card p-4 rounded-lg shadow-md border w-96 max-h-[calc(100vh-4rem)] overflow-y-auto"
		>
			<div>Node not found</div>
		</Panel>
	);
}
