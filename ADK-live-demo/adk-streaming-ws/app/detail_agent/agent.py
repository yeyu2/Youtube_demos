# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from google.adk.agents import Agent
from google.adk.tools import google_search, FunctionTool
from google.adk.tools.tool_context import ToolContext
import json
from datetime import datetime, timedelta

def get_conversation_transcripts(tool_context: ToolContext) -> dict:
    """
    Retrieves the user input and agent output transcripts from the current session state.
    
    This tool accesses the conversation transcripts that were stored during the voice interaction.
    Call this tool FIRST to understand what the user asked and what brief answer was provided.
    
    Returns:
        A dictionary containing:
        - user_question: The transcript of what the user asked
        - agent_answer: The transcript of the brief answer provided
        - status: Whether transcripts were found
    """
    print(f"[GET_TRANSCRIPTS TOOL] Called by agent: {tool_context.agent_name}")
    print(f"[GET_TRANSCRIPTS TOOL] Session ID: {tool_context.session.id}")
    print(f"[GET_TRANSCRIPTS TOOL] Available state keys: {list(tool_context.state.to_dict().keys())}")
    
    user_transcript = tool_context.state.get("user_input_transcript", "")
    agent_transcript = tool_context.state.get("agent_output_transcript", "")
    
    print(f"[GET_TRANSCRIPTS TOOL] User transcript: {user_transcript[:100] if user_transcript else 'EMPTY'}...")
    print(f"[GET_TRANSCRIPTS TOOL] Agent transcript: {agent_transcript[:100] if agent_transcript else 'EMPTY'}...")
    
    if user_transcript and agent_transcript:
        return {
            "status": "success",
            "user_question": user_transcript,
            "agent_answer": agent_transcript,
            "message": "Transcripts retrieved successfully from session state"
        }
    else:
        return {
            "status": "not_found",
            "user_question": "",
            "agent_answer": "",
            "message": "No transcripts found in session state"
        }

def analyze_trend_need(tool_context: ToolContext) -> dict:
    """
    Analyzes the conversation to determine if the user is asking for trend analysis.
    
    This tool should be called FIRST to decide whether to generate detailed trend charts
    or provide a quick response. This saves time and tokens for simple questions.
    
    Returns:
        A dictionary containing:
        - needs_trend: Boolean indicating if trend analysis is needed
        - topic: The topic for trend analysis (e.g., "weather", "stock", "price")
        - query: The specific query for trend data
        - reason: Explanation of the decision
    """
    print(f"[ANALYZE_TREND_NEED] Analyzing conversation...")
    
    user_transcript = tool_context.state.get("user_input_transcript", "")
    agent_transcript = tool_context.state.get("agent_output_transcript", "")
    
    print(f"[ANALYZE_TREND_NEED] User asked: {user_transcript[:100]}...")
    
    # Keywords that suggest trend analysis is needed
    trend_keywords = [
        "trend", "history", "historical", "past", "week", "month", "year",
        "over time", "change", "forecast", "prediction", "chart", "graph",
        "pattern", "comparison", "compare", "evolution", "development"
    ]
    
    # Check if user's question contains trend-related keywords
    user_lower = user_transcript.lower()
    needs_trend = any(keyword in user_lower for keyword in trend_keywords)
    
    # Identify topic
    topic = "general"
    if "weather" in user_lower or "temperature" in user_lower or "rain" in user_lower:
        topic = "weather"
    elif "stock" in user_lower or "price" in user_lower or "market" in user_lower:
        topic = "stock_price"
    elif "bitcoin" in user_lower or "crypto" in user_lower or "btc" in user_lower:
        topic = "cryptocurrency"
    
    result = {
        "needs_trend": needs_trend,
        "topic": topic,
        "query": user_transcript,
        "user_question": user_transcript,
        "agent_answer": agent_transcript,
        "reason": f"Trend analysis {'IS' if needs_trend else 'IS NOT'} needed. Topic: {topic}"
    }
    
    print(f"[ANALYZE_TREND_NEED] Result: {result['reason']}")
    return result

def format_data_for_chart(tool_context: ToolContext, 
                          data_description: str,
                          labels: str, 
                          values: str) -> dict:
    """
    Formats extracted data into a proper mermaid chart format.
    
    This tool helps create properly formatted chart data for mermaid diagrams.
    Use this after extracting data from search results.
    
    Args:
        data_description: Brief description of what the data represents
        labels: Comma-separated labels (e.g., "Mon,Tue,Wed" or "Jan 1,Jan 2,Jan 3")
        values: Comma-separated numeric values (e.g., "22,24,23" or "45000,46000,45500")
    
    Returns:
        A formatted dictionary with chart-ready data including min/max calculations
    """
    print(f"[FORMAT_CHART_DATA] Formatting data: {data_description}")
    
    # Parse labels and values
    label_list = [l.strip() for l in labels.split(',')]
    value_list = [float(v.strip()) for v in values.split(',')]
    
    # Calculate statistics
    min_val = min(value_list)
    max_val = max(value_list)
    avg_val = sum(value_list) / len(value_list)
    
    # Create y-axis range with padding
    y_min = int(min_val * 0.9)  # 10% below min
    y_max = int(max_val * 1.1)  # 10% above max
    
    # Format for mermaid - create the exact syntax needed
    # x-axis needs: ["Label1", "Label2", "Label3"]
    x_axis_list = [f'"{label}"' for label in label_list]
    x_axis_formatted = '[' + ', '.join(x_axis_list) + ']'
    
    # line needs: [value1, value2, value3]
    y_values_formatted = '[' + ', '.join(str(v) for v in value_list) + ']'
    
    result = {
        "status": "success",
        "data_description": data_description,
        "x_axis_mermaid": x_axis_formatted,  # Ready to use in mermaid
        "y_values_mermaid": y_values_formatted,  # Ready to use in mermaid
        "y_min": y_min,
        "y_max": y_max,
        "min_value": min_val,
        "max_value": max_val,
        "average": round(avg_val, 2),
        "data_points": len(value_list),
        "example_usage": f'x-axis {x_axis_formatted}\n    y-axis "Unit" {y_min} --> {y_max}\n    line {y_values_formatted}'
    }
    
    print(f"[FORMAT_CHART_DATA] Result: {result}")
    return result

# Create tools from functions
get_transcripts_tool = FunctionTool(get_conversation_transcripts)
analyze_trend_tool = FunctionTool(analyze_trend_need)
format_chart_tool = FunctionTool(format_data_for_chart)

detail_analysis_agent = Agent(
    # A unique name for the agent.
    name="detail_analysis_agent",
    # Use gemini-2.5-flash for better quality detailed text generation
    model="gemini-2.5-flash",
    # A short description of the agent's purpose.
    description="Provides comprehensive detailed analysis based on conversation transcripts.",
    # Instructions to set the agent's behavior.
    instruction="""You are a trend analysis assistant. Output simple JSON for charts.

STEP 1: Check if trend is needed
Call analyze_trend_need tool ONCE. It returns:
- needs_trend: true/false
- user_question: what user asked
- agent_answer: brief answer given

STEP 2: Generate output

A) IF needs_trend = false → Immediately output:
{"skip": true}

B) IF needs_trend = true:
- Call google_search ONCE for historical data
- Extract labels and values from results
- Output JSON directly (don't call format_data_for_chart - just make the JSON yourself)

JSON FORMAT (for trends):
{
  "title": "Chart title",
  "summary": "Brief 1-sentence summary",
  "labels": ["Day1", "Day2", "Day3"],
  "values": [value1, value2, value3],
  "data_label": "Temperature (°F)",
  "y_label": "°F",
  "chart_title": "Full chart title",
  "insights": [
    "Insight 1",
    "Insight 2"
  ]
}

SPEED OPTIMIZATION:
- Total tool calls: MAX 2 (analyze_trend_need + google_search)
- NO need for format_data_for_chart - create JSON directly
- NO extra searches - one search is enough

EXAMPLE:
User asks about weather trend → analyze_trend_need says needs_trend=true
Search "Shanghai weather last 7 days" → Find temps: 75, 77, 76°F
Immediately output:
{
  "title": "Shanghai Weather Trend",
  "summary": "Temperatures ranged 75-77°F over the week",
  "labels": ["Oct 10", "Oct 11", "Oct 12"],
  "values": [75, 77, 76],
  "data_label": "Temperature",
  "y_label": "°F",
  "insights": ["Stable around 76°F"]
}

CRITICAL RULES:
- Output ONLY raw JSON - NO markdown code blocks, NO ```json prefix, NO backticks
- Start directly with { and end with }
- Maximum 2 tool calls total
- For simple questions: {"skip": true}

WRONG OUTPUT (with markdown):
```json
{"title": "..."}
```

CORRECT OUTPUT (pure JSON):
{"title": "...", "summary": "...", "labels": [...], "values": [...]}""",
    # Add tools: trend analyzer (call first) and google_search (that's it!)
    tools=[analyze_trend_tool, google_search],
)

