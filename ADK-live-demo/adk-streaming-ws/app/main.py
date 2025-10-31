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

import os
import json
import asyncio
import base64
import warnings
import logging

from pathlib import Path
from dotenv import load_dotenv

from google.genai.types import (
    Part,
    Content,
    Blob,
)

from google.adk.runners import InMemoryRunner, Runner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.genai import types

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.websockets import WebSocketDisconnect

from google_search_agent.agent import live_agent
from detail_agent.agent import detail_analysis_agent
from google.adk.agents import SequentialAgent

# Suppress warnings
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
warnings.filterwarnings("ignore", message="there are non-text parts in the response")

# Reduce ADK logging verbosity (suppress "non-text parts" warnings)
logging.getLogger('google.genai').setLevel(logging.ERROR)
logging.getLogger('google.adk').setLevel(logging.ERROR)

#
# ADK Streaming
#

# Load Gemini API Key
load_dotenv()

APP_NAME = "ADK Streaming example"

# Note on Multi-Agent Architecture:
# We use a hybrid approach because:
# - Live agent requires run_live() for audio streaming (not compatible with SequentialAgent)
# - Detail agent uses regular run() for text generation
# Solution: Manual sequential orchestration with shared session state
# Pattern: Live Agent (streaming) -> Detail Agent (triggered on completion)
# Communication: Both agents share session.state for transcript passing

root_agent = live_agent


async def start_agent_session(user_id, is_audio=False):
    """Starts an agent session"""

    # Create a Runner (we'll reuse this for both live and detail agents)
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=root_agent,
    )

    # Create a Session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,  # Replace with actual user ID
    )

    # Set response modalities - AUDIO only is sufficient for transcript
    if is_audio:
        modalities = ["AUDIO"]  # AUDIO modality with output_audio_transcription provides both audio and transcript
    else:
        modalities = ["TEXT"]  # Text only for text mode
    
    # Configure RunConfig with audio transcription
    
    run_config = RunConfig(
        response_modalities=modalities,
        # Enable transcription for agent's speech output
        output_audio_transcription=types.AudioTranscriptionConfig() if is_audio else None,
        # Enable transcription for user's speech input
        input_audio_transcription=types.AudioTranscriptionConfig() if is_audio else None,
    )

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue, session, runner


async def agent_to_client_messaging(websocket, live_events, session, is_audio, runner):
    """Agent to client communication"""
    # Accumulators for full transcripts
    full_input_transcript = ""
    full_output_transcript = ""
    
    async for event in live_events:
        # Check for input transcription (transcript of user's audio speech)
        if event.input_transcription:
            # input_transcription might be an object with a 'text' attribute
            if hasattr(event.input_transcription, 'text'):
                input_text = event.input_transcription.text
            else:
                input_text = str(event.input_transcription)
            
            if input_text:
                # Accumulate full transcript
                full_input_transcript += input_text
                
                message = {
                    "mime_type": "text/plain",
                    "data": input_text,
                    "partial": event.partial,
                    "is_input_transcript": True
                }
                await websocket.send_text(json.dumps(message))
                print(f"[USER INPUT TRANSCRIPT]: {input_text}")
        
        # Check for output transcription (transcript of agent's audio speech)
        if event.output_transcription:
            # output_transcription might be an object with a 'text' attribute
            if hasattr(event.output_transcription, 'text'):
                transcript_text = event.output_transcription.text
            else:
                transcript_text = str(event.output_transcription)
            
            if transcript_text:
                # Accumulate full transcript
                full_output_transcript += transcript_text
                
                message = {
                    "mime_type": "text/plain",
                    "data": transcript_text,
                    "partial": event.partial,
                    "is_output_transcript": True
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT OUTPUT TRANSCRIPT]: {transcript_text}")

        # If the turn complete or interrupted, trigger detail agent
        if event.turn_complete or event.interrupted:
            message = {
                "turn_complete": event.turn_complete,
                "interrupted": event.interrupted,
            }
            await websocket.send_text(json.dumps(message))
            print(f"[AGENT TO CLIENT]: {message}")
            
            # Trigger detail analysis agent if we have transcripts and in audio mode
            if is_audio and full_input_transcript and full_output_transcript:
                try:
                    print(f"[DETAIL AGENT] Storing transcripts in session state...")
                    print(f"  User input: {full_input_transcript[:100]}...")
                    print(f"  Agent output: {full_output_transcript[:100]}...")
                    
                    # Store transcripts in session state for detail agent to access
                    session.state["user_input_transcript"] = full_input_transcript
                    session.state["agent_output_transcript"] = full_output_transcript
                    
                    print(f"[DETAIL AGENT] Creating separate runner and new session...")
                    
                    # Create a separate InMemoryRunner for detail agent
                    detail_runner = InMemoryRunner(
                        app_name=APP_NAME,
                        agent=detail_analysis_agent,
                    )
                    
                    # Create a NEW session for detail agent with initial state
                    detail_session = await detail_runner.session_service.create_session(
                        app_name=APP_NAME,
                        user_id=session.user_id,
                        # Initialize the session with the transcripts in state
                        state={
                            "user_input_transcript": full_input_transcript,
                            "agent_output_transcript": full_output_transcript,
                        }
                    )
                    
                    print(f"[DETAIL AGENT] Created detail session with ID: {detail_session.id}")
                    print(f"[DETAIL AGENT] Detail session state keys: {list(detail_session.state.keys())}")
                    print(f"[DETAIL AGENT] Verifying state contents:")
                    print(f"  - user_input_transcript: {detail_session.state.get('user_input_transcript', 'NOT FOUND')[:50]}...")
                    print(f"  - agent_output_transcript: {detail_session.state.get('agent_output_transcript', 'NOT FOUND')[:50]}...")
                    
                    # Create a simple user message asking agent to analyze the conversation
                    # The agent will use its get_conversation_transcripts tool to read from state
                    user_message = Content(
                        role="user",
                        parts=[Part(text="Please provide a detailed analysis of the conversation.")]
                    )
                    
                    # Run detail agent with its own clean session
                    detail_events = detail_runner.run(
                        session_id=detail_session.id,
                        user_id=detail_session.user_id,
                        new_message=user_message,
                    )
                    
                    print(f"[DETAIL AGENT] Streaming events...")
                    
                    # Stream the detailed response to client (runner.run() returns sync generator)
                    for detail_event in detail_events:
                        if detail_event.content and detail_event.content.parts:
                            for part in detail_event.content.parts:
                                if part.text:
                                    message = {
                                        "mime_type": "application/json",
                                        "data": part.text,
                                        "partial": detail_event.partial,
                                        "is_detailed_analysis": True
                                    }
                                    await websocket.send_text(json.dumps(message))
                                    print(f"[DETAIL AGENT OUTPUT]: {part.text[:100]}...")
                    
                    print(f"[DETAIL AGENT] Completed successfully")
                    
                except WebSocketDisconnect:
                    # Client disconnected, stop processing
                    print(f"[DETAIL AGENT] Client disconnected during detail analysis")
                    raise  # Re-raise to properly close the websocket
                except Exception as e:
                    print(f"[DETAIL AGENT ERROR]: {e}")
                    import traceback
                    traceback.print_exc()
                
                finally:
                    # Reset transcripts for next turn
                    full_input_transcript = ""
                    full_output_transcript = ""
            
            continue

        # Read the Content and its first Part
        part: Part = (
            event.content and event.content.parts and event.content.parts[0]
        )
        if not part:
            continue

        # If it's audio, send Base64 encoded audio data
        is_audio = part.inline_data and part.inline_data.mime_type.startswith("audio/pcm")
        if is_audio:
            audio_data = part.inline_data and part.inline_data.data
            if audio_data:
                message = {
                    "mime_type": "audio/pcm",
                    "data": base64.b64encode(audio_data).decode("ascii")
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")
                continue

        # If it's text (partial or complete), send it
        if part.text:
            message = {
                "mime_type": "text/plain",
                "data": part.text,
                "partial": event.partial,
                "is_transcript": False  # This is regular text, not transcript
            }
            await websocket.send_text(json.dumps(message))
            print(f"[AGENT TO CLIENT]: text/plain: {part.text[:100]}...")


async def client_to_agent_messaging(websocket, live_request_queue):
    """Client to agent communication"""
    try:
        while True:
            # Decode JSON message
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]

            # Send the message to the agent
            if mime_type == "text/plain":
                # Send a text message
                content = Content(role="user", parts=[Part.from_text(text=data)])
                live_request_queue.send_content(content=content)
                print(f"[CLIENT TO AGENT]: {data}")
            elif mime_type == "audio/pcm":
                # Send an audio data
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
            else:
                raise ValueError(f"Mime type not supported: {mime_type}")
    except WebSocketDisconnect:
        print("[CLIENT TO AGENT] WebSocket disconnected (normal)")
    except Exception as e:
        print(f"[CLIENT TO AGENT ERROR]: {e}")


#
# FastAPI web app
#

app = FastAPI()

STATIC_DIR = Path("static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serves the index.html"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: int, is_audio: str):
    """Client websocket endpoint"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{user_id} connected, audio mode: {is_audio}")

    # Start agent session
    user_id_str = str(user_id)
    is_audio_mode = (is_audio == "true")
    live_events, live_request_queue, session, runner = await start_agent_session(user_id_str, is_audio_mode)

    # Start tasks
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events, session, is_audio_mode, runner)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )

    # Wait until the websocket is disconnected or an error occurs
    try:
        tasks = [agent_to_client_task, client_to_agent_task]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Check if any task had an exception (other than WebSocketDisconnect)
        for task in done:
            try:
                task.result()
            except WebSocketDisconnect:
                # Normal disconnection, not an error
                pass
            except Exception as e:
                print(f"[WEBSOCKET ERROR] Task failed: {e}")
    finally:
        # Close LiveRequestQueue
        live_request_queue.close()
        
        # Disconnected
        print(f"Client #{user_id} disconnected")
