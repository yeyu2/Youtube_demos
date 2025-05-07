import requests
import torch
import soundfile
from PIL import Image # Not used in this snippet, but typical for multimodal
import soundfile
from transformers import AutoModelForCausalLM, AutoProcessor, GenerationConfig, pipeline, AutoTokenizer # pipeline and AutoTokenizer also not used directly here
from transformers import TextIteratorStreamer
from threading import Thread
import time
import os
from urllib.request import urlopen
from io import BytesIO

# --- CHANGE THIS LINE ---
model_path = 'microsoft/phi-4-multimodal-instruct'
# -------------------------

# kwargs = {} # This variable isn't used in the rest of the code, can be removed
# kwargs['torch_dtype'] = torch.bfloat16

# Load the processor - uses the model_path (Hugging Face ID)
processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)

# Load the model - uses the model_path (Hugging Face ID)
# trust_remote_code is required for this model
# torch_dtype='auto' is generally good for performance
# _attn_implementation='flash_attention_2' is an optimization, requires Flash Attention installed and GPU
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    trust_remote_code=True,
    torch_dtype='auto', # or torch.bfloat16 if you prefer explicit dtype
    _attn_implementation='flash_attention_2',
).cuda() # Move model to GPU

# Load the generation config - uses the model_path (Hugging Face ID)
# When loading from the hub, just providing the repo ID is standard
generation_config = GenerationConfig.from_pretrained(model_path)

# --- Rest of your code remains the same ---

user_prompt = '<|user|>'
assistant_prompt = '<|assistant|>'
prompt_suffix = '<|end|>'

# System instruction for conversational responses
system_instruction = """You are a helpful multimodal assistant. 
When responding to audio queries, use natural, conversational language that sounds fluent when spoken. 
Respond in a friendly, helpful tone as if you're having a conversation. 
Avoid overly formal language or technical jargon unless necessary. 
Your responses should be clear, concise, and easy to understand when heard rather than read.
Don't forget to call the user by their name at beginning of your response, this user is Adam."""

def load_audio(audio_path):
    try:
        audio, samplerate = soundfile.read(audio_path)
        return (audio, samplerate)
    except FileNotFoundError:
        print(f"Error: {audio_path} not found. Please provide the correct path to an audio file.")
        return None

def load_image(image_path_or_url):
    try:
        if image_path_or_url.startswith(('http://', 'https://')):
            response = requests.get(image_path_or_url, stream=True)
            image = Image.open(BytesIO(response.content))
        else:
            image = Image.open(image_path_or_url)
        return image
    except Exception as e:
        print(f"Error loading image: {e}")
        return None

def generate_streaming(audio_input, custom_prompt=None):
    if audio_input is None:
        return
        
    # Default prompt for audio transcription
    speech_prompt = custom_prompt or "Based on the attached audio, generate a comprehensive text transcription of the spoken content."
    prompt = f'{user_prompt}<|audio_1|>{speech_prompt}{prompt_suffix}{assistant_prompt}'
    
    # Prepare inputs for the model
    inputs = processor(text=prompt, audios=[audio_input], return_tensors='pt').to('cuda:0')
    
    # Set up streaming
    streamer = TextIteratorStreamer(processor, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    
    # Configure generation parameters
    generation_kwargs = dict(
        **inputs,
        max_new_tokens=1200,
        generation_config=generation_config,
        streamer=streamer,
    )
    
    # Start timing
    start_time = time.time()
    
    # Start generation in a separate thread to allow streaming output
    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()
    
    # Print tokens as they're generated
    print("\nStreaming output:")
    for text in streamer:
        print(text, end="", flush=True)
    
    # Calculate and print inference time
    end_time = time.time()
    inference_time = end_time - start_time
    print(f"\n\nInference time: {inference_time:.2f} seconds")
    
    return inference_time

def generate_multimodal(audio_input, image_input, custom_prompt=None):
    """Process both audio and image inputs together"""
    if audio_input is None or image_input is None:
        print("Both audio and image are required for multimodal processing")
        return
    
    print("\n--- MULTIMODAL PROCESSING (AUDIO + IMAGE) ---")
    
    # For multimodal input, we need to indicate both modalities in the prompt
    # Updated to use the correct Phi-4 format
    system_tag = '<|system|>'
    system_end_tag = '<|end|>'
    user_tag = '<|user|>'
    user_end_tag = '<|end|>'
    assistant_tag = '<|assistant|>'
    
    prompt = f'{system_tag}{system_instruction}{system_end_tag}'
    prompt += f'{user_tag}<|audio_1|>{custom_prompt or "Answer the question in the audio based on the image in detail description."}<|image_1|>{user_end_tag}'
    prompt += f'{assistant_tag}'
    
    print(f'>>> Prompt\n{prompt}')
    
    # Prepare inputs for the model with both audio and image
    inputs = processor(
        text=prompt, 
        audios=[audio_input], 
        images=[image_input], 
        return_tensors='pt'
    ).to('cuda:0')
    
    # Get the token length of the input to skip in the output
    input_len = inputs["input_ids"].shape[-1]
    
    # Set up streaming
    streamer = TextIteratorStreamer(
        tokenizer=processor, 
        skip_special_tokens=True,
        skip_prompt=True,  # Skip the input prompt tokens
        clean_up_tokenization_spaces=False
    )
    
    # Configure generation parameters
    generation_kwargs = dict(
        **inputs,
        max_new_tokens=1200,
        generation_config=generation_config,
        streamer=streamer,
    )
    
    # Start timing
    start_time = time.time()
    
    # Start generation in a separate thread to allow streaming output
    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()
    
    # Print tokens as they're generated
    print("\nStreaming output:")
    for text in streamer:
        print(text, end="", flush=True)
    
    # Calculate and print inference time
    end_time = time.time()
    inference_time = end_time - start_time
    print(f"\n\nInference time: {inference_time:.2f} seconds")
    
    return inference_time

def generate_multimodal_two_step(audio_input, image_input, custom_prompt=None):
    """Two-step approach: 
    1. First get image description (not shown to user)
    2. Then use this description with audio for final response
    """
    if audio_input is None or image_input is None:
        print("Both audio and image are required for multimodal processing")
        return
    
    print("\n--- SMART MULTIMODAL PROCESSING (AUDIO + IMAGE) ---")
    
    # Step 1: Get image description without streaming
    print("Step 1: Processing image (hidden from user)...")
    
    # Updated to use the correct Phi-4 format
    system_tag = '<|system|>'
    system_end_tag = '<|end|>'
    user_tag = '<|user|>'
    user_end_tag = '<|end|>'
    assistant_tag = '<|assistant|>'
    
    image_prompt = f'{system_tag}{system_instruction}{system_end_tag}'
    image_prompt += f'{user_tag}<|image_1|>Describe this image in detail.{user_end_tag}'
    image_prompt += f'{assistant_tag}'
    
    # Process the image to get description
    image_inputs = processor(
        text=image_prompt, 
        images=[image_input], 
        return_tensors='pt'
    ).to('cuda:0')
    
    # Generate image description without streaming
    image_output = model.generate(
        **image_inputs,
        max_new_tokens=800,
        generation_config=generation_config
    )
    
    # Get the description text
    image_description = processor.decode(image_output[0], skip_special_tokens=True)
    
    # Extract just the assistant's response (remove the user's prompt)
    split_text = image_description.split(assistant_prompt)
    if len(split_text) > 1:
        image_description = split_text[1].strip()
    
    # Step 2: Use image description with audio
    print("Step 2: Processing audio with image context...")
    
    # Create prompt that includes system instruction, image description and audio
    audio_prompt = custom_prompt or "Answer the question in the audio based on the image."
    
    prompt = f'{system_tag}{system_instruction}{system_end_tag}'
    prompt += f'{user_tag}Image description: {image_description}\n\n<|audio_1|>{audio_prompt}{user_end_tag}'
    prompt += f'{assistant_tag}'
    
    # Prepare inputs for the model with audio and the image description in the text
    inputs = processor(
        text=prompt, 
        audios=[audio_input], 
        return_tensors='pt'
    ).to('cuda:0')
    
    # Get the token length of the input to skip in the output
    input_len = inputs["input_ids"].shape[-1]
    
    # Set up streaming for the final response
    streamer = TextIteratorStreamer(
        tokenizer=processor, 
        skip_special_tokens=True,
        skip_prompt=True,  # Skip the input prompt tokens
        clean_up_tokenization_spaces=False
    )
    
    # Configure generation parameters
    generation_kwargs = dict(
        **inputs,
        max_new_tokens=1200,
        generation_config=generation_config,
        streamer=streamer,
    )
    
    # Start timing
    start_time = time.time()
    
    # Start generation in a separate thread to allow streaming output
    thread = Thread(target=model.generate, kwargs=generation_kwargs)
    thread.start()
    
    # Print tokens as they're generated
    print("\nFinal Response (based on image description and audio):")
    for text in streamer:
        print(text, end="", flush=True)
    
    # Calculate and print inference time
    end_time = time.time()
    inference_time = end_time - start_time
    print(f"\n\nTotal inference time: {inference_time:.2f} seconds")
    
    return inference_time

def main():
    print("Multimodal Processing Tool")
    print("=========================")
    
    # Default audio file
    default_audio_path = './record.wav'
    audio_input = load_audio(default_audio_path)
    
    # Default image URL - load it automatically at startup
    default_image_url = 'https://www.ilankelman.org/stopsigns/australia.jpg'
    image_input = load_image(default_image_url)
    
    if audio_input is None:
        print(f"Starting without a default audio file. You'll need to provide a valid path.")
    else:
        print(f"Default audio loaded: {default_audio_path}")
        
    if image_input is None:
        print(f"Failed to load default image. You'll need to provide a valid image.")
    else:
        print(f"Default image loaded: {default_image_url}")
    
    while True:
        print("\nOptions:")
        print("1. Audio-only processing")
        print("2. Load audio file")
        print("3. Load different image (current: default stop sign)")
        print("4. Direct multimodal (audio + image together)")
        print("5. Smart multimodal (image analysis + audio)")
        print("6. Change prompt")
        print("7. Exit")
        
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == '1':
            if audio_input:
                generate_streaming(audio_input)
            else:
                print("No audio loaded. Please load an audio file first.")
        
        elif choice == '2':
            audio_path = input("Enter path to audio file: ").strip()
            new_audio = load_audio(audio_path)
            if new_audio:
                audio_input = new_audio
                print(f"Successfully loaded audio: {audio_path}")
        
        elif choice == '3':
            image_path = input("Enter path or URL to image file: ").strip()
            new_image = load_image(image_path)
            if new_image:
                image_input = new_image
                print(f"Successfully loaded image: {image_path}")
        
        elif choice == '4':
            if audio_input and image_input:
                custom_prompt = input("Enter custom prompt (or press Enter for default): ").strip() or None
                generate_multimodal(audio_input, image_input, custom_prompt)
            else:
                print("Both audio and image must be loaded. Please load both first.")
        
        elif choice == '5':
            if audio_input and image_input:
                custom_prompt = input("Enter custom prompt (or press Enter for default): ").strip() or None
                generate_multimodal_two_step(audio_input, image_input, custom_prompt)
            else:
                print("Both audio and image must be loaded. Please load both first.")
        
        elif choice == '6':
            custom_prompt = input("Enter custom prompt for processing: ").strip()
            mode = input("Select mode (1: Audio-only, 2: Direct multimodal, 3: Smart multimodal): ").strip()
            
            if mode == '1' and audio_input:
                generate_streaming(audio_input, custom_prompt)
            elif mode == '2' and audio_input and image_input:
                generate_multimodal(audio_input, image_input, custom_prompt)
            elif mode == '3' and audio_input and image_input:
                generate_multimodal_two_step(audio_input, image_input, custom_prompt)
            else:
                print("Invalid mode or missing media. Please check your inputs.")
        
        elif choice == '7':
            print("Exiting program.")
            break
        
        else:
            print("Invalid choice. Please enter a number between 1-7.")

if __name__ == "__main__":
    main()