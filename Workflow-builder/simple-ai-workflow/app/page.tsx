import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Workflow, MessagesSquare } from "lucide-react";

export default function Home() {
	return (
		<div className="flex items-center justify-center min-h-screen p-8 bg-gradient-to-br from-background to-muted/20">
			<div className="w-full max-w-4xl">
				<div className="text-center mb-12">
					<h1 className="text-4xl font-bold mb-4">Simple AI Workflow</h1>
					<p className="text-lg text-muted-foreground">
						Build powerful AI agent workflows with a visual interface
					</p>
				</div>

				<div className="grid md:grid-cols-2 gap-6">
					<Card className="hover:shadow-lg transition-shadow">
						<CardHeader>
							<div className="flex items-center gap-2 mb-2">
								<Workflow className="h-6 w-6" />
								<CardTitle>Workflow Builder</CardTitle>
							</div>
							<CardDescription>
								Visual workflow designer with drag-and-drop nodes, AI agents, and conditional routing
							</CardDescription>
						</CardHeader>
						<CardContent>
							<ul className="space-y-2 mb-4 text-sm text-muted-foreground">
								<li>✓ Drag-and-drop interface</li>
								<li>✓ AI agent nodes with custom prompts</li>
								<li>✓ Conditional branching with if-else nodes</li>
								<li>✓ Real-time workflow execution</li>
								<li>✓ Live chat integration</li>
							</ul>
							<Link href="/workflow">
								<Button className="w-full">
									Open Workflow Builder
								</Button>
							</Link>
						</CardContent>
					</Card>

					<Card className="hover:shadow-lg transition-shadow">
						<CardHeader>
							<div className="flex items-center gap-2 mb-2">
								<MessagesSquare className="h-6 w-6" />
								<CardTitle>Components</CardTitle>
							</div>
							<CardDescription>
								Pre-built UI components for chat messages, inputs, and more
							</CardDescription>
						</CardHeader>
						<CardContent>
							<ul className="space-y-2 mb-4 text-sm text-muted-foreground">
								<li>✓ Chat message components</li>
								<li>✓ Chat input with mentions</li>
								<li>✓ Markdown rendering</li>
								<li>✓ Tool invocations display</li>
								<li>✓ Avatar and status badges</li>
							</ul>
							<div className="text-sm text-muted-foreground">
								<p className="mb-2">Install components:</p>
								<code className="bg-muted px-2 py-1 rounded text-xs block">
									npx shadcn@latest add @simple-ai/chat-message
								</code>
							</div>
						</CardContent>
					</Card>
				</div>

				<div className="mt-8 text-center text-sm text-muted-foreground">
					<p>
						Powered by{" "}
						<a href="https://reactflow.dev" className="underline" target="_blank" rel="noopener noreferrer">
							React Flow
						</a>
						{" "}and{" "}
						<a href="https://ai-sdk.dev" className="underline" target="_blank" rel="noopener noreferrer">
							Vercel AI SDK
						</a>
					</p>
				</div>
			</div>
		</div>
	);
}
