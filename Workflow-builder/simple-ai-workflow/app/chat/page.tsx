import { ChatMain } from "@/components/chat/chat-main";
import { AppLayout } from "@/components/layout/app-layout";

export default function Page() {
	return (
		<AppLayout sidebarChildren={null}>
			<ChatMain />
		</AppLayout>
	);
}
