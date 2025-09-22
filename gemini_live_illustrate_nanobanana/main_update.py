
import asyncio
import json
import os
import uuid
import re
from google import genai
import base64
from google.genai import types

from websockets.server import WebSocketServerProtocol
import websockets.server
import io
import datetime
from PIL import Image
from io import BytesIO

from env_loader import load_env, require_keys

# Optional: clear proxy env vars to avoid local proxy interference (e.g., 127.0.0.1:8080)
def _clear_proxies():
    for key in [
        'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
        'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
    ]:
        os.environ.pop(key, None)

if os.getenv("CLEAR_PROXY") == "1":
    _clear_proxies()
    print("Proxy environment variables cleared due to CLEAR_PROXY=1")

# Load .env and validate required keys
load_env()
require_keys(["GOOGLE_API_KEY"]) 

# Load API key from environment
gemini_api_key = os.environ.get('GOOGLE_API_KEY', '')
MODEL = "gemini-2.0-flash-live-001"  # For multimodal
IMAGE_MODEL = "gemini-2.5-flash-image-preview"  # For image editing
PROMPT_MODEL = "gemini-2.5-flash-lite"  # For generating edit prompts

# Live API client
client = genai.Client(
  http_options={
    'api_version': 'v1beta',  # Updated API version based on reference
  }
)

# Separate client for image operations
image_client = genai.Client()

# Simple function to clean up text (only basic cleaning)
def clean_text(text):
    """Simple cleaning of text - just handle whitespace."""
    if not text:
        return ""
    # Replace multiple spaces with single space and trim
    return re.sub(r'\s+', ' ', text).strip()

async def generate_edit_prompt(image_data, response_text):
    """
    Generate an image edit prompt based on the model's response.
    
    Args:
        image_data: The original image data
        response_text: The model's text response to the user's question
    
    Returns:
        str: A prompt for editing the image, or None if no edit is needed
    """
    try:
        # Decode base64 image if it's base64-encoded
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data
            
        image = Image.open(BytesIO(image_bytes))
        
        # Create prompt generation text
        prompt_generation_text = f"""
        I'm going to show you an image and my response to a user's question about it.
        Based on my response, generate a prompt that would instruct how to annotate the image to better explain my answer.
        
        My response to the user was: {response_text}
        
        Generate a concise image editing prompt that would add helpful visual annotations.
        If my response doesn't relate to the image or doesn't require visual annotation, reply with 'NO_EDIT_NEEDED'.
        
        Image editing prompt:
        """
        
        # Use the separate image_client for content generation
        response = image_client.models.generate_content(
            model=PROMPT_MODEL,
            contents=[prompt_generation_text, image],
        )
        
        prompt = response.candidates[0].content.parts[0].text.strip()
        
        # Don't edit if the model thinks it's not needed
        if prompt == "NO_EDIT_NEEDED":
            return None
            
        return prompt
    except Exception as e:
        print(f"Error generating edit prompt: {e}")
        return None

async def chunk_timer(delay, websocket, image_for_edit, current_response_text, transcript_finalized):
    """Timer function to trigger image editing after a delay with no new chunks"""
    await asyncio.sleep(delay)
    if not transcript_finalized and image_for_edit["data"]:
        processed_text = clean_text(current_response_text)
        
        if processed_text:
            print("Generating edit prompt...")
            prompt_text = await generate_edit_prompt(base64.b64decode(image_for_edit["data"]), processed_text)
            
            if prompt_text:
                print("Editing image...")
                edited_image, explanation = await edit_image(image_for_edit["data"], prompt_text)
                
                await websocket.send(json.dumps({
                    "edited_image": {
                        "image": edited_image,
                        "mime_type": "image/png",
                        "explanation": explanation,
                        "prompt": prompt_text
                    }
                }))
                return True
    return False

async def edit_image(image_data, prompt):
    """
    Edit an image using Gemini's image API.
    
    Args:
        image_data (bytes): The image data as bytes
        prompt (str): The prompt describing the edits to make
    
    Returns:
        tuple: (edited_image_data, explanation_text)
    """
    try:
        # Decode base64 image if it's base64-encoded
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data
            
        image = Image.open(BytesIO(image_bytes))
        
        # Create edit prompt
        edit_prompt = f"Edit this screenshot: {prompt}. Add annotations like arrows, circles, highlights, or text labels to explain the content. Don't completely change the image, just annotate it clearly."
        
        # Use the separate image_client for image editing
        response = image_client.models.generate_content(
            model=IMAGE_MODEL,
            contents=[edit_prompt, image],
        )
        
        # Extract results
        explanation_text = None
        edited_image_data = None
        
        for part in response.candidates[0].content.parts:
            if part.text is not None:
                explanation_text = part.text
            elif part.inline_data is not None:
                edited_image = Image.open(BytesIO(part.inline_data.data))
                # Convert image back to base64
                buffered = BytesIO()
                edited_image.save(buffered, format="PNG")
                edited_image_data = base64.b64encode(buffered.getvalue()).decode('utf-8')
        
        return edited_image_data, explanation_text
    except Exception as e:
        print(f"Error editing image: {e}")
        return None, f"Error editing image: {str(e)}"

async def gemini_session_handler(websocket: WebSocketServerProtocol):
    print(f"Starting Gemini session")
    # Track the most recent image
    latest_image = {"data": None, "mime_type": None}
    # Track the accumulated response text
    current_response_text = ""
    # Flag to track if we're in the middle of a response
    is_responding = True  # Start as true to capture initial transcriptions
    # Flag to track if an image is being processed for editing
    is_editing_image = False
    # Flag to track if we should reset the transcript on next input
    should_reset_transcript = False
    # Simplified: finalized transcript for current turn
    transcript_finalized = False
    # Capture the image present when the first transcript chunk arrives
    first_chunk_seen = False
    image_for_edit = {"data": None, "mime_type": None}
    # Timer variables for chunk-based editing
    last_chunk_time = None
    chunk_timer_task = None
    CHUNK_TIMEOUT = 1.0  # 1 second timeout between chunks
    
    try:
        config_message = await websocket.recv()
        config_data = json.loads(config_message)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    #Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr.
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                ),
                language_code='en-US',
            ),
            system_instruction="""You are a live, multimodal tutor speaking as if annotating a shared screen or whiteboard.
            When the user refers to the on-screen image/screenshot, narrate what you would mark visually: for example,
            "I'd circle ...", "I'd draw an arrow to ...", "I'd highlight ...", and give short, stepwise explanations
            tied to visible regions ("top-right chart", "left column", "second item in the list"). Keep sentences short
            and spoken-friendly. Do not give tool commands or image-edit prompts. If the user is not asking about the
            image, answer normally and you may optionally point out where to look on the screen.""",
              
              output_audio_transcription=types.AudioTranscriptionConfig(),
              input_audio_transcription=types.AudioTranscriptionConfig(),
        )

        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print(f"Connected to Gemini API")

            async def send_to_gemini():
                nonlocal is_responding, current_response_text, should_reset_transcript, transcript_finalized, first_chunk_seen, image_for_edit
                
                try:
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            
                            # Check if we should reset transcript first
                            if should_reset_transcript:
                                current_response_text = ""
                                transcript_finalized = False
                                should_reset_transcript = False
                            
                            # Manual edit command still available
                            if "edit_latest_image" in data:
                                if latest_image["data"] is None:
                                    await websocket.send(json.dumps({
                                        "error": "No image available to edit"
                                    }))
                                    continue
                                    
                                prompt = data["edit_latest_image"]["prompt"]
                                
                                # Process image editing asynchronously
                                edited_image, explanation = await edit_image(latest_image["data"], prompt)
                                
                                # Send the edited image back to the client
                                await websocket.send(json.dumps({
                                    "edited_image": {
                                        "image": edited_image,
                                        "mime_type": "image/png",
                                        "explanation": explanation
                                    }
                                }))
                                continue
                            
                            if "realtime_input" in data:
                                for chunk in data["realtime_input"]["media_chunks"]:
                                    if chunk["mime_type"] == "audio/pcm":
                                        # Using updated API method with Blob
                                        audio_data = base64.b64decode(chunk["data"])
                                        await session.send_realtime_input(
                                            media=types.Blob(data=audio_data, mime_type='audio/pcm;rate=16000')
                                        )
                                    
                                    elif chunk["mime_type"].startswith("image/"):
                                        # Store the latest image
                                        latest_image["data"] = chunk["data"]
                                        latest_image["mime_type"] = chunk["mime_type"]
                                        
                                        # New image for this conversation; keep accumulating
                                        is_responding = True
                                        
                                        # Send to Gemini using updated API method
                                        image_data = base64.b64decode(chunk["data"])
                                        await session.send_realtime_input(
                                            media=types.Blob(data=image_data, mime_type=chunk["mime_type"])
                                        )
                            
                            elif "text" in data:
                                text_content = data["text"]
                                
                                # Reset transcript for new text input since this is a new user query
                                is_responding = True
                                current_response_text = ""
                                transcript_finalized = False
                                
                                # Use updated API method for text
                                await session.send_client_content(
                                    turns={"role": "user", "parts": [{"text": text_content}]}, 
                                    turn_complete=True
                                )
                                
                        except Exception as e:
                            print(f"Error sending to Gemini: {e}")
                            import traceback
                            traceback.print_exc()
                    print("Client connection closed (send)")
                except Exception as e:
                    print(f"Error sending to Gemini: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    print("send_to_gemini closed")

            async def receive_from_gemini():
                nonlocal current_response_text, is_responding, should_reset_transcript, transcript_finalized, first_chunk_seen, image_for_edit, last_chunk_time, chunk_timer_task
                
                # Track transcription for debugging
                transcription_chunks_received = 0
                
                try:
                    while True:
                        try:
                            print("receiving from gemini")
                            async for response in session.receive():
                                if response.server_content and hasattr(response.server_content, 'interrupted') and response.server_content.interrupted is not None:
                                    print(f"[{datetime.datetime.now()}] Generation interrupted")
                                    await websocket.send(json.dumps({"interrupted": "True"}))
                                    continue

                                if response.usage_metadata:
                                    usage = response.usage_metadata
                                    print(f'Used {usage.total_token_count} tokens in total.')

                                # Accumulate transcriptions with tracking
                                if response.server_content and hasattr(response.server_content, 'output_transcription') and response.server_content.output_transcription is not None:
                                    transcription_text = response.server_content.output_transcription.text
                                    transcription_chunks_received += 1
                                    
                                    # If we've finalized this turn, don't accumulate further
                                    if transcript_finalized:
                                        await websocket.send(json.dumps({
                                            "transcription": {
                                                "text": transcription_text,
                                                "sender": "Gemini",
                                                "finished": response.server_content.output_transcription.finished
                                            }
                                        }))
                                        continue
                                    
                                    # Capture the image as soon as we receive the first transcript chunk
                                    if transcription_text and not first_chunk_seen:
                                        if latest_image["data"]:
                                            image_for_edit["data"] = latest_image["data"]
                                            image_for_edit["mime_type"] = latest_image["mime_type"]
                                        first_chunk_seen = True
                                    
                                    # Accumulate the text and manage timer
                                    if transcription_text:
                                        current_response_text += transcription_text
                                        
                                        # Update last chunk time and reset timer
                                        last_chunk_time = datetime.datetime.now()
                                        
                                        # Cancel any existing timer
                                        if chunk_timer_task and not chunk_timer_task.done():
                                            chunk_timer_task.cancel()
                                        
                                        # Only start timer if we have an image and haven't finalized the transcript
                                        if not transcript_finalized and image_for_edit["data"]:
                                            # Start a new timer
                                            chunk_timer_task = asyncio.create_task(
                                                chunk_timer(CHUNK_TIMEOUT, websocket, image_for_edit, current_response_text, transcript_finalized)
                                            )
                                            
                                            # Add callback to set transcript_finalized when timer completes
                                            def on_timer_done(task):
                                                nonlocal transcript_finalized
                                                try:
                                                    if not task.cancelled() and task.result():
                                                        transcript_finalized = True
                                                except Exception:
                                                    pass
                                            
                                            chunk_timer_task.add_done_callback(on_timer_done)
                                    
                                    # If finished flag is True, process immediately without waiting for timer
                                    finished = response.server_content.output_transcription.finished
                                    if (not transcript_finalized and image_for_edit["data"] and finished):
                                        # Cancel any existing timer
                                        if chunk_timer_task and not chunk_timer_task.done():
                                            chunk_timer_task.cancel()
                                        
                                        processed_text = clean_text(current_response_text)
                                        if processed_text:
                                            print("Generating edit prompt...")
                                            prompt_text = await generate_edit_prompt(base64.b64decode(image_for_edit["data"]), processed_text)
                                            if prompt_text:
                                                print("Editing image...")
                                                edited_image, explanation = await edit_image(image_for_edit["data"], prompt_text)
                                                await websocket.send(json.dumps({
                                                    "edited_image": {
                                                        "image": edited_image,
                                                        "mime_type": "image/png",
                                                        "explanation": explanation,
                                                        "prompt": prompt_text
                                                    }
                                                }))
                                        transcript_finalized = True
                                    
                                    # Send to client
                                    await websocket.send(json.dumps({
                                        "transcription": {
                                            "text": transcription_text,
                                            "sender": "Gemini",
                                            "finished": response.server_content.output_transcription.finished
                                        }
                                    }))
                                    
                                if response.server_content and hasattr(response.server_content, 'input_transcription') and response.server_content.input_transcription is not None:
                                    # Process input transcription
                                    _user_chunk = response.server_content.input_transcription.text
                                    await websocket.send(json.dumps({
                                        "transcription": {
                                            "text": response.server_content.input_transcription.text,
                                            "sender": "User",
                                            "finished": response.server_content.input_transcription.finished
                                        }
                                    }))

                                if response.server_content is None:
                                    continue
                                    
                                model_turn = response.server_content.model_turn
                                if model_turn:
                                    for part in model_turn.parts:
                                        if hasattr(part, 'text') and part.text is not None:
                                            # Also accumulate the response text if not finalized
                                            if part.text and not transcript_finalized:
                                                current_response_text += part.text
                                            
                                            await websocket.send(json.dumps({"text": part.text}))
                                        
                                        elif hasattr(part, 'inline_data') and part.inline_data is not None:
                                            try:
                                                audio_data = part.inline_data.data
                                                base64_audio = base64.b64encode(audio_data).decode('utf-8')
                                                await websocket.send(json.dumps({
                                                    "audio": base64_audio,
                                                }))
                                            except Exception as e:
                                                print(f"Error processing assistant audio: {e}")

                                # When turn is complete, process the accumulated text (if we didn't already)
                                if response.server_content and response.server_content.turn_complete:
                                    # Just do minimal cleaning (trim and normalize spaces)
                                    processed_text = clean_text(current_response_text)
                                    
                                    # Final transcription complete message
                                    await websocket.send(json.dumps({
                                        "transcription": {
                                            "text": "",
                                            "sender": "Gemini",
                                            "finished": True
                                        }
                                    }))
                                    
                                    # Set flag to reset transcript on next input
                                    
                                    # Cancel any existing timer
                                    if chunk_timer_task and not chunk_timer_task.done():
                                        chunk_timer_task.cancel()
                                    
                                    should_reset_transcript = True
                                    is_responding = True
                                    transcript_finalized = False
                                    first_chunk_seen = False
                                    image_for_edit = {"data": None, "mime_type": None}
                                    last_chunk_time = None
                                    chunk_timer_task = None
                        
                        except websockets.exceptions.ConnectionClosedOK:
                            print("Client connection closed normally (receive)")
                            break
                        except Exception as e:
                            print(f"Error receiving from Gemini: {e}")
                            import traceback
                            traceback.print_exc()
                            break

                except Exception as e:
                    print(f"Error receiving from Gemini: {e}")
                    import traceback
                    traceback.print_exc()
                finally:
                    print("Gemini connection closed (receive)")

            async def process_image_edit(response_text):
                """Process image editing if we have both an image and a response"""
                nonlocal is_editing_image
                
                if latest_image["data"] is None:
                    return
                
                if is_editing_image:
                    return
                    
                is_editing_image = True
                try:
                    # Generate edit prompt based on the response
                    print("Generating edit prompt...")
                    edit_prompt = await generate_edit_prompt(latest_image["data"], response_text)
                    
                    # Only proceed if we have a meaningful edit prompt
                    if edit_prompt:
                        # For testing - skip actual image generation and just return the prompt
                        await websocket.send(json.dumps({
                            "edit_prompt": {
                                "prompt": edit_prompt,
                                "would_edit": True
                            }
                        }))
                    else:
                        await websocket.send(json.dumps({
                            "edit_prompt": {
                                "prompt": "NO_EDIT_NEEDED",
                                "would_edit": False
                            }
                        }))
                except Exception as e:
                    print(f"Error in process_image_edit: {e}")
                finally:
                    is_editing_image = False

            # Start send and receive tasks
            send_task = asyncio.create_task(send_to_gemini())
            receive_task = asyncio.create_task(receive_from_gemini())
            await asyncio.gather(send_task, receive_task)

    except Exception as e:
        print(f"Error in Gemini session: {e}")
    finally:
        print("Gemini session closed.")
    
async def main() -> None:
    # Use explicit IPv4 address and handle deprecation
    server = await websockets.server.serve(
        gemini_session_handler,
        host="0.0.0.0",  # Explicitly use IPv4 localhost
        port=9090,
        compression=None  # Disable compression to avoid deprecation warning
    )
    
    print("Running websocket server on 0.0.0.0:9090...")
    await asyncio.Future()  # Keep the server running indefinitely

if __name__ == "__main__":
    asyncio.run(main())
