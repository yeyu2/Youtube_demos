"""
Context Engineering Demo - Tools

This module demonstrates key context engineering patterns from the Google blog:
1. Handle Pattern - Store references, not content
2. State for Data Flow - Tools communicate via context.state
3. On-Demand Loading - Load content only when processing
4. State Prefixes - temp:, user:, app: for different scopes
"""

from google.adk.tools import ToolContext
from google.genai import types


# Simulated document storage
# In production, this would be a database or file storage service
DOCUMENTS = {
    "doc_001": {
        "title": "Q3 Financial Report",
        "content": """Revenue increased 15% year-over-year, reaching $4.2 billion. 
Operating margin improved to 23%, up from 19% last quarter. 
Key growth drivers include cloud services (+32%) and subscription revenue (+28%). 
Headcount grew by 150 employees, primarily in engineering and sales.
Cash position remains strong at $2.1 billion with no long-term debt.""",
        "size": "2.3 MB"
    },
    "doc_002": {
        "title": "Product Roadmap 2025",
        "content": """Priority 1: AI integration across all products (Q1 2025).
Priority 2: Mobile-first redesign for consumer apps (Q2 2025).
Priority 3: Enterprise security features including SSO and audit logs (Q3 2025).
Priority 4: International expansion - APAC region focus (Q4 2025).
Budget allocation: 40% AI, 25% Mobile, 20% Enterprise, 15% International.""",
        "size": "1.1 MB"
    },
    "doc_003": {
        "title": "Customer Feedback Summary",
        "content": """Top feature requests from Q3 survey (2,500 respondents):
1. Better mobile experience - 45% of respondents
2. Faster load times - 32% of respondents  
3. Dark mode support - 28% of respondents
4. Offline functionality - 22% of respondents

NPS score: 72 (up from 68 last quarter).
Customer churn rate decreased to 2.1%.
Most praised feature: real-time collaboration (mentioned by 61% of promoters).""",
        "size": "890 KB"
    }
}


def list_documents(tool_context: ToolContext) -> dict:
    """List available documents without loading their content.
    
    PATTERN: Handle Pattern
    - Returns metadata (references) not actual content
    - Keeps the prompt small regardless of document sizes
    - User can then choose which document to load
    
    Returns:
        dict: List of document metadata (id, title, size)
    """
    docs = []
    for doc_id, doc in DOCUMENTS.items():
        docs.append({
            "id": doc_id,
            "title": doc["title"],
            "size": doc["size"]
            # Note: We intentionally don't include "content" here
        })
    
    return {
        "available_documents": docs,
        "count": len(docs),
        "hint": "Use load_document with a doc_id to load a specific document"
    }


def load_document(tool_context: ToolContext, doc_id: str) -> dict:
    """Load a document and store its reference in state.
    
    PATTERN: State for Data Flow + Handle Pattern
    - Stores doc_id in state (small reference)
    - Saves content as artifact (external storage)
    - Other tools can access via state without re-specifying doc_id
    
    Args:
        tool_context: ADK tool context for state and artifact access
        doc_id: Document identifier (e.g., "doc_001")
    
    Returns:
        dict: Load status and document metadata
    """
    if doc_id not in DOCUMENTS:
        available = list(DOCUMENTS.keys())
        return {
            "error": f"Document '{doc_id}' not found",
            "available_ids": available
        }
    
    doc = DOCUMENTS[doc_id]
    
    # Store reference in state (small, stays in working context)
    tool_context.state["temp:current_doc_id"] = doc_id
    tool_context.state["temp:current_doc_title"] = doc["title"]
    
    # Store content as artifact (large, external storage)
    # This keeps the content out of the prompt until needed
    artifact_data = types.Part.from_text(text=doc["content"])
    tool_context.save_artifact(f"doc_{doc_id}.txt", artifact_data)
    
    return {
        "status": "loaded",
        "doc_id": doc_id,
        "title": doc["title"],
        "size": doc["size"],
        "note": "Content saved as artifact. Use analyze_document to process it."
    }


def analyze_document(tool_context: ToolContext) -> dict:
    """Analyze the currently loaded document.
    
    PATTERN: On-Demand Loading + State for Data Flow
    - Reads doc_id from state (set by load_document)
    - Loads artifact content only when actually processing
    - Content doesn't sit in prompt for every turn
    
    Returns:
        dict: Analysis results including word count and content preview
    """
    # Read from state - no need to pass doc_id explicitly
    doc_id = tool_context.state.get("temp:current_doc_id")
    if not doc_id:
        return {
            "error": "No document loaded",
            "hint": "Use load_document first to load a document"
        }
    
    doc_title = tool_context.state.get("temp:current_doc_title", "Unknown")
    
    # Load content from artifact only when needed
    content = None
    try:
        artifact = tool_context.load_artifact(f"doc_{doc_id}.txt")
        if artifact and hasattr(artifact, 'text'):
            content = artifact.text
    except Exception:
        pass
    
    # Fallback to direct access for demo purposes
    if not content:
        content = DOCUMENTS.get(doc_id, {}).get("content", "")
    
    if not content:
        return {"error": f"Could not load content for {doc_id}"}
    
    # Perform analysis
    word_count = len(content.split())
    line_count = len(content.strip().split('\n'))
    has_numbers = any(char.isdigit() for char in content)
    has_percentages = '%' in content
    
    return {
        "doc_id": doc_id,
        "title": doc_title,
        "word_count": word_count,
        "line_count": line_count,
        "contains_metrics": has_numbers,
        "contains_percentages": has_percentages,
        "content_preview": content[:300] + "..." if len(content) > 300 else content
    }


def save_user_preference(
    tool_context: ToolContext, 
    preference_key: str, 
    preference_value: str
) -> dict:
    """Save a user preference to persistent state.
    
    PATTERN: State Prefixes
    - temp: for temporary data (cleared after invocation)
    - user: for user-level persistent data (survives sessions)
    - app: for application-level persistent data
    
    Args:
        tool_context: ADK tool context
        preference_key: Preference name (e.g., "summary_style")
        preference_value: Preference value (e.g., "brief")
    
    Returns:
        dict: Confirmation of saved preference
    """
    # Use user: prefix for persistent user preferences
    state_key = f"user:preference:{preference_key}"
    tool_context.state[state_key] = preference_value
    
    return {
        "status": "saved",
        "key": preference_key,
        "value": preference_value,
        "state_key": state_key,
        "note": "Preference saved. Will persist across sessions with a persistent SessionService."
    }


def get_user_preferences(tool_context: ToolContext) -> dict:
    """Retrieve all saved user preferences.
    
    PATTERN: State for Data Flow
    - Reads from persistent state
    - Demonstrates how preferences survive across tool calls
    
    Returns:
        dict: All saved user preferences
    """
    preferences = {}
    
    # Check common preference keys
    # In production, you'd iterate over all state keys with user:preference: prefix
    common_keys = [
        "summary_style",
        "detail_level", 
        "language",
        "format",
        "tone",
        "length"
    ]
    
    for key in common_keys:
        state_key = f"user:preference:{key}"
        value = tool_context.state.get(state_key)
        if value:
            preferences[key] = value
    
    if not preferences:
        return {
            "preferences": {},
            "note": "No preferences saved yet. Use save_user_preference to set them.",
            "example": "save_user_preference(preference_key='summary_style', preference_value='brief')"
        }
    
    return {
        "preferences": preferences,
        "count": len(preferences)
    }


def clear_current_document(tool_context: ToolContext) -> dict:
    """Clear the currently loaded document from state.
    
    PATTERN: State Management
    - Demonstrates cleaning up temporary state
    - Uses temp: prefix which should be cleared after invocation anyway
    
    Returns:
        dict: Confirmation of cleared state
    """
    doc_id = tool_context.state.get("temp:current_doc_id")
    doc_title = tool_context.state.get("temp:current_doc_title")
    
    if not doc_id:
        return {"status": "nothing_to_clear", "note": "No document was loaded"}
    
    # Clear the state
    tool_context.state["temp:current_doc_id"] = None
    tool_context.state["temp:current_doc_title"] = None
    
    return {
        "status": "cleared",
        "cleared_doc_id": doc_id,
        "cleared_doc_title": doc_title
    }
