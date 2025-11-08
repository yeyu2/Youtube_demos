import * as React from "react";
import { useCallback, useState, type ComponentProps } from "react";
import {
	Sidebar,
	SidebarInset,
	SidebarProvider,
} from "@/components/ui/sidebar";
import { cn } from "@/lib/utils";

export const MIN_WIDTH = 320; // 20rem
export const MAX_WIDTH = 800; // 50rem
export const DEFAULT_WIDTH = 448; // 28rem

export function AppLayout({ 
	sidebarWidth = DEFAULT_WIDTH,
	...props 
}: ComponentProps<typeof SidebarProvider> & {
	sidebarWidth?: number;
}) {
	return (
		<SidebarProvider
			style={{
				// @ts-expect-error CSS custom properties
				"--sidebar-width": `${sidebarWidth}px`,
				"--sidebar-width-mobile": "30rem",
			}}
			{...props}
		/>
	);
}

export function AppLayoutInset({
	className,
	...props
}: ComponentProps<typeof SidebarInset>) {
	return <SidebarInset className={className} {...props} />;
}

export function AppLayoutSidebar({
	className,
	side = "right",
	onResize,
	...props
}: ComponentProps<typeof Sidebar> & {
	onResize?: (width: number) => void;
}) {
	const [isResizing, setIsResizing] = useState(false);

	const handleMouseDown = useCallback((e: React.MouseEvent) => {
		e.preventDefault();
		setIsResizing(true);
	}, []);

	const handleMouseMove = useCallback(
		(e: MouseEvent) => {
			if (!isResizing) return;

			const newWidth =
				side === "right"
					? window.innerWidth - e.clientX
					: e.clientX;

			const clampedWidth = Math.max(
				MIN_WIDTH,
				Math.min(MAX_WIDTH, newWidth),
			);

			onResize?.(clampedWidth);
		},
		[isResizing, side, onResize],
	);

	const handleMouseUp = useCallback(() => {
		setIsResizing(false);
	}, []);

	// Add event listeners for mouse move and up
	React.useEffect(() => {
		if (isResizing) {
			document.addEventListener("mousemove", handleMouseMove);
			document.addEventListener("mouseup", handleMouseUp);
			document.body.style.cursor = "ew-resize";
			document.body.style.userSelect = "none";

			return () => {
				document.removeEventListener("mousemove", handleMouseMove);
				document.removeEventListener("mouseup", handleMouseUp);
				document.body.style.cursor = "";
				document.body.style.userSelect = "";
			};
		}
	}, [isResizing, handleMouseMove, handleMouseUp]);

	return (
		<Sidebar
			className={cn("bg-background relative", className)}
			side={side}
			{...props}
		>
			{/* Resize Handle */}
			<div
				onMouseDown={handleMouseDown}
				className={cn(
					"absolute top-0 bottom-0 w-1 hover:w-1.5 bg-transparent hover:bg-border transition-all cursor-ew-resize z-50 group",
					side === "right" ? "left-0" : "right-0",
				)}
			>
				<div className="absolute inset-y-0 left-1/2 -translate-x-1/2 w-px bg-border opacity-0 group-hover:opacity-100 transition-opacity" />
			</div>
			{props.children}
		</Sidebar>
	);
}
