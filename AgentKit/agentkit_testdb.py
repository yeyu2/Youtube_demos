import agentkit
from agentkit import Graph, SimpleDBNode
from agentkit.compose_prompt import ComposePromptDB

import agentkit.llm_api
import os

# Set up OpenAI API key
os.environ["OPENAI_KEY"] = "sk-your-openai-api-key"
os.environ["OPENAI_ORG"] = "your-openai-org"

LLM_API_FUNCTION = agentkit.llm_api.get_query("gpt-4o")

LLM_API_FUNCTION.debug = True # Disable this to enable API-level error handling-retry

# Create a simple database (dictionary) with stock market data
db = {
    "company": "YeyuLab",
    "financial_metrics": {
        "revenue": "5B",
        "profit_margin": "15%",
        "debt_to_equity": 0.8
    },
    "shorthands": {}
}

graph = Graph()

# Node 1: Analyze financial health
subtask1 = "Analyze the financial health of $db.company$ based on the given financial metrics: revenue of $db.financial_metrics.revenue$, profit margin of $db.financial_metrics.profit_margin$, and debt-to-equity ratio of $db.financial_metrics.debt_to_equity$. Provide a brief assessment."
node1 = SimpleDBNode(
    "financial_health",
    subtask1,
    graph,
    LLM_API_FUNCTION,
    ComposePromptDB(),
    db,
    verbose=True
)
graph.add_node(node1)

# Evaluate the graph
result = graph.evaluate()

