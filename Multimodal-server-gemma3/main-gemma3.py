import asyncio
import json
import websockets
import base64
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline, AutoProcessor, Gemma3ForConditionalGeneration
import numpy as np
import logging
import sys
import io
from PIL import Image
import time
import os
from datetime import datetime
# Import Kokoro TTS library
from kokoro import KPipeline
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

class AudioSegmentDetector:
    """Detects speech segments based on audio energy levels"""
    
    def __init__(self, 
                 sample_rate=16000,
                 energy_threshold=0.015,
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
                self.current_generation_task.cancel()
                try:
                    await self.current_generation_task
                except asyncio.CancelledError:
                    pass
                self.current_generation_task = None
            
            if self.current_tts_task and not self.current_tts_task.done():
                self.current_tts_task.cancel()
                try:
                    await self.current_tts_task
                except asyncio.CancelledError:
                    pass
                self.current_tts_task = None
            
            # Clear TTS playing state
            await self.set_tts_playing(False)
    
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
                                        await self.cancel_current_tasks()
                                
                                # Add to queue
                                await self.segment_queue.put(speech_segment)
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

class WhisperTranscriber:
    """Handles speech transcription using Whisper large-v3 model with pipeline"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        # Use GPU for transcription
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device: {self.device}")
        
        # Set torch dtype based on device
        self.torch_dtype = torch.float16 if self.device != "cpu" else torch.float32
        
        # Load model and processor
        model_id = "openai/whisper-large-v3-turbo"
        logger.info(f"Loading {model_id}...")
        
        # Load model
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id, 
            torch_dtype=self.torch_dtype,
            low_cpu_mem_usage=True, 
            use_safetensors=True
        )
        self.model.to(self.device)
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(model_id)
        
        # Create pipeline
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=self.model,
            tokenizer=self.processor.tokenizer,
            feature_extractor=self.processor.feature_extractor,
            torch_dtype=self.torch_dtype,
            device=self.device,
        )
        
        logger.info("Whisper model ready for transcription")
        
        # Counter
        self.transcription_count = 0
    
    async def transcribe(self, audio_bytes, sample_rate=16000):
        """Transcribe audio bytes to text using the pipeline"""
        try:
            # Convert PCM bytes to numpy array
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Check for valid audio
            if len(audio_array) < 1000:  # Too short
                return ""
            
            # Use the pipeline to transcribe
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.pipe(
                    {"array": audio_array, "sampling_rate": sample_rate},
                    generate_kwargs={
                        "task": "transcribe",
                        "language": "english",
                        "temperature": 0.0
                    }
                )
            )
            
            # Extract the text from the result
            text = result.get("text", "").strip()
            
            self.transcription_count += 1
            logger.info(f"Transcription result: '{text}'")
            
            return text
                
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return ""

class GemmaMultimodalProcessor:
    """Handles multimodal generation using Gemma 3 model"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        # Use GPU for generation
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device for Gemma: {self.device}")
        
        # Load model and processor
        model_id = "google/gemma-3-4b-it"
        logger.info(f"Loading {model_id}...")
        
        # Load model with 8-bit quantization for memory efficiency
        self.model = Gemma3ForConditionalGeneration.from_pretrained(
            model_id,
            device_map="auto",
            load_in_8bit=True,  # Enable 8-bit quantization
            torch_dtype=torch.bfloat16
        )
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(model_id)
        
        logger.info("Gemma model ready for multimodal generation")
        
        # Cache for most recent image
        self.last_image = None
        self.last_image_timestamp = 0
        self.lock = asyncio.Lock()
        
        # Message history management
        self.message_history = []
        self.max_history_messages = 4  # Keep last 4 exchanges (2 user, 2 assistant)
        
        # Counter
        self.generation_count = 0
    
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
    
    def _build_messages(self, text):
        """Build messages array with history for the model"""
        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": """You are a helpful assistant providing spoken 
                responses about images and engaging in natural conversation. Keep your responses concise, 
                fluent, and conversational. Use natural oral language that's easy to listen to.

                When responding:
                1. If the user's question or comment is clearly about the image, provide a relevant,
                   focused response about what you see.
                2. If the user's input is not clearly related to the image or lacks context:
                   - Don't force image descriptions into your response
                   - Respond naturally as in a normal conversation
                   - If needed, politely ask for clarification (e.g., "Could you please be more specific 
                     about what you'd like to know about the image?")
                3. Keep responses concise:
                   - Aim for 2-3 short sentences
                   - Focus on the most relevant information
                   - Use conversational language
                
                Maintain conversation context and refer to previous exchanges naturally when relevant.
                If the user's request is unclear, ask them to repeat or clarify in a friendly way."""}]
            }
        ]
        
        # Add conversation history
        messages.extend(self.message_history)
        
        # Add current user message with image
        messages.append({
            "role": "user",
            "content": [
                {"type": "image", "image": self.last_image},
                {"type": "text", "text": text}
            ]
        })
        
        return messages
    
    def _update_history(self, user_text, assistant_response):
        """Update message history with new exchange"""
        # Add user message
        self.message_history.append({
            "role": "user",
            "content": [{"type": "text", "text": user_text}]
        })
        
        # Add assistant response
        self.message_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": assistant_response}]
        })
        
        # Trim history to keep only recent messages
        if len(self.message_history) > self.max_history_messages:
            self.message_history = self.message_history[-self.max_history_messages:]
                
    async def generate_streaming(self, text, initial_chunks=3):
        """Generate a response using the latest image and text input with streaming for initial chunks"""
        async with self.lock:
            try:
                if not self.last_image:
                    logger.warning("No image available for multimodal generation")
                    return None, f"No image context: {text}"
                
                # Build messages with history
                messages = self._build_messages(text)
                
                # Prepare inputs for the model
                inputs = self.processor.apply_chat_template(
                    messages, 
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt"
                ).to(self.model.device)
                
                input_len = inputs["input_ids"].shape[-1]
                
                # Create a streamer for token-by-token generation
                from transformers import TextIteratorStreamer
                from threading import Thread
                
                streamer = TextIteratorStreamer(
                    self.processor.tokenizer,
                    skip_special_tokens=True,
                    skip_prompt=True
                )
                
                # Start generation in a separate thread
                generation_kwargs = dict(
                    **inputs,
                    max_new_tokens=128,
                    do_sample=True,
                    temperature=0.7,
                    use_cache=True,
                    streamer=streamer,
                )
                
                thread = Thread(target=self.model.generate, kwargs=generation_kwargs)
                thread.start()
                
                # Collect initial text until we have a complete sentence or enough content
                initial_text = ""
                min_chars = 50  # Minimum characters to collect for initial chunk
                sentence_end_pattern = re.compile(r'[.!?]')
                has_sentence_end = False
                
                # Collect the first sentence or minimum character count
                for chunk in streamer:
                    initial_text += chunk
                    
                    # Check if we have a sentence end
                    if sentence_end_pattern.search(chunk):
                        has_sentence_end = True
                        # If we have at least some content, break after sentence end
                        if len(initial_text) >= min_chars / 2:
                            break
                    
                    # If we have enough content, break
                    if len(initial_text) >= min_chars and (has_sentence_end or "," in initial_text):
                        break
                    
                    # Safety check - if we've collected a lot of text without sentence end
                    if len(initial_text) >= min_chars * 2:
                        break
                
                # Return initial text and the streamer for continued generation
                self.generation_count += 1
                logger.info(f"Gemma initial generation: '{initial_text}' ({len(initial_text)} chars)")
                
                # Don't update history yet - wait for complete response
                # Store user message for later
                self.pending_user_message = text
                self.pending_response = initial_text
                
                return streamer, initial_text
                
            except Exception as e:
                logger.error(f"Gemma streaming generation error: {e}")
                return None, f"Error processing: {text}"

    def _update_history_with_complete_response(self, user_text, initial_response, remaining_text=None):
        """Update message history with complete response, including any remaining text"""
        # Combine initial and remaining text if available
        complete_response = initial_response
        if remaining_text:
            complete_response = initial_response + remaining_text
        
        # Add user message
        self.message_history.append({
            "role": "user",
            "content": [{"type": "text", "text": user_text}]
        })
        
        # Add complete assistant response
        self.message_history.append({
            "role": "assistant",
            "content": [{"type": "text", "text": complete_response}]
        })
        
        # Trim history to keep only recent messages
        if len(self.message_history) > self.max_history_messages:
            self.message_history = self.message_history[-self.max_history_messages:]
        
        logger.info(f"Updated message history with complete response ({len(complete_response)} chars)")

    async def generate(self, text):
        """Generate a response using the latest image and text input (non-streaming)"""
        async with self.lock:
            try:
                if not self.last_image:
                    logger.warning("No image available for multimodal generation")
                    return f"No image context: {text}"
                
                # Build messages with history
                messages = self._build_messages(text)
                
                # Prepare inputs for the model
                inputs = self.processor.apply_chat_template(
                    messages, 
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    return_tensors="pt"
                ).to(self.model.device)
                
                input_len = inputs["input_ids"].shape[-1]
                
                # Generate response with parameters tuned for concise output
                generation = self.model.generate(
                    **inputs, 
                    max_new_tokens=128,
                    do_sample=True,
                    temperature=0.7,
                    use_cache=True,
                )
                
                # Decode the generated tokens
                generated_text = self.processor.decode(
                    generation[0][input_len:],
                    skip_special_tokens=True
                )
                
                # Update conversation history
                self._update_history(text, generated_text)
                
                self.generation_count += 1
                logger.info(f"Gemma generation result ({len(generated_text)} chars)")
                
                return generated_text
                
            except Exception as e:
                logger.error(f"Gemma generation error: {e}")
                return f"Error processing: {text}"

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
            
            # Set Chinese voice to xiaobei
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
        """Convert remaining text to speech using Kokoro TTS with comprehensive splitting for quality"""
        if not text or not self.pipeline:
            return None
        
        try:
            logger.info(f"Synthesizing remaining speech for text: '{text[:50]}...' if len(text) > 50 else text")
            
            # Run TTS in a thread pool to avoid blocking
            audio_segments = []
            
            # Use the executor to run the TTS pipeline with comprehensive splitting
            # For remaining text, we want to process it with proper splits for better quality
            generator = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.pipeline(
                    text, 
                    voice=self.default_voice, 
                    speed=1, 
                    split_pattern=r'[.!?。！？,，;；:]+'  # Comprehensive splitting for remaining text
                )
            )
            
            # Process all generated segments
            for gs, ps, audio in generator:
                audio_segments.append(audio)
            
            # Combine all audio segments
            if audio_segments:
                combined_audio = np.concatenate(audio_segments)
                self.synthesis_count += 1
                logger.info(f"Remaining speech synthesis complete: {len(combined_audio)} samples")
                return combined_audio
            return None
            
        except Exception as e:
            logger.error(f"Remaining speech synthesis error: {e}")
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

async def handle_client(websocket):
    """Handles WebSocket client connection"""
    try:
        # Receive initial configuration
        await websocket.recv()
        logger.info("Client connected")
        
        # Initialize speech detection and get instance of processors
        detector = AudioSegmentDetector()
        transcriber = WhisperTranscriber.get_instance()
        gemma_processor = GemmaMultimodalProcessor.get_instance()
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
                        # Transcribe directly
                        transcription = await transcriber.transcribe(speech_segment)
                        
                        # Filter out pure punctuation or empty transcriptions
                        if transcription:
                            # Remove extra whitespace
                            transcription = transcription.strip()
                            
                            # Check if transcription contains any alphanumeric characters
                            if not any(c.isalnum() for c in transcription):
                                logger.info(f"Skipping pure punctuation transcription: '{transcription}'")
                                continue
                            
                            # Filter out single-word utterances and common filler sounds
                            words = [w for w in transcription.split() if any(c.isalnum() for c in w)]
                            if len(words) <= 1:
                                logger.info(f"Skipping single-word transcription: '{transcription}'")
                                continue
                                
                            # Filter out common filler sounds and very short responses
                            filler_patterns = [
                                r'^(um+|uh+|ah+|oh+|hm+|mhm+|hmm+)$',
                                r'^(okay|yes|no|yeah|nah)$',
                                r'^bye+$'
                            ]
                            if any(re.match(pattern, transcription.lower()) for pattern in filler_patterns):
                                logger.info(f"Skipping filler sound: '{transcription}'")
                                continue
                            
                            # Send interrupt signal before starting new generation
                            logger.info("Sending interrupt signal for new speech detection")
                            interrupt_message = json.dumps({"interrupt": True})
                            logger.info(f"Interrupt message: {interrupt_message}")
                            await websocket.send(interrupt_message)
                            
                            # Set TTS playing flag and start new generation workflow
                            await detector.set_tts_playing(True)
                            
                            try:
                                # Create generation task
                                generation_task = asyncio.create_task(
                                    gemma_processor.generate_streaming(transcription, initial_chunks=3)
                                )
                                
                                # Store the generation task
                                await detector.set_current_tasks(generation_task=generation_task)
                                
                                # Wait for initial generation
                                try:
                                    streamer, initial_text = await generation_task
                                except asyncio.CancelledError:
                                    logger.info("Generation cancelled - new speech detected")
                                    continue
                                
                                if initial_text:
                                    # Create TTS task for initial speech
                                    tts_task = asyncio.create_task(
                                        tts_processor.synthesize_initial_speech(initial_text)
                                    )
                                    
                                    # Store the TTS task
                                    await detector.set_current_tasks(tts_task=tts_task)
                                    
                                    try:
                                        # Wait for initial audio synthesis
                                        initial_audio = await tts_task
                                        
                                        if initial_audio is not None:
                                            # Convert to base64 and send to client
                                            audio_bytes = (initial_audio * 32767).astype(np.int16).tobytes()
                                            base64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                                            
                                            # Send the initial audio to the client
                                            await websocket.send(json.dumps({
                                                "audio": base64_audio
                                            }))
                                            
                                            # Start collecting remaining text in parallel
                                            remaining_text_task = asyncio.create_task(
                                                collect_remaining_text(streamer)
                                            )
                                            
                                            # Store the remaining text task
                                            await detector.set_current_tasks(generation_task=remaining_text_task)
                                            
                                            try:
                                                # Wait for remaining text collection
                                                remaining_text = await remaining_text_task
                                                
                                                # Update message history with complete response
                                                gemma_processor._update_history_with_complete_response(
                                                    transcription, initial_text, remaining_text
                                                )
                                                
                                                if remaining_text:
                                                    # Create TTS task for remaining text
                                                    remaining_tts_task = asyncio.create_task(
                                                        tts_processor.synthesize_remaining_speech(remaining_text)
                                                    )
                                                    
                                                    # Store the TTS task
                                                    await detector.set_current_tasks(tts_task=remaining_tts_task)
                                                    
                                                    try:
                                                        # Wait for remaining audio synthesis
                                                        remaining_audio = await remaining_tts_task
                                                        
                                                        if remaining_audio is not None:
                                                            # Convert to base64 and send to client
                                                            audio_bytes = (remaining_audio * 32767).astype(np.int16).tobytes()
                                                            base64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                                                            
                                                            # Send the remaining audio to the client
                                                            await websocket.send(json.dumps({
                                                                "audio": base64_audio
                                                            }))
                                                    
                                                    except asyncio.CancelledError:
                                                        # Even if TTS is cancelled, keep the message history
                                                        logger.info("Remaining TTS cancelled - new speech detected")
                                                        continue
                                            
                                            except asyncio.CancelledError:
                                                # If text collection is cancelled, update history with what we have
                                                gemma_processor._update_history_with_complete_response(
                                                    transcription, initial_text
                                                )
                                                logger.info("Remaining text collection cancelled - new speech detected")
                                                continue
                                    
                                    except asyncio.CancelledError:
                                        # If initial TTS is cancelled, still update history
                                        gemma_processor._update_history_with_complete_response(
                                            transcription, initial_text
                                        )
                                        logger.info("Initial TTS cancelled - new speech detected")
                                        continue
                            
                            except websockets.exceptions.ConnectionClosed:
                                break
                            except Exception as e:
                                logger.error(f"Error in speech processing: {e}")
                            finally:
                                # Clear TTS playing flag and tasks
                                await detector.set_tts_playing(False)
                                await detector.set_current_tasks()
                                
                    await asyncio.sleep(0.01)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    logger.error(f"Error detecting speech: {e}")
                    await detector.set_tts_playing(False)
                    await detector.set_current_tasks()
        
        async def collect_remaining_text(streamer):
            """Collect remaining text from the streamer"""
            collected_text = ""
            
            if streamer:
                try:
                    for chunk in streamer:
                        collected_text += chunk
                except asyncio.CancelledError:
                    raise
                
            return collected_text
        
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
                            elif chunk["mime_type"] == "image/jpeg" and not detector.tts_playing:
                                image_data = base64.b64decode(chunk["data"])
                                await gemma_processor.set_image(image_data)
                    
                    # Only process standalone image if TTS is not playing
                    if "image" in data and not detector.tts_playing:
                        image_data = base64.b64decode(data["image"])
                        await gemma_processor.set_image(image_data)
                        
                except Exception as e:
                    logger.error(f"Error receiving data: {e}")
        
        # Run tasks concurrently
        await asyncio.gather(
            receive_audio_and_images(),
            detect_speech_segments(),
            send_keepalive(),
            return_exceptions=True
        )
        
    except websockets.exceptions.ConnectionClosed:
        logger.info("Connection closed")
    except Exception as e:
        logger.error(f"Session error: {e}")
    finally:
        # Ensure TTS playing flag is cleared when connection ends
        await detector.set_tts_playing(False)

async def main():
    """Main function to start the WebSocket server"""
    try:
        # Initialize all processors ahead of time to load models
        transcriber = WhisperTranscriber.get_instance()
        gemma_processor = GemmaMultimodalProcessor.get_instance()
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
