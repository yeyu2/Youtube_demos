import asyncio
import json
import websockets
import base64
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline, AutoModelForCausalLM
from transformers import TextIteratorStreamer, GenerationConfig
import numpy as np
import logging
import sys
import io
from PIL import Image
import time
import os
from datetime import datetime
from threading import Thread
import re
# Import Kokoro TTS library
from kokoro import KPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Add compatibility for Python < 3.10 where anext is not available
try:
    anext
except NameError:
    async def anext(iterator):
        """Get the next item from an async iterator, or raise StopAsyncIteration."""
        try:
            return await iterator.__anext__()
        except StopAsyncIteration:
            raise

class AudioSegmentDetector:
    """Detects speech segments based on audio energy levels"""
    
    def __init__(self, 
                 sample_rate=16000,
                 energy_threshold=0.02,
                 silence_duration=0.8,
                 min_speech_duration=0.8,
                 max_speech_duration=15): 
        
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_samples = int(silence_duration * sample_rate)
        self.min_speech_samples = int(min_speech_duration * sample_rate)
        self.max_speech_samples = int(max_speech_duration * sample_rate)
        
        # Internal state
        self.audio_buffer = bytearray()
        self.is_speech_active = False
        self.silence_counter = 0
        self.speech_start_idx = 0
        self.lock = asyncio.Lock()
        self.segment_queue = asyncio.Queue()
        
        # Counters
        self.segments_detected = 0
        
        # Add TTS playback and generation control
        self.tts_playing = False
        self.tts_lock = asyncio.Lock()
        self.current_generation_task = None
        self.current_tts_task = None
        self.task_lock = asyncio.Lock()
    
    async def set_tts_playing(self, is_playing):
        """Set TTS playback state"""
        async with self.tts_lock:
            self.tts_playing = is_playing
    
    async def cancel_current_tasks(self):
        """Cancel any ongoing generation and TTS tasks"""
        async with self.task_lock:
            if self.current_generation_task and not self.current_generation_task.done():
                logger.info("Cancelling current generation task due to interrupt")
                self.current_generation_task.cancel()
                try:
                    await self.current_generation_task
                except asyncio.CancelledError:
                    logger.info("Generation task successfully cancelled")
                    pass
                self.current_generation_task = None
            
            if self.current_tts_task and not self.current_tts_task.done():
                logger.info("Cancelling current TTS task due to interrupt")
                self.current_tts_task.cancel()
                try:
                    await self.current_tts_task
                except asyncio.CancelledError:
                    logger.info("TTS task successfully cancelled")
                    pass
                self.current_tts_task = None
            
            # Clear TTS playing state
            await self.set_tts_playing(False)
            logger.info("TTS playing state cleared after interrupt")
    
    async def set_current_tasks(self, generation_task=None, tts_task=None):
        """Set current generation and TTS tasks"""
        async with self.task_lock:
            self.current_generation_task = generation_task
            self.current_tts_task = tts_task
    
    async def add_audio(self, audio_bytes):
        """Add audio data to the buffer and check for speech segments"""
        async with self.lock:
            # Add new audio to buffer regardless of TTS state
            self.audio_buffer.extend(audio_bytes)
            
            # Convert recent audio to numpy for energy analysis
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Calculate audio energy (root mean square)
            if len(audio_array) > 0:
                energy = np.sqrt(np.mean(audio_array**2))
                
                # Speech detection logic
                if not self.is_speech_active and energy > self.energy_threshold:
                    # Speech start detected
                    self.is_speech_active = True
                    self.speech_start_idx = max(0, len(self.audio_buffer) - len(audio_bytes))
                    self.silence_counter = 0
                    logger.info(f"Speech start detected (energy: {energy:.6f})")
                    
                elif self.is_speech_active:
                    if energy > self.energy_threshold:
                        # Continued speech
                        self.silence_counter = 0
                    else:
                        # Potential end of speech
                        self.silence_counter += len(audio_array)
                        
                        # Check if enough silence to end speech segment
                        if self.silence_counter >= self.silence_samples:
                            speech_end_idx = len(self.audio_buffer) - self.silence_counter
                            speech_segment = bytes(self.audio_buffer[self.speech_start_idx:speech_end_idx])
                            
                            # Reset for next speech detection
                            self.is_speech_active = False
                            self.silence_counter = 0
                            
                            # Trim buffer to keep only recent audio
                            self.audio_buffer = self.audio_buffer[speech_end_idx:]
                            
                            # Only process if speech segment is long enough
                            if len(speech_segment) >= self.min_speech_samples * 2:  # × 2 for 16-bit
                                self.segments_detected += 1
                                logger.info(f"Speech segment detected: {len(speech_segment)/2/self.sample_rate:.2f}s")
                                
                                # If TTS is playing or generation is ongoing, cancel them
                                async with self.tts_lock:
                                    if self.tts_playing:
                                        logger.info("Detected speech segment during TTS playback - triggering interrupt flow")
                                        await self.cancel_current_tasks()
                                
                                # Add to queue
                                await self.segment_queue.put(speech_segment)
                                logger.info(f"Added speech segment to queue (queue size: {self.segment_queue.qsize()})")
                                return speech_segment
                            
                        # Check if speech segment exceeds maximum duration
                        elif (len(self.audio_buffer) - self.speech_start_idx) > self.max_speech_samples * 2:
                            speech_segment = bytes(self.audio_buffer[self.speech_start_idx:
                                                             self.speech_start_idx + self.max_speech_samples * 2])
                            # Update start index for next segment
                            self.speech_start_idx += self.max_speech_samples * 2
                            self.segments_detected += 1
                            logger.info(f"Max duration speech segment: {len(speech_segment)/2/self.sample_rate:.2f}s")
                            
                            # If TTS is playing or generation is ongoing, cancel them
                            async with self.tts_lock:
                                if self.tts_playing:
                                    await self.cancel_current_tasks()
                            
                            # Add to queue
                            await self.segment_queue.put(speech_segment)
                            return speech_segment
            
            return None
    
    async def get_next_segment(self):
        """Get the next available speech segment"""
        try:
            return await asyncio.wait_for(self.segment_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

class Phi4MultimodalProcessor:
    """Handles multimodal generation using Phi 4 model"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        # Use GPU for generation
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device for Phi-4: {self.device}")
        
        # Load model and processor
        model_id = "microsoft/phi-4-multimodal-instruct"
        logger.info(f"Loading {model_id}...")
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        
        # Load model
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            trust_remote_code=True,
            torch_dtype='auto',
            _attn_implementation='flash_attention_2',
        ).to(self.device)
        
        # Load generation config
        self.generation_config = GenerationConfig.from_pretrained(model_id)
        
        logger.info("Phi-4 model ready for multimodal generation")
        
        # Define prompt components
        self.system_tag = '<|system|>'
        self.system_end_tag = '<|end|>'
        self.user_tag = '<|user|>'
        self.user_end_tag = '<|end|>'
        self.assistant_tag = '<|assistant|>'
        
        # System instruction for conversational responses
        self.system_instruction = """You are a helpful multimodal assistant. You have three important responsibilities:
For meaningful speech: When the audio contains actual questions or commands, respond in natural, conversational language that sounds fluent when spoken.
Style: For valid queries, respond in a friendly, helpful tone. Your responses should be clear, concise, and easy to understand when heard rather than read. """
        
        # Cache for most recent image and audio
        self.last_image = None
        self.last_audio = None
        self.last_image_timestamp = 0
        self.lock = asyncio.Lock()
        
        # Message history management
        self.message_history = []
        self.max_history_messages = 4  # Keep last 4 exchanges (2 user, 2 assistant)
        
        # Counter
        self.generation_count = 0
        
        # Track raw audio for conversation
        self.last_audio_text = None
    
    async def set_image(self, image_data):
        """Cache the most recent image received"""
        async with self.lock:
            try:
                # Convert image data to PIL Image
                image = Image.open(io.BytesIO(image_data))
                
                # Resize to 75% of original size
                new_size = (int(image.size[0] * 0.75), int(image.size[1] * 0.75))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
                
                # Clear message history when new image is set
                self.message_history = []
                self.last_image = image
                self.last_image_timestamp = time.time()
                return True
            except Exception as e:
                logger.error(f"Error processing image: {e}")
                return False
    
    async def process_audio(self, audio_bytes, text_placeholder="Process this audio with the image context"):
        """Process audio input and generate response"""
        if not self.last_image:
            logger.warning("No image available for multimodal generation")
            return None, "No image available for multimodal generation"
        
        # Convert audio bytes to numpy array
        try:
            # Convert PCM bytes to numpy array for compatibility with Phi-4
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            # Store the sample rate
            sample_rate = 16000  # The standard rate used in our system
            self.last_audio = (audio_array, sample_rate)
            
            # Store placeholder for history tracking since we don't have transcription
            self.last_audio_text = "[Audio Input]"
        except Exception as e:
            logger.error(f"Error processing audio bytes: {e}")
            return None, f"Error processing audio: {str(e)}"
        
        return await self.generate_streaming(text_placeholder)
    
    async def generate_streaming(self, text_query, initial_chunks=3):
        """Generate a response using the latest image and text input with streaming"""
        async with self.lock:
            try:
                if not self.last_image:
                    logger.warning("No image available for multimodal generation")
                    return None, "No image available", False
                
                # Create the prompt with proper format
                custom_prompt = """Answer the question in the audio based on the image in detail description.
                If it's noise or background sounds, reply EXACTLY with 'NOISE_DETECTED', or 'NO_SPEECH'."""

                # Format using the correct structure for Phi-4
                prompt = f'{self.system_tag}{self.system_instruction}{self.system_end_tag}'
                prompt += f'{self.user_tag}<|audio_1|>{custom_prompt}<|image_1|>{self.user_end_tag}'
                prompt += f'{self.assistant_tag}'
                
                logger.info(f"Generated prompt: {prompt}")
                
                # Prepare inputs for the model
                inputs = self.processor(
                    text=prompt, 
                    audios=[self.last_audio], 
                    images=[self.last_image], 
                    return_tensors='pt'
                ).to(self.device)
                
                # Get the token length of the input to skip in the output
                input_len = inputs["input_ids"].shape[-1]
                
                # Create a streamer for token-by-token generation
                streamer = TextIteratorStreamer(
                    tokenizer=self.processor, 
                    skip_special_tokens=True, 
                    skip_prompt=True,  # Add this to skip the prompt
                    clean_up_tokenization_spaces=False
                )
                
                # Configure generation parameters
                generation_kwargs = dict(
                    **inputs,
                    max_new_tokens=1200,
                    generation_config=self.generation_config,
                    streamer=streamer,
                )
                
                # Start generation in a separate thread
                thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
                thread.start()
                
                # Collect initial text until we have a complete sentence or enough content
                initial_text = ""
                min_chars = 50  # Minimum characters to collect for initial chunk
                sentence_end_pattern = re.compile(r'[.!?]')
                has_sentence_end = False
                initial_collection_stopped_early = False # Flag to check if we broke early
                
                # Collect the first sentence or minimum character count
                for chunk in streamer:
                    initial_text += chunk
                    logger.info(f"Streaming chunk: '{chunk}'")
                    
                    # Check if we have a sentence end
                    if sentence_end_pattern.search(chunk):
                        has_sentence_end = True
                        # If we have at least some content, break after sentence end
                        if len(initial_text) >= min_chars / 2:
                            initial_collection_stopped_early = True
                            break
                    
                    # If we have enough content, break
                    if len(initial_text) >= min_chars and (has_sentence_end or "," in initial_text):
                        initial_collection_stopped_early = True
                        break
                    
                    # Safety check - if we've collected a lot of text without sentence end
                    if len(initial_text) >= min_chars * 2:
                        initial_collection_stopped_early = True
                        break
                
                # Return initial text and the streamer for continued generation
                self.generation_count += 1
                logger.info(f"Phi-4 initial generation: '{initial_text}' ({len(initial_text)} chars)")
                
                # Store user message and initial response
                self.pending_user_message = text_query
                self.pending_response = initial_text
                
                # Check if the response indicates noise detection
                noise_indicators = ["NOISE_DETECTED", "NO_SPEECH"]
                is_noise = any(initial_text.strip() == indicator for indicator in noise_indicators)
                
                if is_noise:
                    logger.info(f"Noise detected in audio: '{initial_text}'. Skipping TTS processing.")
                    # Update history with the noise detection but don't process TTS
                    self.update_history_with_complete_response(
                        "[Audio Input - Noise]", initial_text
                    )
                    # Return with noise indication
                    return streamer, f"NOISE:{initial_text}", initial_collection_stopped_early
                
                return streamer, initial_text, initial_collection_stopped_early
                
            except Exception as e:
                logger.error(f"Phi-4 streaming generation error: {e}")
                return None, f"Error processing: {text_query}", False
                
    def update_history_with_complete_response(self, audio_placeholder, initial_response, remaining_text=None):
        """Update message history with complete response, including any remaining text"""
        # Combine initial and remaining text if available
        complete_response = initial_response
        if remaining_text:
            complete_response = initial_response + remaining_text
        
        # Add to history for context in future exchanges
        self.message_history.append({
            "role": "user",
            "text": audio_placeholder
        })
        
        self.message_history.append({
            "role": "assistant",
            "text": complete_response
        })
        
        # Trim history to keep only recent messages
        if len(self.message_history) > self.max_history_messages:
            self.message_history = self.message_history[-self.max_history_messages:]
        
        logger.info(f"Updated message history with complete response ({len(complete_response)} chars)")

class KokoroTTSProcessor:
    """Handles text-to-speech conversion using Kokoro model"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        logger.info("Initializing Kokoro TTS processor...")
        try:
            # Initialize Kokoro TTS pipeline with Chinese
            self.pipeline = KPipeline(lang_code='a')
            
            # Set voice
            self.default_voice = 'af_sarah'
            
            logger.info("Kokoro TTS processor initialized successfully")
            # Counter
            self.synthesis_count = 0
        except Exception as e:
            logger.error(f"Error initializing Kokoro TTS: {e}")
            self.pipeline = None
    
    async def synthesize_initial_speech(self, text):
        """Convert initial text to speech using Kokoro TTS with minimal splitting for speed"""
        if not text or not self.pipeline:
            return None
        
        try:
            logger.info(f"Synthesizing initial speech for text: '{text}'")
            
            # Run TTS in a thread pool to avoid blocking
            audio_segments = []
            
            # Use the executor to run the TTS pipeline with minimal splitting
            # For initial text, we want to process it quickly with minimal splits
            generator = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.pipeline(
                    text, 
                    voice=self.default_voice, 
                    speed=1, 
                    split_pattern=None  # No splitting for initial text to process faster
                )
            )
            
            # Process all generated segments
            for gs, ps, audio in generator:
                audio_segments.append(audio)
            
            # Combine all audio segments
            if audio_segments:
                combined_audio = np.concatenate(audio_segments)
                self.synthesis_count += 1
                logger.info(f"Initial speech synthesis complete: {len(combined_audio)} samples")
                return combined_audio
            return None
            
        except Exception as e:
            logger.error(f"Initial speech synthesis error: {e}")
            return None
    
    async def synthesize_remaining_speech(self, text):
        """Convert remaining text to speech using Kokoro TTS with optimized splitting for responsive streaming"""
        if not text or not self.pipeline:
            return None
        
        try:
            logger.info(f"Synthesizing chunk speech for text: '{text[:50]}...' if len(text) > 50 else text")
            
            # Run TTS in a thread pool to avoid blocking
            audio_segments = []
            
            # Determine appropriate split pattern based on text length
            # For shorter chunks, use minimal splitting to process faster
            if len(text) < 100:
                split_pattern = None  # No splitting for very short chunks
            else:
                # Use appropriate punctuation for sentence-level splitting
                split_pattern = r'[.!?。！？]+'
            
            # Use the executor to run the TTS pipeline with optimized splitting
            generator = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.pipeline(
                    text, 
                    voice=self.default_voice, 
                    speed=1, 
                    split_pattern=split_pattern
                )
            )
            
            # Process all generated segments
            for gs, ps, audio in generator:
                audio_segments.append(audio)
            
            # Combine all audio segments
            if audio_segments:
                combined_audio = np.concatenate(audio_segments)
                self.synthesis_count += 1
                logger.info(f"Chunk speech synthesis complete: {len(combined_audio)} samples")
                return combined_audio
            return None
            
        except Exception as e:
            logger.error(f"Chunk speech synthesis error: {e}")
            return None
    
    async def synthesize_speech(self, text):
        """Convert text to speech using Kokoro TTS (legacy method)"""
        if not text or not self.pipeline:
            return None
        
        try:
            logger.info(f"Synthesizing speech for text: '{text[:50]}...' if len(text) > 50 else text")
            
            # Run TTS in a thread pool to avoid blocking
            audio_segments = []
            
            # Use the executor to run the TTS pipeline
            # Updated split pattern to include Chinese punctuation marks
            generator = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.pipeline(
                    text, 
                    voice=self.default_voice, 
                    speed=1, 
                    split_pattern=r'[.!?。！？]+'  # Added Chinese punctuation marks
                )
            )
            
            # Process all generated segments
            for gs, ps, audio in generator:
                audio_segments.append(audio)
            
            # Combine all audio segments
            if audio_segments:
                combined_audio = np.concatenate(audio_segments)
                self.synthesis_count += 1
                logger.info(f"Speech synthesis complete: {len(combined_audio)} samples")
                return combined_audio
            return None
            
        except Exception as e:
            logger.error(f"Speech synthesis error: {e}")
            return None

async def collect_remaining_text(streamer, chunk_size=80):
    """Collect remaining text from the streamer in smaller chunks
    
    Args:
        streamer: The text streamer object
        chunk_size: Maximum characters per chunk before yielding
        
    Yields:
        Text chunks as they become available
    """
    current_chunk = ""
    
    if streamer:
        try:
            for chunk in streamer:
                current_chunk += chunk
                logger.info(f"Collecting remaining text chunk: '{chunk}'")
                
                # Check if we've reached a good breaking point (sentence end)
                if (len(current_chunk) >= chunk_size and 
                    (current_chunk.endswith('.') or current_chunk.endswith('!') or 
                     current_chunk.endswith('?') or '.' in current_chunk[-15:])):
                    logger.info(f"Yielding text chunk of length {len(current_chunk)}")
                    yield current_chunk
                    current_chunk = ""
            
            # Yield any remaining text
            if current_chunk:
                logger.info(f"Yielding final text chunk of length {len(current_chunk)}")
                yield current_chunk
                
        except asyncio.CancelledError:
            # If there's text collected before cancellation, yield it
            if current_chunk:
                logger.info(f"Yielding partial text chunk before cancellation: {len(current_chunk)} chars")
                yield current_chunk
            raise

async def handle_client(websocket):
    """Handles WebSocket client connection"""
    try:
        # Receive initial configuration
        await websocket.recv()
        logger.info("Client connected")

        # Initialize speech detection and get instance of processors
        detector = AudioSegmentDetector()
        phi4_processor = Phi4MultimodalProcessor.get_instance()
        tts_processor = KokoroTTSProcessor.get_instance()

        # Add keepalive task
        async def send_keepalive():
            while True:
                try:
                    await websocket.ping()
                    await asyncio.sleep(10)  # Send ping every 10 seconds
                except Exception:
                    break

        async def detect_speech_segments():
            while True:
                try:
                    # Get next segment from queue
                    speech_segment = await detector.get_next_segment()
                    if speech_segment:
                        logger.info(f"Processing new speech segment from queue ({len(speech_segment)/2/16000:.2f}s)")

                        # Set TTS playing flag and start new generation workflow
                        # We set this early, but will clear it if it's noise
                        await detector.set_tts_playing(True)
                        logger.info("Tentatively set TTS playing flag, starting generation workflow")

                        try:
                            # Create generation task - directly pass audio to Phi-4
                            logger.info("Creating new Phi-4 generation task for speech segment")
                            generation_task = asyncio.create_task(
                                phi4_processor.process_audio(speech_segment)
                            )

                            # Store the generation task
                            await detector.set_current_tasks(generation_task=generation_task)
                            logger.info("Generation task registered in detector")

                            # Wait for initial generation
                            try:
                                logger.info("Awaiting initial text generation from Phi-4")
                                streamer, initial_text, initial_collection_stopped_early = await generation_task
                                logger.info(f"Received initial text generation: '{initial_text[:30]}...' ({len(initial_text)} chars), Stopped early: {initial_collection_stopped_early}")

                                # Check if the response indicates noise detection
                                if initial_text.startswith("NOISE:"):
                                    logger.info(f"Noise detected in audio: '{initial_text}'. Skipping TTS processing and interrupt.")
                                    # Clear TTS playing flag as it was just noise
                                    await detector.set_tts_playing(False)
                                    await detector.set_current_tasks() # Clear tasks
                                    continue # Skip the rest of the processing for this segment

                                # If we reach here, it means the audio was NOT noise.
                                # Now is the correct time to send the interrupt.
                                logger.info("Sending interrupt signal as speech is confirmed (not noise)")
                                interrupt_message = json.dumps({"interrupt": True})
                                await websocket.send(interrupt_message)
                                logger.info(f"Interrupt message sent: {interrupt_message}")

                            except asyncio.CancelledError:
                                logger.info("Generation cancelled - likely due to newer speech detection before analysis completed")
                                # Ensure TTS flag is cleared if generation was cancelled before noise check
                                await detector.set_tts_playing(False)
                                continue

                            # Proceed with TTS only if initial_text is valid (not None and not noise)
                            if initial_text:
                                # Create TTS task for initial speech
                                logger.info("Creating TTS task for initial speech")
                                tts_task = asyncio.create_task(
                                    tts_processor.synthesize_initial_speech(initial_text)
                                )

                                # Store the TTS task (overwriting previous generation task reference)
                                await detector.set_current_tasks(tts_task=tts_task)
                                logger.info("TTS task registered in detector")

                                try:
                                    # Wait for initial audio synthesis
                                    logger.info("Awaiting initial audio synthesis")
                                    initial_audio = await tts_task
                                    logger.info(f"Initial audio synthesis complete: {len(initial_audio) if initial_audio is not None else 0} samples")

                                    if initial_audio is not None:
                                        # Convert to base64 and send to client
                                        audio_bytes = (initial_audio * 32767).astype(np.int16).tobytes()
                                        base64_audio = base64.b64encode(audio_bytes).decode('utf-8')

                                        # Log audio size for debugging
                                        logger.info(f"Sending initial audio: {len(audio_bytes)} bytes")

                                        # Send the initial audio to the client
                                        await websocket.send(json.dumps({
                                            "audio": base64_audio
                                        }))
                                        logger.info("Initial audio sent to client")

                                        # Only process remaining chunks if initial collection didn't exhaust the stream
                                        if initial_collection_stopped_early:
                                            logger.info("Starting chunked text processing because initial collection stopped early.")
                                            collected_chunks = []

                                            try:
                                                # Create an async iterator from the generator function
                                                text_iterator = collect_remaining_text(streamer)

                                                # Process text chunks as they become available
                                                while True:
                                                    try:
                                                        # Get the next chunk with appropriate error handling
                                                        text_chunk = await anext(text_iterator)
                                                        logger.info(f"Processing text chunk: '{text_chunk[:50]}...' ({len(text_chunk)} chars)")
                                                        collected_chunks.append(text_chunk)

                                                        # Create TTS task for this text chunk
                                                        logger.info(f"Creating TTS task for text chunk of {len(text_chunk)} chars")
                                                        chunk_tts_task = asyncio.create_task(
                                                            tts_processor.synthesize_remaining_speech(text_chunk)
                                                        )

                                                        # Store the TTS task
                                                        await detector.set_current_tasks(tts_task=chunk_tts_task)
                                                        logger.info("Chunk TTS task registered in detector")

                                                        # Wait for audio synthesis for this chunk
                                                        logger.info("Awaiting chunk audio synthesis")
                                                        chunk_audio = await chunk_tts_task
                                                        logger.info(f"Chunk audio synthesis complete: {len(chunk_audio) if chunk_audio is not None else 0} samples")

                                                        if chunk_audio is not None:
                                                            # Convert to base64 and send to client
                                                            audio_bytes = (chunk_audio * 32767).astype(np.int16).tobytes()
                                                            base64_audio = base64.b64encode(audio_bytes).decode('utf-8')

                                                            # Log audio size for debugging
                                                            logger.info(f"Sending chunk audio: {len(audio_bytes)} bytes")

                                                            # Send this chunk audio to the client
                                                            await websocket.send(json.dumps({
                                                                "audio": base64_audio
                                                            }))
                                                            logger.info("Chunk audio sent to client")

                                                    except StopAsyncIteration:
                                                        # No more chunks available, we're done
                                                        logger.info("All text chunks processed")
                                                        break

                                                    except asyncio.CancelledError:
                                                        logger.info("Text processing cancelled")
                                                        raise # Re-raise to be caught by outer handler

                                                    except Exception as e:
                                                        logger.error(f"Error processing text chunk: {e}")
                                                        # Continue with next chunk if possible
                                                        continue

                                                # Log completion of chunk processing
                                                logger.info("Finished processing all text chunks.")

                                                # When all chunks are processed, update history with complete response
                                                if collected_chunks:
                                                    complete_remaining_text = "".join(collected_chunks)
                                                    phi4_processor.update_history_with_complete_response(
                                                        "[Audio Input]", initial_text, complete_remaining_text
                                                    )
                                                    logger.info(f"Updated history with complete response of {len(initial_text) + len(complete_remaining_text)} chars")

                                            except asyncio.CancelledError:
                                                # If text collection is cancelled, update history with what we have
                                                logger.info("Remaining text collection cancelled - updating history with partial response")
                                                if collected_chunks:
                                                    partial_remaining_text = "".join(collected_chunks)
                                                    phi4_processor.update_history_with_complete_response(
                                                        "[Audio Input]", initial_text, partial_remaining_text
                                                    )
                                                else:
                                                    # Only initial text was generated before cancellation
                                                    phi4_processor.update_history_with_complete_response(
                                                        "[Audio Input]", initial_text
                                                    )
                                                logger.info("Remaining text collection cancelled - likely new speech detected")
                                                continue # Jump out of the initial TTS try block

                                        else:
                                            # Streamer was likely exhausted, just update history with initial text
                                            logger.info("Skipping chunked text processing as streamer was likely exhausted.")
                                            phi4_processor.update_history_with_complete_response(
                                                "[Audio Input]", initial_text
                                            )

                                        # Signal end of audio stream to client (always send after processing is done)
                                        logger.info("Sending end of audio stream signal to client.")
                                        await websocket.send(json.dumps({"audio_complete": True}))

                                except asyncio.CancelledError:
                                    # If initial TTS is cancelled, still update history
                                    logger.info("Initial TTS cancelled - updating history with initial text")
                                    phi4_processor.update_history_with_complete_response(
                                        "[Audio Input]", initial_text
                                    )
                                    logger.info("Initial TTS cancelled - likely new speech detected")
                                    continue # Skip to next segment detection loop

                        except websockets.exceptions.ConnectionClosed:
                            logger.info("WebSocket connection closed during speech processing")
                            break
                        except Exception as e:
                            logger.error(f"Error in speech processing: {e}")
                        finally:
                            # Clear TTS playing flag and tasks at the end of processing a valid speech segment
                            # Or if an error occurred after the noise check
                            logger.info("Clearing TTS playing flag and tasks at end of processing or error")
                            await detector.set_tts_playing(False)
                            await detector.set_current_tasks()
                            logger.info("Speech processing cycle complete for this segment")

                    await asyncio.sleep(0.01) # Small sleep to prevent tight loop when queue is empty
                except websockets.exceptions.ConnectionClosed:
                    logger.info("WebSocket connection closed during speech detection loop")
                    break
                except Exception as e:
                    logger.error(f"Error in detect_speech_segments loop: {e}")
                    logger.info("Clearing TTS playing flag and tasks due to error in detection loop")
                    # Ensure state is reset even if an error occurs in the loop logic
                    await detector.set_tts_playing(False)
                    await detector.set_current_tasks()
                    await asyncio.sleep(0.1) # Avoid rapid error loops

        async def receive_audio_and_images():
            async for message in websocket:
                try:
                    data = json.loads(message)

                    # Handle audio data
                    if "realtime_input" in data:
                        for chunk in data["realtime_input"]["media_chunks"]:
                            if chunk["mime_type"] == "audio/pcm":
                                audio_data = base64.b64decode(chunk["data"])
                                await detector.add_audio(audio_data)
                            # Only process image if TTS is not playing
                            elif chunk["mime_type"] == "image/jpeg":
                                tts_is_playing = False
                                async with detector.tts_lock:
                                    tts_is_playing = detector.tts_playing
                                if not tts_is_playing:
                                    image_data = base64.b64decode(chunk["data"])
                                    await phi4_processor.set_image(image_data)

                    # Only process standalone image if TTS is not playing
                    if "image" in data:
                         tts_is_playing = False
                         async with detector.tts_lock:
                             tts_is_playing = detector.tts_playing
                         if not tts_is_playing:
                            image_data = base64.b64decode(data["image"])
                            await phi4_processor.set_image(image_data)

                except websockets.exceptions.ConnectionClosed:
                    logger.info("WebSocket connection closed during receive loop")
                    break # Exit the receive loop
                except Exception as e:
                    logger.error(f"Error receiving data: {e}")
                    # Decide if we should break or continue based on error type
                    if isinstance(e, (json.JSONDecodeError, KeyError)):
                        logger.warning("Ignoring malformed message.")
                    else:
                        # For other errors, maybe break the loop
                        break

        # Run tasks concurrently
        # Use asyncio.wait to handle task completion and potential errors gracefully
        receive_task = asyncio.create_task(receive_audio_and_images())
        detect_task = asyncio.create_task(detect_speech_segments())
        keepalive_task = asyncio.create_task(send_keepalive())

        done, pending = await asyncio.wait(
            [receive_task, detect_task, keepalive_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel pending tasks if one task finishes (e.g., connection closed)
        for task in pending:
            task.cancel()
            try:
                await task # Allow cancellation to propagate
            except asyncio.CancelledError:
                pass # Expected

        # Log results of completed tasks if needed (e.g., exceptions)
        for task in done:
            try:
                result = task.result()
            except Exception as e:
                logger.error(f"Task {task.get_name()} finished with error: {e}")

    except websockets.exceptions.ConnectionClosed as cc:
        logger.info(f"Connection closed: Code={cc.code}, Reason='{cc.reason}'")
    except Exception as e:
        logger.error(f"Session error: {e}", exc_info=True) # Log traceback for unexpected errors
    finally:
        logger.info("Client disconnected, ensuring TTS flag is cleared.")
        # Ensure TTS playing flag is cleared when connection ends, regardless of how
        # Need to get the detector instance potentially created within the try block
        # This part is tricky if detector wasn't initialized due to early error.
        # A better approach might be to pass detector instance around or handle cleanup differently.
        # For now, assuming detector was likely initialized if we reach finally from within the main try.
        if 'detector' in locals():
             await detector.set_tts_playing(False)
             await detector.cancel_current_tasks() # Also cancel any lingering tasks

async def main():
    """Main function to start the WebSocket server"""
    try:
        # Initialize processors ahead of time to load models
        phi4_processor = Phi4MultimodalProcessor.get_instance()
        tts_processor = KokoroTTSProcessor.get_instance()
        
        logger.info("Starting WebSocket server on 0.0.0.0:9073")
        # Add ping_interval and ping_timeout parameters
        async with websockets.serve(
            handle_client, 
            "0.0.0.0", 
            9073,
            ping_interval=20,    # Send ping every 20 seconds
            ping_timeout=60,     # Wait up to 60 seconds for pong response
            close_timeout=10     # Wait up to 10 seconds for close handshake
        ):
            logger.info("WebSocket server running on 0.0.0.0:9073")
            await asyncio.Future()  # Run forever
    except Exception as e:
        logger.error(f"Server error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
