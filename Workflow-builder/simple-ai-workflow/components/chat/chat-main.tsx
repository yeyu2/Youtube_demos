import { ChatContent } from "@/components/chat/chat-content";
import { ChatHeader } from "@/components/chat/chat-header";

export function ChatMain() {
	return (
		<div className="flex-1 flex flex-col h-full">
			<ChatHeader />
			<ChatContent />
		</div>
	);
}
