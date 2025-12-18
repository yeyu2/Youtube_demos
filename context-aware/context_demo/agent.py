"""
Context Engineering Demo - Agent

This agent demonstrates context engineering principles from the Google blog:
- Handle Pattern: References instead of content
- State for Data Flow: Tools communicate via context.state
- On-Demand Loading: Load content only when processing
- State Prefixes: temp:, user:, app: for different scopes

Run with: adk web
"""

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from .tools import (
    list_documents,
    load_document,
    analyze_document,
    save_user_preference,
    get_user_preferences,
    clear_current_document
)


# Wrap functions as ADK FunctionTools
list_documents_tool = FunctionTool(list_documents)
load_document_tool = FunctionTool(load_document)
analyze_document_tool = FunctionTool(analyze_document)
save_preference_tool = FunctionTool(save_user_preference)
get_preferences_tool = FunctionTool(get_user_preferences)
clear_document_tool = FunctionTool(clear_current_document)


AGENT_INSTRUCTION = """You are a Document Assistant demonstrating context engineering patterns.

## Your Tools

1. `list_documents` - Show available documents (returns metadata only, not content)
2. `load_document` - Load a document by ID (stores reference in state, content as artifact)
3. `analyze_document` - Analyze the loaded document (reads from state, loads artifact on-demand)
4. `save_user_preference` - Save a user preference (uses user: prefix for persistence)
5. `get_user_preferences` - Get all saved preferences
6. `clear_current_document` - Clear the loaded document from state

## Workflow

**For document questions:**
1. First call `list_documents` to show what's available
2. Call `load_document` with the doc_id user wants
3. Call `analyze_document` to process it

**For preferences:**
- Use `save_user_preference` when user mentions preferences (e.g., "I like brief summaries")
- Use `get_user_preferences` to check what's saved

## Key Behaviors

- Always list before loading (don't guess document IDs)
- Always load before analyzing (state must be set first)
- Keep responses concise - focus on results, not architecture explanations
- When user says "analyze it" or "summarize it", use the currently loaded document from state

## Example Interactions

User: "What documents do you have?"
→ Call list_documents, show the results

User: "Load the financial report"
→ Call load_document with doc_id="doc_001"

User: "What's in it?"
→ Call analyze_document (uses state to find current doc)

User: "I prefer detailed analysis"
→ Call save_user_preference with key="detail_level", value="detailed"
"""


root_agent = LlmAgent(
    name="ContextDemoAgent",
    model="gemini-2.5-pro",
    instruction=AGENT_INSTRUCTION,
    tools=[
        list_documents_tool,
        load_document_tool,
        analyze_document_tool,
        save_preference_tool,
        get_preferences_tool,
        clear_document_tool
    ]
)
