import asyncio
import json
import websockets
import base64
import torch
from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline, Qwen2_5_VLForConditionalGeneration, BitsAndBytesConfig
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
        
        # Add TTS playback lock
        self.tts_playing = False
        self.tts_lock = asyncio.Lock()
    
    async def set_tts_playing(self, is_playing):
        """Set TTS playback state"""
        async with self.tts_lock:
            self.tts_playing = is_playing
    
    async def add_audio(self, audio_bytes):
        """Add audio data to the buffer and check for speech segments"""
        async with self.lock:
            # Check if TTS is playing
            async with self.tts_lock:
                if self.tts_playing:
                    return None
                    
            # Add new audio to buffer
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
                            
                            # Only return if speech segment is long enough
                            if len(speech_segment) >= self.min_speech_samples * 2:  # × 2 for 16-bit
                                self.segments_detected += 1
                                logger.info(f"Speech segment detected: {len(speech_segment)/2/self.sample_rate:.2f}s")
                                
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
        model_id = "openai/whisper-small"
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

class QwenMultimodalProcessor:
    """Handles multimodal generation using Qwen2.5-VL model with 4-bit quantization"""
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self):
        # Use GPU for generation
        self.device = "cuda:0" if torch.cuda.is_available() else "cpu"
        logger.info(f"Using device for Qwen: {self.device}")
        
        # Configure 4-bit quantization
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True
        )
        
        # Load model and processor
        model_id = "Qwen/Qwen2.5-VL-3B-Instruct"
        logger.info(f"Loading {model_id} with 4-bit quantization...")
        
        # Load model with 4-bit quantization
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            model_id,
            quantization_config=quantization_config,
            device_map="auto"
        )
        
        # Load processor
        self.processor = AutoProcessor.from_pretrained(model_id)
        
        logger.info("Qwen model ready for multimodal generation (4-bit quantized)")
        
        # Cache for most recent image
        self.last_image = None
        self.last_image_timestamp = 0
        self.lock = asyncio.Lock()
        
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
                
                self.last_image = image
                self.last_image_timestamp = time.time()
                return True
            except Exception as e:
                logger.error(f"Error processing image: {e}")
                return False
                
    async def generate(self, text):
        """Generate a response using the latest image and text input"""
        async with self.lock:
            try:
                if not self.last_image:
                    logger.warning("No image available for multimodal generation")
                    return f"No image context: {text}"
                
                # Create messages format with system instruction for conversational output
                messages = [
                    {
                        "role": "system",
                        "content": """You are a helpful assistant providing spoken 
                        responses about images. Keep your answers concise, fluent, 
                        and conversational. Use natural oral language that's easy to listen to.
                        Avoid lengthy explanations and focus on the most important information. 
                        Limit your response to 2-3 short sentences when possible.
                        Ask user to repeat or clarify if the request content is not clear or broken."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image", "image": self.last_image},
                            {"type": "text", "text": text}
                        ]
                    }
                ]
                
                # Prepare inputs for the model
                text_input = self.processor.apply_chat_template(
                    messages, 
                    tokenize=False, 
                    add_generation_prompt=True
                )
                
                # Process images and text
                inputs = self.processor(
                    text=[text_input],
                    images=[self.last_image],
                    padding=True,
                    return_tensors="pt"
                )
                
                # Move inputs to device
                inputs = inputs.to(self.device)
                
                # Generate response with parameters tuned for concise output
                generated_ids = self.model.generate(
                    **inputs, 
                    max_new_tokens=128,  # Reduced from 256 to encourage brevity
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.9,
                    repetition_penalty=1.2  # Discourage repetitive text
                )
                
                # Decode the response
                generated_ids_trimmed = [
                    out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
                ]
                output_text = self.processor.batch_decode(
                    generated_ids_trimmed, 
                    skip_special_tokens=True, 
                    clean_up_tokenization_spaces=False
                )[0]
                
                self.generation_count += 1
                logger.info(f"Qwen generation result ({len(output_text)} chars)")
                
                return output_text
                
            except Exception as e:
                logger.error(f"Qwen generation error: {e}")
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
            # Initialize Kokoro TTS pipeline with English
            self.pipeline = KPipeline(lang_code='a')
            
            # Set English voice to xiaobei
            self.default_voice = 'af_sarah'
            
            logger.info("Kokoro TTS processor initialized successfully")
            # Counter
            self.synthesis_count = 0
        except Exception as e:
            logger.error(f"Error initializing Kokoro TTS: {e}")
            self.pipeline = None
    
    async def synthesize_speech(self, text):
        """Convert text to speech using Kokoro TTS"""
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
        qwen_processor = QwenMultimodalProcessor.get_instance()
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
                        if transcription:
                            # Generate response using Qwen with the cached image
                            response = await qwen_processor.generate(transcription)
                            
                            # Set TTS playing flag before synthesis
                            await detector.set_tts_playing(True)
                            
                            try:
                                # Synthesize speech from the response
                                audio = await tts_processor.synthesize_speech(response)
                                if audio is not None:
                                    # Convert to base64 and send to client
                                    audio_bytes = (audio * 32767).astype(np.int16).tobytes()
                                    base64_audio = base64.b64encode(audio_bytes).decode('utf-8')
                                    
                                    # Send the audio to the client
                                    await websocket.send(json.dumps({
                                        "audio": base64_audio
                                    }))
                                    
                                    # Calculate playback duration and split into smaller sleep intervals
                                    total_duration = len(audio) / 24000  # seconds
                                    interval = 0.5  # sleep in 0.5 second intervals
                                    intervals = int(total_duration / interval)
                                    
                                    try:
                                        # Wait for audio playback using ping/pong for connection check
                                        for _ in range(intervals):
                                            await websocket.ping()
                                            await asyncio.sleep(interval)
                                        
                                        # Sleep for remaining time
                                        remaining = total_duration - (intervals * interval)
                                        if remaining > 0:
                                            await websocket.ping()
                                            await asyncio.sleep(remaining)
                                            
                                    except websockets.exceptions.ConnectionClosed:
                                        break
                                    
                            except websockets.exceptions.ConnectionClosed:
                                break
                            finally:
                                # Clear TTS playing flag after playback
                                await detector.set_tts_playing(False)
                                
                    await asyncio.sleep(0.01)
                except websockets.exceptions.ConnectionClosed:
                    break
                except Exception as e:
                    logger.error(f"Error detecting speech: {e}")
                    await detector.set_tts_playing(False)
        
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
                                await qwen_processor.set_image(image_data)
                    
                    # Only process standalone image if TTS is not playing
                    if "image" in data and not detector.tts_playing:
                        image_data = base64.b64decode(data["image"])
                        await qwen_processor.set_image(image_data)
                        
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
        qwen_processor = QwenMultimodalProcessor.get_instance()
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