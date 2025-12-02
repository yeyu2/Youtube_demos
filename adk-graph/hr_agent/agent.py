"""
TalentGraph HR Agent - ADK Agent with Knowledge Graph Integration
Provides conversational interface to the HR knowledge graph with two main capabilities:
1. Add/update information to the graph
2. Search and retrieve information from the graph
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from google.adk.agents.llm_agent import Agent
from google.adk.tools.function_tool import FunctionTool

from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.llm_client.gemini_client import GeminiClient, LLMConfig
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.nodes import EpisodeType
from graphiti_core.prompts.models import Message

load_dotenv()

# Configuration
google_api_key = os.environ.get('GOOGLE_API_KEY')
falkor_host = os.environ.get('FALKORDB_HOST', 'localhost')
falkor_port = os.environ.get('FALKORDB_PORT', '6379')

# Global Graphiti instance (initialized on first use)
_graphiti_instance = None


# Pydantic models for structured outputs
class SearchQueries(BaseModel):
    """Model for structured search query generation."""
    queries: List[str] = Field(
        description="List of 2-4 targeted search queries to retrieve information from the knowledge graph",
        min_items=1,
        max_items=4
    )


async def get_graphiti() -> Graphiti:
    """Get or create the Graphiti instance."""
    global _graphiti_instance
    
    if _graphiti_instance is None:
        falkor_driver = FalkorDriver(
            host=falkor_host, 
            port=falkor_port,
            database="talentgraph"
        )
        
        llm_client = GeminiClient(
            config=LLMConfig(
                api_key=google_api_key,
                model="gemini-2.5-pro",
                small_model="gemini-2.5-flash-lite"
            )
        )
        
        embedder = GeminiEmbedder(
            config=GeminiEmbedderConfig(
                api_key=google_api_key,
                embedding_model="gemini-embedding-001"
            )
        )
        
        cross_encoder = GeminiRerankerClient(
            config=LLMConfig(
                api_key=google_api_key,
                model="gemini-2.5-flash-lite"
            )
        )
        
        _graphiti_instance = Graphiti(
            graph_driver=falkor_driver,
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder
        )
    
    return _graphiti_instance


async def add_hr_information(content: str, description: str = "HR information update") -> str:
    """
    Add or update HR information in the knowledge graph.
    
    Use this tool when the user provides new information about:
    - Employee details (name, role, skills, clearances)
    - Organizational changes (promotions, transfers, new hires)
    - Project assignments or updates
    - Team structure changes
    - Compliance or policy updates
    
    Args:
        content: The detailed information to add to the knowledge graph. 
                 Should be comprehensive and include all relevant context.
        description: A brief description of what type of information this is 
                    (e.g., "promotion announcement", "new hire", "project update")
    
    Returns:
        A confirmation message indicating the information was successfully added.
    
    Example:
        content: "John Smith joined as a Senior DevOps Engineer on the Platform Team, 
                  reporting to Bob Thompson. He has expertise in Kubernetes and AWS."
        description: "New hire announcement"
    """
    graphiti = await get_graphiti()
    
    try:
        # Add episode to the knowledge graph
        await graphiti.add_episode(
            name=f"hr_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            episode_body=content,
            source=EpisodeType.text,
            source_description=description,
            reference_time=datetime.now(timezone.utc),
        )
        
        return f"✅ Successfully added HR information to knowledge graph: {description}"
    
    except Exception as e:
        return f"❌ Error adding information to knowledge graph: {str(e)}"


async def search_hr_information(query: str, max_results: int = 10) -> str:
    """
    Search the HR knowledge graph for information.
    
    This tool performs intelligent multi-step search to retrieve HR information:
    - Employee information (roles, skills, managers, projects)
    - Organizational structure and reporting lines
    - Project teams and assignments
    - Compliance status and security clearances
    - Skills and expertise across the organization
    
    The tool automatically:
    1. Breaks down complex queries into multiple targeted searches
    2. Retrieves relevant facts from the knowledge graph
    3. Returns formatted facts list for the agent to filter and summarize
    
    Args:
        query: The HR question or information request. Can be complex queries like:
               - "Who reports to Bob Thompson?"
               - "Find all Kubernetes experts with Level 3 clearance"
               - "What projects is Alice Johnson working on?"
               - "Who is available to join Project X?"
        max_results: Maximum number of facts to retrieve per search (default: 10)
    
    Returns:
        A formatted list of relevant facts from the knowledge graph with temporal information.
        The agent will filter and summarize these facts based on the user's query.
    """
    print(f"🔎 DEBUG: Starting search for: '{query}'")
    graphiti = await get_graphiti()
    
    try:
        # Step 1: Determine search strategy based on query complexity
        search_queries = await _generate_search_queries(query)
        print(f"🧠 DEBUG: Generated search queries: {search_queries}")
        
        # Step 2: Execute multiple searches in parallel
        print(f"🚀 DEBUG: Executing {len(search_queries)} graph searches in parallel...")
        
        async def execute_single_search(q):
            print(f"▶️ DEBUG: Search started: '{q}'")
            results = await graphiti.search(q, num_results=max_results)
            print(f"✅ DEBUG: Found {len(results)} results for '{q}'")
            return q, results

        # Run all searches concurrently
        search_tasks = [execute_single_search(q) for q in search_queries]
        results_list = await asyncio.gather(*search_tasks)
        
        # Process and deduplicate results
        all_facts = []
        seen_facts = set()
        
        for q, results in results_list:
            for result in results:
                # Deduplicate based on fact content
                if result.fact not in seen_facts:
                    seen_facts.add(result.fact)
                    all_facts.append({
                        'fact': result.fact,
                        'valid_at': str(result.valid_at) if hasattr(result, 'valid_at') and result.valid_at else None,
                        'invalid_at': str(result.invalid_at) if hasattr(result, 'invalid_at') and result.invalid_at else None,
                        'query': q
                    })
        
        if not all_facts:
            print("❌ DEBUG: No facts found.")
            return "❌ No relevant information found in the knowledge graph for this query."
        
        # Step 3: Synthesize results (formatting only)
        synthesized_answer = await _synthesize_search_results(query, all_facts)
        print(f"📝 DEBUG: Returning synthesized answer ({len(synthesized_answer)} chars)")
        
        return synthesized_answer
    
    except Exception as e:
        print(f"🔥 DEBUG: Error in search: {e}")
        import traceback
        traceback.print_exc()
        return f"❌ Error searching knowledge graph: {str(e)}"


async def _generate_search_queries(original_query: str) -> List[str]:
    """
    Generate multiple targeted search queries from a complex user query.
    Uses LLM with Pydantic response_model for structured output.
    """
    llm_client = GeminiClient(
        config=LLMConfig(
            api_key=google_api_key,
            model="gemini-2.5-pro",
            small_model="gemini-2.5-flash-lite"
        )
    )
    
    prompt = """You are an HR knowledge graph search expert. Break down this user query into 2-4 targeted search queries 
that will retrieve relevant information from the knowledge graph.

User Query: "{query}"

Generate search queries that cover:
- Direct entity searches (people, teams, projects)
- Relationship searches (reports to, works on, has skill)
- Attribute searches (clearances, skills, status)

Example queries: "Alice Johnson manager projects", "Platform Team members", "Level 3 clearance employees""".format(query=original_query)

    try:
        # Use response_model for structured Pydantic output
        response_dict = await llm_client.generate_response(
            messages=[Message(role="user", content=prompt)],
            response_model=SearchQueries
        )
        
        # Parse dict into Pydantic model
        queries_obj = SearchQueries(**response_dict)
        
        return queries_obj.queries
    
    except Exception as e:
        # Fallback to original query if parsing fails
        print(f"Warning: Failed to generate structured queries: {e}")
        import traceback
        traceback.print_exc()
        return [original_query]


async def _synthesize_search_results(original_query: str, facts: List[Dict[str, Any]]) -> str:
    """
    Format search results as a list of relevant facts.
    The speech agent will handle filtering and summarization based on the user query.
    """
    # Format facts with temporal information
    formatted_facts = []
    for i, fact in enumerate(facts, 1):
        fact_text = f"{i}. {fact['fact']}"
        
        # Add temporal information if available
        temporal_info = []
        if fact.get('valid_at'):
            temporal_info.append(f"Valid from: {fact['valid_at']}")
        if fact.get('invalid_at'):
            temporal_info.append(f"Invalid at: {fact['invalid_at']}")
        
        if temporal_info:
            fact_text += f" [{', '.join(temporal_info)}]"
        
        formatted_facts.append(fact_text)
    
    # Return formatted list with header
    result = f"""Retrieved {len(facts)} relevant facts from the knowledge graph:

{chr(10).join(formatted_facts)}

Note: These are raw facts from the knowledge graph. Please filter and summarize based on the user's query."""
    
    return result


# Create the HR Agent
root_agent = Agent(
    model="gemini-2.5-flash-native-audio-preview-09-2025",
    #model = "gemini-2.5-flash",
    name="talentgraph_hr_agent",
    description=(
        "TalentGraph HR Intelligence Agent\n\n"
        "I am an AI assistant with access to TechNova's HR knowledge graph. "
        "I can help you with:\n\n"
        "📊 Information Retrieval:\n"
        "- Employee details (roles, skills, managers, projects)\n"
        "- Organizational structure and reporting lines\n"
        "- Project teams and assignments\n"
        "- Compliance status and security clearances\n"
        "- Skills and expertise searches\n\n"
        "✏️ Information Updates:\n"
        "- Record new hires or departures\n"
        "- Update promotions and role changes\n"
        "- Add project assignments\n"
        "- Record compliance or certification updates\n\n"
        "Example queries:\n"
        "- 'Who reports to Bob Thompson?'\n"
        "- 'Find all Kubernetes experts with Level 3 clearance'\n"
        "- 'What projects is Alice Johnson working on?'\n"
        "- 'Record that John Smith was promoted to Senior Engineer'\n\n"
        "I use intelligent multi-step search to answer complex questions and "
        "maintain temporal awareness of organizational changes."
    ),
    tools=[
        FunctionTool(add_hr_information),
        FunctionTool(search_hr_information),
    ],
)


# Cleanup function
async def cleanup():
    """Close the Graphiti connection."""
    global _graphiti_instance
    if _graphiti_instance:
        await _graphiti_instance.close()
        _graphiti_instance = None
