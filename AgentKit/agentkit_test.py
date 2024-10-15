import agentkit
from agentkit import Graph, BaseNode
import agentkit.llm_api
import os
os.environ["OPENAI_KEY"] = "sk-your-openai-api-key"
os.environ["OPENAI_ORG"] = "your-openai-org"

graph = Graph()

LLM_API_FUNCTION = agentkit.llm_api.get_query("gpt-4o")
LLM_API_FUNCTION.debug = True

# Node 1: Generate a story idea
story_idea_key = "story_idea"
story_idea_prompt = "Generate a creative and short story idea involving a time traveler and a talking llama."
story_idea_node = BaseNode(story_idea_key, story_idea_prompt, graph, LLM_API_FUNCTION, agentkit.compose_prompt.BaseComposePrompt(), verbose=True)
graph.add_node(story_idea_node)
# Node 2: Develop the story idea into a short outline
outline_key = "outline"
outline_prompt = "Develop idea into a short outline"
outline_node = BaseNode(outline_key, outline_prompt, graph, LLM_API_FUNCTION, agentkit.compose_prompt.BaseComposePrompt(), verbose=True)
graph.add_node(outline_node)
# Node 3: Write a short story based on the outline
story_key = "story"
story_prompt = "Write a final version of the short story"
story_node = BaseNode(story_key, story_prompt, graph, LLM_API_FUNCTION, agentkit.compose_prompt.BaseComposePrompt(), verbose=True)
graph.add_node(story_node)
# Node 4: Review the story
review_key = "review"
review_prompt = "Review the story with its outline and provide 50 words short feedback and an integer score under 100"
review_node = BaseNode(review_key, review_prompt, graph, LLM_API_FUNCTION, agentkit.compose_prompt.BaseComposePrompt(), verbose=True)
graph.add_node(review_node)

graph.add_edge(story_idea_key, outline_key)
graph.add_edge(outline_key, story_key)
graph.add_edge(story_key, review_key)
graph.add_edge(outline_key, review_key)

#Node 5: temporary node 1 for recommendation to New York Times
recommend_nyt_key = "recommend_nyt"
recommend_nyt_prompt = "Recommend the story to New York Times"
recommend_nyt_node = BaseNode(recommend_nyt_key, recommend_nyt_prompt, graph, LLM_API_FUNCTION, agentkit.compose_prompt.BaseComposePrompt(), verbose=True)
graph.add_temporary_node(recommend_nyt_node)
graph.add_edge_temporary(review_key, recommend_nyt_key)
graph.add_edge_temporary(story_key, recommend_nyt_key)

result = graph.evaluate()

# Node 6: temporary node 2 for recommendation to Washington Post
recommend_wapo_key = "recommend_wapo"
recommend_wapo_prompt = "Recommend the story to Washington Post"
recommend_wapo_node = BaseNode(recommend_wapo_key, recommend_wapo_prompt, graph, LLM_API_FUNCTION, agentkit.compose_prompt.BaseComposePrompt(), verbose=True)
graph.add_temporary_node(recommend_wapo_node)
graph.add_edge_temporary(review_key, recommend_wapo_key)
graph.add_edge_temporary(story_key, recommend_wapo_key)

result = graph.evaluate()