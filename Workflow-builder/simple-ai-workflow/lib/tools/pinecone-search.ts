import { tool } from "ai";
import { z } from "zod";
import { Pinecone } from "@pinecone-database/pinecone";

const pineconeSearchParamsSchema = z.object({
	query: z.string().describe("The search query to find semantically similar content"),
	topK: z
		.number()
		.min(1)
		.max(20)
		.optional()
		.default(5)
		.describe("Number of similar results to return (1-20)"),
	namespace: z
		.string()
		.optional()
		.default("__default__")
		.describe("Namespace to search in (default: '__default__')"),
});

export type PineconeSearchParams = z.infer<typeof pineconeSearchParamsSchema>;

const pineconeSearchResultSchema = z.object({
	success: z.literal(true),
	query: z.string(),
	results: z.array(
		z.object({
			id: z.string(),
			score: z.number(),
			text: z.string().optional(),
			metadata: z.record(z.any()).optional(),
		}),
	),
	totalResults: z.number(),
});

const pineconeSearchErrorResultSchema = z.object({
	success: z.literal(false),
	message: z.string(),
});

const pineconeSearchOutputSchema = z.union([
	pineconeSearchResultSchema,
	pineconeSearchErrorResultSchema,
]);

export type PineconeSearchResult = z.infer<typeof pineconeSearchOutputSchema>;

export const pineconeSearchTool = () =>
	tool({
		description:
			"Search a knowledge base using semantic search powered by Pinecone vector database. Finds content semantically similar to your query, even if exact words don't match. Use this to retrieve relevant information from uploaded documents, manuals, guides, or any indexed content.",
		inputSchema: pineconeSearchParamsSchema,
		outputSchema: pineconeSearchOutputSchema,
		execute: async ({
			query,
			topK,
			namespace,
		}): Promise<PineconeSearchResult> => {
			try {
				const apiKey = process.env.PINECONE_API_KEY;
				const indexName = process.env.PINECONE_INDEX_NAME;
				const indexHost = process.env.PINECONE_INDEX_HOST;

				if (!apiKey) {
					return {
						success: false,
						message:
							"Pinecone API key is not configured. Please add PINECONE_API_KEY to your environment variables.",
					};
				}

				if (!indexName) {
					return {
						success: false,
						message:
							"Pinecone index name is not configured. Please add PINECONE_INDEX_NAME to your environment variables.",
					};
				}

				if (!indexHost) {
					return {
						success: false,
						message:
							"Pinecone index host is not configured. Please add PINECONE_INDEX_HOST to your environment variables.",
					};
				}

				// Initialize Pinecone client
				const pc = new Pinecone({ apiKey });

				// Get the index with specific host
				const index = pc.index(indexName, indexHost);

				// Use searchRecords for text-based search (with integrated embedding)
				// This is the modern approach for Pinecone serverless indexes
				const response = await index.namespace(namespace).searchRecords({
					query: {
						topK,
						inputs: { text: query },
					},
					// Request all fields to get the content
					fields: ["*"],
				});

				// Transform results
				const results = (response.result?.hits || []).map((hit: any) => ({
					id: hit._id,
					score: hit._score,
					text: hit.fields?.text || hit.fields?.chunk_text || hit.fields?.content || "",
					metadata: hit.fields || {},
				}));

				return {
					success: true,
					query,
					results,
					totalResults: results.length,
				};
			} catch (error) {
				console.error("[pineconeSearchTool] Error:", error);
				const message =
					error instanceof Error
						? error.message
						: "Unknown error occurred while searching";
				return {
					success: false,
					message: `Failed to search Pinecone: ${message}`,
				};
			}
		},
	});

