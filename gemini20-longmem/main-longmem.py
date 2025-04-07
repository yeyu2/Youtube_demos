import asyncio
import json
import os
import uuid
from google import genai
import base64
from mem0 import Memory
from websockets.server import WebSocketServerProtocol  # Updated import
import websockets.server
import io
from pydub import AudioSegment
import google.generativeai as generative
import wave
import datetime


# Load API key from environment
os.environ['GOOGLE_API_KEY'] = ''
gemini_api_key = os.environ['GOOGLE_API_KEY']
MODEL = "gemini-2.0-flash-exp"  # For multimodal

client = genai.Client(
  http_options={
    'api_version': 'v1alpha',
  }
)

config = {
    "embedder": {
        "provider": "gemini",
        "config": {
            "model": "models/gemini-embedding-exp-03-07",
        }
    },
    "llm": {
        "provider": "gemini",
        "config": {
            "model": "gemini-2.0-flash",
            "temperature": 0.1,
            "max_tokens": 2048,
        }
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "embedding_model_dims": 768,
            "host": "localhost",
            "port": 6333,
        }
    }
}
memory = Memory.from_config(config)

# Use a fixed user ID for testing
FIXED_USER_ID = "test_user_123"

def get_user_id(session_id):
    """Return the fixed user ID for all sessions."""
    return FIXED_USER_ID

def add_to_memory(messages, user_id, metadata=None):
    """Add conversation to memory and return memory ID, handling only the assistant role."""
    if metadata is None:
        metadata = {"category": "tutoring_session"}
    print(f"Adding to memory: {messages}, user_id: {user_id}, metadata: {metadata}")
    result = memory.add(messages, user_id=user_id, metadata=metadata)
    print(f"Added memory: {result}")
    return result.get("id") if result else None

def query_memory(query, user_id):
    """Search for relevant memories based on the query."""
    response = memory.search(query=query, user_id=user_id)
    
    # Handle the correct result structure with 'results' key
    if isinstance(response, dict) and "results" in response:
        result_memories = response["results"]
    else:
        # Fallback handling if structure is different
        result_memories = response if isinstance(response, list) else []
    
    return result_memories

# Define the tool (function) for memory querying
tool_query_memory = {
    "function_declarations": [
        {
            "name": "query_memory",
            "description": "Query the memory database to retrieve relevant past interactions with the user.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "query": {
                        "type": "STRING",
                        "description": "The query string to search the memory."
                    }
                },
                "required": ["query"]
            }
        }
    ]
}

async def gemini_session_handler(websocket: WebSocketServerProtocol):
    try:
        session_id = str(uuid.uuid4())
        user_id = get_user_id(session_id)
        current_conversation = []
        
        config_message = await websocket.recv()
        config_data = json.loads(config_message)
        config = config_data.get("setup", {})

        config["system_instruction"] = """You are a helpful math tutor. Before answering any questions, you MUST first use the query_memory tool to check if we have discussed similar topics or concepts before with this student.

        If relevant past discussions are found:
        1. Reference the previous context to maintain continuity in the tutoring
        2. Build upon previously explained concepts
        3. Remind the student of relevant points we covered before

        If no relevant past discussions are found:
        1. Start with foundational explanations
        2. Break down complex concepts into simpler parts
        3. Use clear examples and step-by-step solutions

        Always be patient, encouraging, and adapt your explanations based on the student's demonstrated understanding from past interactions. Focus on helping the student develop strong mathematical intuition and problem-solving skills.

        """
        config["tools"] = [tool_query_memory]
        
        # Initialize audio buffers and control flags
        has_user_audio = False
        user_audio_buffer = b''
        has_assistant_audio = False
        assistant_audio_buffer = b''
        should_accumulate_user_audio = True  # Control flag for user audio accumulation

        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print(f"Connected to Gemini API for user {user_id}")

            async def send_to_gemini():
                nonlocal has_user_audio, user_audio_buffer, should_accumulate_user_audio
                try:
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            
                            if "realtime_input" in data:
                                for chunk in data["realtime_input"]["media_chunks"]:
                                    # Handle audio input
                                    if chunk["mime_type"] == "audio/pcm":
                                        # Only accumulate if we should
                                        if should_accumulate_user_audio:
                                            try:
                                                # Ensure we get binary data from the base64 input
                                                audio_chunk = base64.b64decode(chunk["data"])
                                                has_user_audio = True
                                                user_audio_buffer += audio_chunk
                                                #print(f"Added {len(audio_chunk)} bytes to user audio buffer. Total: {len(user_audio_buffer)}")
                                            except Exception as e:
                                                print(f"Error processing audio chunk: {e}")
                                        #else:
                                            #print("Skipping audio accumulation while assistant is responding")
                                        
                                        # Always send to Gemini regardless of accumulation
                                        await session.send(input={
                                            "mime_type": "audio/pcm",
                                            "data": chunk["data"]
                                        })
                                    
                                    # Handle image input
                                    elif chunk["mime_type"].startswith("image/"):
                                        current_conversation.append({
                                            "role": "user", 
                                            "content": "[Image shared by user]"
                                        })
                                        
                                        await session.send(input={
                                            "mime_type": chunk["mime_type"],
                                            "data": chunk["data"]
                                        })
                            
                            # Handle text input
                            elif "text" in data:
                                text_content = data["text"]
                                current_conversation.append({
                                    "role": "user", 
                                    "content": text_content
                                })
                                
                                await session.send(input={
                                    "mime_type": "text/plain",
                                    "data": text_content
                                })
                                
                        except Exception as e:
                            print(f"Error sending to Gemini: {e}")
                    print("Client connection closed (send)")
                except Exception as e:
                    print(f"Error sending to Gemini: {e}")
                finally:
                    print("send_to_gemini closed")

            async def receive_from_gemini():
                nonlocal has_assistant_audio, assistant_audio_buffer, has_user_audio, user_audio_buffer, should_accumulate_user_audio
                try:
                    while True:
                        try:
                            print("receiving from gemini")
                            async for response in session.receive():
                                if response.server_content is None:
                                    if response.tool_call is not None:
                                        print(f"Tool call received: {response.tool_call}")

                                        function_calls = response.tool_call.function_calls
                                        function_responses = []

                                        for function_call in function_calls:
                                            name = function_call.name
                                            args = function_call.args
                                            call_id = function_call.id

                                            # Handle memory query tool
                                            if name == "query_memory":
                                                try:
                                                    # Get memories from the updated query_memory function
                                                    memories = query_memory(args["query"], user_id)
                                                    # Sort memories by score and get top 3
                                                    sorted_memories = sorted(memories, key=lambda x: x['score'], reverse=True)[:10]
                                                    
                                                    # Create readable summary from top memories
                                                    memory_points = [mem['memory'] for mem in sorted_memories]
                                                    memory_summary = "Memory summary: " + "; ".join(memory_points)
                                                    # Format the response with the expected structure
                                                    function_responses.append(
                                                        {
                                                            "id": call_id,
                                                            "name": name,
                                                            "response": {"result": memory_summary}
                                                        }
                                                    ) 
                                                    
                                                    # Log memory retrieval but don't display to user
                                                    print(f"Memory retrieved: {json.dumps(memories)}")
                                                except Exception as e:
                                                    print(f"Error querying memory: {e}")
                                                    continue

                                        # Send function response back to Gemini
                                        if function_responses:
                                            print(f"Sending function response: {function_responses}")
                                            await session.send(input=function_responses)
                                    continue  # Skip the rest of the loop for this iteration

                                # Only process model_turn if server_content is not None
                                model_turn = response.server_content.model_turn
                                if model_turn:
                                    for part in model_turn.parts:
                                        if hasattr(part, 'text') and part.text is not None:
                                            await websocket.send(json.dumps({"text": part.text}))
                                            current_text = part.text
                                        
                                        elif hasattr(part, 'inline_data') and part.inline_data is not None:
                                            try:
                                                # Stop user audio accumulation when assistant starts responding with audio
                                                should_accumulate_user_audio = False
                                                
                                                # Get the raw binary audio data
                                                audio_data = part.inline_data.data
                                                
                                                # Base64 encode for the client
                                                base64_audio = base64.b64encode(audio_data).decode('utf-8')
                                                await websocket.send(json.dumps({
                                                    "audio": base64_audio,
                                                }))
                                                
                                                # Accumulate assistant's audio (raw binary)
                                                has_assistant_audio = True
                                                assistant_audio_buffer += audio_data
                                            except Exception as e:
                                                print(f"Error processing assistant audio: {e}")

                                if response.server_content and response.server_content.turn_complete:
                                    print('\n<Turn complete>')
                                    user_text = None
                                    assistant_text = None
                                    
                                    # Start transcription process
                                    transcription_tasks = []
                                    
                                    # Transcribe user's audio if present
                                    if has_user_audio and user_audio_buffer:
                                        try:
                                            # Convert user audio with 16kHz sample rate
                                            user_wav_base64 = convert_pcm_to_wav(user_audio_buffer, is_user_input=True)
                                            if user_wav_base64:
                                                user_text = transcribe_audio(user_wav_base64)
                                                print(f"Transcribed user audio: {user_text}")
                                            else:
                                                print("User audio conversion failed")
                                                user_text = "User audio could not be processed."
                                        except Exception as e:
                                            print(f"Error processing user audio: {e}")
                                            user_text = "User audio processing error."
                                    
                                    # Transcribe assistant's audio if present
                                    if has_assistant_audio and assistant_audio_buffer:
                                        try:
                                            # Convert assistant audio with 24kHz sample rate
                                            assistant_wav_base64 = convert_pcm_to_wav(assistant_audio_buffer, is_user_input=False)
                                            if assistant_wav_base64:
                                                assistant_text = transcribe_audio(assistant_wav_base64)
                                                if assistant_text:    
                                                    await websocket.send(json.dumps({
                                                        "text": assistant_text
                                                    }))
                                            else:
                                                print("Assistant audio conversion failed")
                                                assistant_text = "Assistant audio could not be processed."
                                        except Exception as e:
                                            print(f"Error processing assistant audio: {e}")
                                            assistant_text = "Assistant audio processing error."
                                    
                                    # Add to memory if we have both parts of the conversation
                                    if user_text and assistant_text:
                                        messages = [
                                            {"role": "user", "content": user_text},
                                            {"role": "assistant", "content": assistant_text}
                                        ]
                                        add_to_memory(messages, user_id)
                                        print('\n<Turn complete, memory updated>')
                                    else:
                                        print("Skipping memory update: Missing user or assistant text")
                                    
                                    # Reset audio states and buffers
                                    has_user_audio = False
                                    user_audio_buffer = b''
                                    has_assistant_audio = False
                                    assistant_audio_buffer = b''
                                    
                                    # Re-enable user audio accumulation for the next turn
                                    should_accumulate_user_audio = True
                                    print("Re-enabling user audio accumulation for next turn")
                        except websockets.exceptions.ConnectionClosedOK:
                            print("Client connection closed normally (receive)")
                            break
                        except Exception as e:
                            print(f"Error receiving from Gemini: {e}")
                            break

                except Exception as e:
                    print(f"Error receiving from Gemini: {e}")
                finally:
                    print("Gemini connection closed (receive)")

            # Start send and receive tasks
            send_task = asyncio.create_task(send_to_gemini())
            receive_task = asyncio.create_task(receive_from_gemini())
            await asyncio.gather(send_task, receive_task)

    except Exception as e:
        print(f"Error in Gemini session: {e}")
    finally:
        print("Gemini session closed.")

def transcribe_audio(audio_data):
    """Transcribes audio using Gemini 1.5 Flash."""
    try:
        # Make sure we have valid audio data
        if not audio_data:
            return "No audio data received."
        
        # Check if the input is already a base64 string
        if isinstance(audio_data, str):
            wav_audio_base64 = audio_data
        else:
            # This is binary data that needs conversion
            return "Invalid audio data format."
            
        # Create a client specific for transcription
        transcription_client = generative.GenerativeModel(model_name="gemini-2.0-flash-lite")
        
        prompt = """Generate a transcript of the speech. 
        Please do not include any other text in the response. 
        If you cannot hear the speech, please only say '<Not recognizable>'."""
        
        response = transcription_client.generate_content(
            [
                prompt,
                {
                    "mime_type": "audio/wav", 
                    "data": base64.b64decode(wav_audio_base64),
                }
            ]
        )
            
        return response.text

    except Exception as e:
        print(f"Transcription error: {e}")
        return "Transcription failed."

def convert_pcm_to_wav(pcm_data, is_user_input=False):
    """Converts PCM audio to base64 encoded WAV."""
    try:
        # Ensure we're working with binary data
        if not isinstance(pcm_data, bytes):
            print(f"PCM data is not bytes, it's {type(pcm_data)}")
            try:
                # Try to convert to bytes if it's not already
                if isinstance(pcm_data, str):
                    # If it's a base64 string, decode it
                    pcm_data = base64.b64decode(pcm_data)
            except Exception as e:
                print(f"Error converting PCM data to bytes: {e}")
                return None

        # Create a WAV in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000 if is_user_input else 24000)  # 16kHz for user input, 24kHz for assistant
            wav_file.writeframes(pcm_data)
        
        # Reset buffer position
        wav_buffer.seek(0)
        
        # Convert to base64
        wav_base64 = base64.b64encode(wav_buffer.getvalue()).decode('utf-8')
        return wav_base64
        
    except Exception as e:
        print(f"Error converting PCM to WAV: {e}")
        return None
    
async def main() -> None:
    # Use explicit IPv4 address and handle deprecation
    server = await websockets.server.serve(
        gemini_session_handler,
        host="0.0.0.0",  # Explicitly use IPv4 localhost
        port=9084,
        compression=None  # Disable compression to avoid deprecation warning
    )
    
    print("Running websocket server on 0.0.0.0:9084...")
    print("Long memory tutoring assistant ready to help")
    await asyncio.Future()  # Keep the server running indefinitely

if __name__ == "__main__":
    asyncio.run(main())
