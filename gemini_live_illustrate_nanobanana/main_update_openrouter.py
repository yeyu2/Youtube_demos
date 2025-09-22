import asyncio
import json
import os
import uuid
import re
import base64
from io import BytesIO
import datetime
import requests

from PIL import Image
from websockets.server import WebSocketServerProtocol
import websockets.server

from google import genai
from google.genai import types

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
require_keys(["GOOGLE_API_KEY", "OPENROUTER_API_KEY"])  # voice uses Google; edit uses OpenRouter

MODEL = "gemini-2.0-flash-live-001"  # For multimodal (voice)
PROMPT_MODEL = "gemini-2.5-flash"  # For generating edit prompts (text)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL_IMAGE = "google/gemini-2.5-flash-image-preview"

# Live API client for voice
client = genai.Client(
  http_options={
    'api_version': 'v1beta',
  }
)

# Separate client for prompt generation (text)
image_client = genai.Client()

# Simple function to clean up text (only basic cleaning)
def clean_text(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()

async def generate_edit_prompt(image_data, response_text):
    try:
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data
        image = Image.open(BytesIO(image_bytes))

        prompt_generation_text = f"""
        I'm going to show you an image and my response to a user's question about it.
        Based on my response, generate a prompt that would instruct how to annotate the image to better explain my answer.

        My response to the user was: {response_text}

        Generate a concise image editing prompt that would add helpful visual annotations.
        If my response doesn't relate to the image or doesn't require visual annotation, reply with 'NO_EDIT_NEEDED'.

        Image editing prompt:
        """

        response = image_client.models.generate_content(
            model=PROMPT_MODEL,
            contents=[prompt_generation_text, image],
        )
        prompt = response.candidates[0].content.parts[0].text.strip()
        
        if prompt == "NO_EDIT_NEEDED":
            return None
        return prompt
    except Exception as e:
        print(f"Error generating edit prompt: {e}")
        return None

# ---------- OpenRouter helpers ----------


def _or_headers():
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    referer = os.getenv("OPENROUTER_REFERER")
    title = os.getenv("OPENROUTER_TITLE")
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


def _or_decode_data_url(url: str):
    try:
        if not url.startswith("data:image"):
            return None
        comma = url.find(',')
        if comma == -1:
            return None
        b64 = url[comma + 1:]
        decoded = base64.b64decode(b64)
        return decoded
    except Exception:
        return None


def _or_parse_images(choice: dict):
    images = []
    message = choice.get("message") or {}
    content = message.get("content")
    
    if isinstance(content, list):
        for part in content:
            if part.get("type") == "image_url":
                url = (part.get("image_url") or {}).get("url")
                if not url:
                    continue
                if url.startswith("http://") or url.startswith("https://"):
                    try:
                        resp = requests.get(url, timeout=30)
                        resp.raise_for_status()
                        images.append(resp.content)
                    except Exception:
                        pass
                else:
                    data = _or_decode_data_url(url)
                    if data:
                        images.append(data)
    
    imgs = message.get("images")
    if isinstance(imgs, list):
        for img in imgs:
            url = None
            if isinstance(img.get("image_url"), dict):
                url = img["image_url"].get("url")
            elif isinstance(img.get("url"), str):
                url = img.get("url")
            
            if not url:
                continue
                
            if url.startswith("http://") or url.startswith("https://"):
                try:
                    resp = requests.get(url, timeout=30)
                    resp.raise_for_status()
                    images.append(resp.content)
                except Exception:
                    pass
            else:
                data = _or_decode_data_url(url)
                if data:
                    images.append(data)
    
    return images

# ---------- OpenRouter-backed image edit ----------


async def edit_image(image_data, prompt):
    try:
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        else:
            image_bytes = image_data

        b64 = base64.b64encode(image_bytes).decode('utf-8')
        data_url = f"data:image/png;base64,{b64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{prompt}"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]
            }
        ]
        payload = {
            "model": OPENROUTER_MODEL_IMAGE,
            "messages": messages,
        }
        resp = requests.post(OPENROUTER_API_URL, headers=_or_headers(), data=json.dumps(payload), timeout=120)
        
        if resp.status_code == 429:
            print("OpenRouter returned 429 RESOURCE_EXHAUSTED. Please slow down or check your quota.")
        resp.raise_for_status()
        data = resp.json()

        explanation_text = None
        edited_image_data = None
        for choice in data.get("choices", []):
            images = _or_parse_images(choice)
            for img_bytes in images:
                edited_image_data = base64.b64encode(img_bytes).decode('utf-8')
                break
            if edited_image_data:
                break
            
        return edited_image_data, explanation_text
    except Exception as e:
        print(f"Error editing image: {e}")
        return None, f"Error editing image: {str(e)}"

# ---------------- Voice session logic (unchanged) ----------------


async def chunk_timer(delay, websocket, image_for_edit, current_response_text, transcript_finalized):
    """Timer function to trigger image editing after a delay with no new chunks"""
    await asyncio.sleep(delay)
    if not transcript_finalized and image_for_edit["data"]:
        processed_text = clean_text(current_response_text)
        
        if processed_text:
            print(f"Generating edit prompt...")
            prompt_text = await generate_edit_prompt(base64.b64decode(image_for_edit["data"]), processed_text)
            
            if prompt_text:
                print(f"Editing image...")
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

async def gemini_session_handler(websocket: WebSocketServerProtocol):
    print(f"Starting Gemini session")
    latest_image = {"data": None, "mime_type": None}
    current_response_text = ""
    is_responding = True
    is_editing_image = False
    should_reset_transcript = False
    transcript_finalized = False
    first_chunk_seen = False
    image_for_edit = {"data": None, "mime_type": None}
    last_chunk_time = None
    chunk_timer_task = None
    CHUNK_TIMEOUT = 1.0  # 1 second timeout between chunks

    try:
        config_message = await websocket.recv()
        _ = json.loads(config_message)

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
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
                            if should_reset_transcript:
                                current_response_text = ""
                                transcript_finalized = False
                                should_reset_transcript = False

                            if "realtime_input" in data:
                                for chunk in data["realtime_input"]["media_chunks"]:
                                    if chunk["mime_type"] == "audio/pcm":
                                        await session.send_realtime_input(
                                            media=types.Blob(data=base64.b64decode(chunk["data"]), mime_type='audio/pcm;rate=16000')
                                        )
                                    elif chunk["mime_type"].startswith("image/"):
                                        latest_image["data"] = chunk["data"]
                                        latest_image["mime_type"] = chunk["mime_type"]
                                        is_responding = True
                                        await session.send_realtime_input(
                                            media=types.Blob(data=base64.b64decode(chunk["data"]), mime_type=chunk["mime_type"])
                                        )
                            elif "text" in data:
                                text_content = data["text"]
                                is_responding = True
                                current_response_text = ""
                                transcript_finalized = False
                                await session.send_client_content(
                                    turns={"role": "user", "parts": [{"text": text_content}]},
                                    turn_complete=True
                                )
                        except Exception as e:
                            print(f"Error sending to Gemini: {e}")
                    print("Client connection closed (send)")
                except Exception as e:
                    print(f"Error sending to Gemini: {e}")
                finally:
                    print("send_to_gemini closed")

            async def receive_from_gemini():
                nonlocal current_response_text, is_responding, should_reset_transcript, transcript_finalized, first_chunk_seen, image_for_edit, last_chunk_time, chunk_timer_task
                transcription_chunks_received = 0
                try:
                    while True:
                        try:
                            print("receiving from gemini")
                            async for response in session.receive():
                                if response.server_content and hasattr(response.server_content, 'interrupted') and response.server_content.interrupted is not None:
                                    await websocket.send(json.dumps({"interrupted": "True"}))
                                    continue

                                if response.server_content and hasattr(response.server_content, 'output_transcription') and response.server_content.output_transcription is not None:
                                    transcription_text = response.server_content.output_transcription.text
                                    transcription_chunks_received += 1

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

                                    finished = response.server_content.output_transcription.finished
                                    
                                    # If finished flag is True, process immediately without waiting for timer
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

                                    await websocket.send(json.dumps({
                                        "transcription": {
                                            "text": transcription_text,
                                            "sender": "Gemini",
                                            "finished": response.server_content.output_transcription.finished
                                        }
                                    }))

                                if response.server_content and hasattr(response.server_content, 'input_transcription') and response.server_content.input_transcription is not None:
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

                                if response.server_content and response.server_content.turn_complete:
                                    await websocket.send(json.dumps({
                                        "transcription": {
                                            "text": "",
                                            "sender": "Gemini",
                                            "finished": True
                                        }
                                    }))
                                    processed_text = clean_text(current_response_text)
                                    
                                    # Cancel any existing timer
                                    if chunk_timer_task and not chunk_timer_task.done():
                                        chunk_timer_task.cancel()
                                    
                                    should_reset_transcript = True
                                    is_responding = True
                                    transcript_finalized = False
                                    first_chunk_seen = False
                                    image_for_edit = {"data": None, "mime_type": None }
                                    last_chunk_time = None
                                    chunk_timer_task = None

                        except websockets.exceptions.ConnectionClosedOK:
                            break
                        except Exception as e:
                            print(f"Error receiving from Gemini: {e}")
                            break
                except Exception as e:
                    print(f"Error receiving from Gemini: {e}")
                finally:
                    print("Gemini connection closed (receive)")

            send_task = asyncio.create_task(send_to_gemini())
            receive_task = asyncio.create_task(receive_from_gemini())
            await asyncio.gather(send_task, receive_task)

    except Exception as e:
        print(f"Error in Gemini session: {e}")
    finally:
        print("Gemini session closed.")

async def main() -> None:
    server = await websockets.server.serve(
        gemini_session_handler,
        host="0.0.0.0",
        port=9090,
        compression=None
    )
    print("Running websocket server on 0.0.0.0:9090...")
    await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main()) 