import { tool } from "ai";
import { z } from "zod";

const braveSearchParamsSchema = z.object({
	query: z.string().describe("The search query"),
	count: z
		.number()
		.min(1)
		.max(20)
		.optional()
		.default(10)
		.describe("Number of search results to return (1-20)"),
	freshness: z
		.enum(["24h", "week", "month", "year"])
		.optional()
		.describe("Time period for results (e.g., '24h' for last 24 hours)"),
});

export type BraveSearchParams = z.infer<typeof braveSearchParamsSchema>;

const braveSearchResultSchema = z.object({
	success: z.literal(true),
	query: z.string(),
	results: z.array(
		z.object({
			title: z.string(),
			url: z.string(),
			description: z.string().optional(),
			published_date: z.string().optional(),
		}),
	),
	totalResults: z.number(),
});

const braveSearchErrorResultSchema = z.object({
	success: z.literal(false),
	message: z.string(),
});

const braveSearchOutputSchema = z.union([
	braveSearchResultSchema,
	braveSearchErrorResultSchema,
]);

export type BraveSearchResult = z.infer<typeof braveSearchOutputSchema>;

export const braveSearchTool = () =>
	tool({
		description:
			"Search the web using Brave Search API. Returns recent and relevant web results for any query. Use this to find current information, news, articles, and general web content.",
		inputSchema: braveSearchParamsSchema,
		outputSchema: braveSearchOutputSchema,
		execute: async ({
			query,
			count,
			freshness,
		}): Promise<BraveSearchResult> => {
			try {
				const apiKey = process.env.BRAVE_SEARCH_API_KEY;

				if (!apiKey) {
					return {
						success: false,
						message:
							"Brave Search API key is not configured. Please add BRAVE_SEARCH_API_KEY to your environment variables.",
					};
				}

				// Build URL with query parameters
				const params = new URLSearchParams({
					q: query,
					count: count.toString(),
				});

				if (freshness) {
					params.append("freshness", freshness);
				}

				const searchUrl = `https://api.search.brave.com/res/v1/web/search?${params.toString()}`;

				const response = await fetch(searchUrl, {
					headers: {
						Accept: "application/json",
						"Accept-Encoding": "gzip",
						"X-Subscription-Token": apiKey,
					},
				});

				if (!response.ok) {
					if (response.status === 401) {
						return {
							success: false,
							message:
								"Invalid Brave Search API key. Please check your API key configuration.",
						};
					}
					if (response.status === 429) {
						return {
							success: false,
							message:
								"Rate limit exceeded. Please try again later or upgrade your Brave Search API plan.",
						};
					}
					throw new Error(
						`Brave Search API error: ${response.status}`,
					);
				}

				const data = await response.json();

				// Extract web results
				const webResults = data.web?.results || [];

				const results = webResults.map((result: any) => ({
					title: result.title || "",
					url: result.url || "",
					description: result.description || "",
					published_date: result.age || undefined,
				}));

				return {
					success: true,
					query,
					results,
					totalResults: results.length,
				};
			} catch (error) {
				console.error("[braveSearchTool] Error:", error);
				const message =
					error instanceof Error
						? error.message
						: "Unknown error occurred while searching";
				return {
					success: false,
					message: `Failed to search: ${message}`,
				};
			}
		},
	});

