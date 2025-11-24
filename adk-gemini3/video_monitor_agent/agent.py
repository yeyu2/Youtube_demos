import asyncio
import json
from typing import AsyncGenerator

from google.adk.agents import LiveRequestQueue
from google.adk.agents.llm_agent import Agent
from google.adk.tools.function_tool import FunctionTool
from google.genai import Client
from google.genai import types as genai_types
from pydantic import BaseModel, Field


class VideoAnalysisResult(BaseModel):
    """Structured result from video frame analysis."""
    observation: str = Field(description="Brief answer to the user's specific query only, ignoring irrelevant details")
    status_key: str = Field(description="A short, consistent key for the current state (e.g., 'smiling', 'not_smiling', '2_people', 'no_motion')")
    significant_change: bool = Field(description="Whether the status_key represents a significant change that user was asking to know for monitoring")


# For video streaming, `input_stream: LiveRequestQueue` is required and reserved key parameter for ADK to pass the video streams in.
async def monitor_video_stream(
    input_stream: LiveRequestQueue,
    detection_query: str = "Describe what you see in this image briefly.",
) -> AsyncGenerator[str, None]:
    """Continuously monitor the video stream and alert when the detected status changes.
    Use this for ongoing monitoring where you want to be notified of changes.
    
    Args:
        input_stream: The video stream queue from ADK.
        detection_query: What to monitor in the video frames. 
                        For example: "Are people smiling?", "Count the number of people", 
                        "Detect any motion or changes", etc.
    """
    print(f"start continuous monitoring with query: {detection_query}")
    client = Client(vertexai=False)
    prompt_text = detection_query
    last_result = None
    first_frame_received = False
    
    while True:
        last_valid_req = None
        if not first_frame_received:
            print("Waiting for video stream...")
        else:
            print("Start monitoring loop")

        # use this loop to pull the latest images and discard the old ones
        while input_stream._queue.qsize() != 0:
            live_req = await input_stream.get()

            if live_req.blob is not None and live_req.blob.mime_type == "image/jpeg":
                last_valid_req = live_req

        # If we found a valid image, process it
        if last_valid_req is not None:
            if not first_frame_received:
                print("✓ First video frame received! Starting analysis...")
                first_frame_received = True
                # Yield immediate acknowledgment before slow API call
                yield "Starting video monitoring, analyzing first frame..."
            else:
                print("Processing the most recent frame from the queue")

            # Create an image part using the blob's data and mime type
            image_part = genai_types.Part.from_bytes(
                data=last_valid_req.blob.data, mime_type=last_valid_req.blob.mime_type
            )
            
            # Build the prompt with context about previous state
            if last_result is not None:
                context_prompt = f"{prompt_text}\n\nPrevious status_key was: '{last_result}'. Compare with current state."
            else:
                context_prompt = f"{prompt_text}\n\nThis is the first frame being analyzed."

            contents = genai_types.Content(
                role="user",
                parts=[image_part, genai_types.Part.from_text(text=context_prompt)],
            )

            # Call the model to generate structured content
            response = client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    system_instruction=(
                        "You are a helpful video analysis assistant. Analyze the image ONLY for what the user asked about.\n"
                        "Provide:\n"
                        "1. observation: A brief answer to the user's specific query (ignore irrelevant details)\n"
                        "2. status_key: A short, consistent identifier for the current state (use simple values like 'yes', 'no', 'tired', 'alert', etc.)\n"
                        "3. significant_change: Compare the current status_key with the previous status_key provided in the prompt.\n"
                        "   - Set to true ONLY if the status_key has changed (e.g., 'tired' → 'alert', 'yes' → 'no')\n"
                        "   - Set to false if the status_key is the same as before (minor variations don't count)\n"
                        "   - For the first frame, set to false\n"
                        "Focus ONLY on what was asked. Be concise to save tokens."
                    ),
                    response_mime_type="application/json",
                    response_schema=VideoAnalysisResult,
                ),
            )
            
            # Parse the structured response
            result_text = response.candidates[0].content.parts[0].text
            result_data = json.loads(result_text)
            analysis = VideoAnalysisResult(**result_data)
            
            # Decide whether to yield based on model's significant_change flag
            is_first = last_result is None
            
            if is_first:
                # First detection - always report
                last_result = analysis.status_key
                yield f"Initial detection: {analysis.observation}"
                print(f"✓ YIELD - Initial detection: {analysis.observation} [status_key: {analysis.status_key}, significant_change: {analysis.significant_change}]")
            elif analysis.significant_change:
                # Model detected something significant - report it
                last_result = analysis.status_key
                yield f"Update: {analysis.observation}"
                print(f"✓ YIELD - Significant change detected: {analysis.observation} [status_key: {analysis.status_key}, significant_change: {analysis.significant_change}]")
            else:
                # No significant change - silent monitoring
                print(f"✗ SILENT - No significant change [status_key: {analysis.status_key}, significant_change: {analysis.significant_change}]: {analysis.observation}")

        await asyncio.sleep(5)


async def analyze_video_frame(
    input_stream: LiveRequestQueue,
    query: str = "What do you see in this image?",
) -> AsyncGenerator[str, None]:
    """Analyze the current video frame once and return the result immediately.
    Use this for one-time questions about what's currently visible.
    
    Args:
        input_stream: The video stream queue from ADK.
        query: The specific question to answer about the current frame.
               For example: "What am I holding?", "How many fingers am I showing?",
               "What color is my shirt?", etc.
    """
    print(f"Analyzing current frame with query: {query}")
    client = Client(vertexai=False)
    
    # Get the most recent frame
    last_valid_req = None
    while input_stream._queue.qsize() != 0:
        live_req = await input_stream.get()
        if live_req.blob is not None and live_req.blob.mime_type == "image/jpeg":
            last_valid_req = live_req
    
    if last_valid_req is not None:
        print("Analyzing the most recent frame")
        
        # Create an image part using the blob's data and mime type
        image_part = genai_types.Part.from_bytes(
            data=last_valid_req.blob.data, mime_type=last_valid_req.blob.mime_type
        )
        
        contents = genai_types.Content(
            role="user",
            parts=[image_part, genai_types.Part.from_text(text=query)],
        )
        
        # Call the model to generate content based on the provided image and prompt
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=(
                    "You are a helpful video analysis assistant. Analyze the image "
                    "and respond to the user's query accurately and concisely."
                )
            ),
        )
        result = response.candidates[0].content.parts[0].text
        yield result
        print(f"Analysis result: {result}")
    else:
        yield "No video frame available to analyze."
        print("No video frame available")


def stop_streaming(function_name: str):
    """Stop a currently running streaming function.

    Args:
        function_name: The name of the streaming function to stop (e.g., 'monitor_video_stream', 'analyze_video_frame').
    """
    print(f"Stopping streaming function: {function_name}")
    return f"Stopped {function_name}"


# Create the root agent with Gemini 3 Pro
root_agent = Agent(
    model="gemini-2.5-flash-native-audio-preview-09-2025",
    name="video_monitor_agent",
    description=(
        "An intelligent video monitoring agent powered by Gemini 3 Pro that can analyze video streams in real-time.\n\n"
        "This agent demonstrates advanced video analysis capabilities using ADK streaming tools.\n\n"
        "**Two modes of operation:**\n\n"
        "1. **Continuous Monitoring** (monitor_video_stream):\n"
        "   - Use for ongoing monitoring with alerts on status changes\n"
        "   - Examples: 'Monitor if I'm looking at the screen', 'Alert me when someone enters', 'Watch for motion'\n"
        "   - Yields updates only when significant changes are detected\n\n"
        "2. **One-Time Analysis** (analyze_video_frame):\n"
        "   - Use for specific questions about what's currently visible\n"
        "   - Examples: 'What am I holding?', 'How many fingers am I showing?', 'What color is my shirt?'\n"
        "   - Returns immediate single response\n\n"
        "The agent uses structured output and intelligent change detection to minimize unnecessary updates "
        "and provide meaningful, context-aware responses."
    ),
    tools=[
        monitor_video_stream,
        analyze_video_frame,
        FunctionTool(stop_streaming),
    ]
)
