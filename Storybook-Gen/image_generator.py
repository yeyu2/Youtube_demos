#!/usr/bin/env python3
"""
Image generator module for storybook generation.

This module handles the generation of cover and page images using OpenAI's APIs:
- Cover images are generated using the Create Image API
- Page images are generated using the Edit Image API with the cover as reference
"""

import os
import json
import time
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

# Import OpenAI client
from openai import OpenAI

# Import utils for environment variables
from src.utils import get_env, load_environment, ensure_output_dir


def generate_image(prompt: str, output_path: Path, model: str = None) -> Tuple[Path, Optional[Dict]]:
    """
    Generate an image using OpenAI's Create Image API.
    
    Args:
        prompt: The text prompt for image generation
        output_path: Where to save the generated image
        model: The model to use for generation (defaults to env variable or gpt-image-1)
    
    Returns:
        Tuple of (output_path, usage_data)
    """
    # Ensure the parent directory exists
    output_path.parent.mkdir(exist_ok=True, parents=True)
    
    # Get API key from environment
    api_key = get_env("OPENAI_API_KEY")
    
    # Get model from environment if not specified
    if not model:
        model = get_env("IMAGE_MODEL", "gpt-image-1")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Generate the image
    print(f"Generating image with {model} using prompt of length {len(prompt)} chars...")
    
    try:
        # Prepare parameters based on model
        params = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": get_env("IMAGE_SIZE", "1024x1024"),
        }
        
        # Add quality parameter for gpt-image-1
        if model == "gpt-image-1":
            params["quality"] = "high"
        
        # Generate the image
        response = client.images.generate(**params)
        
        # Process response based on model
        if model == "gpt-image-1":
            # For gpt-image-1, decode base64
            if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
                image_bytes = base64.b64decode(response.data[0].b64_json)
                with open(output_path, "wb") as f:
                    f.write(image_bytes)
            else:
                # If no b64_json, try URL
                import requests
                image_url = response.data[0].url
                image_response = requests.get(image_url)
                with open(output_path, "wb") as f:
                    f.write(image_response.content)
        else:
            # For dall-e models, download from URL
            import requests
            image_url = response.data[0].url
            image_response = requests.get(image_url)
            with open(output_path, "wb") as f:
                f.write(image_response.content)
        
        # Extract and return usage data if available
        usage_data = getattr(response, "usage", None)
        if usage_data:
            usage_dict = {
                "total_tokens": usage_data.total_tokens,
                "input_tokens": usage_data.input_tokens,
                "output_tokens": usage_data.output_tokens
            }
        else:
            usage_dict = None
        
        print(f"Image saved to {output_path}")
        return output_path, usage_dict
        
    except Exception as e:
        print(f"Error generating image: {e}")
        return output_path, None


def generate_image_with_reference(
    prompt: str, 
    reference_image_path: Path, 
    output_path: Path,
    model: str = None
) -> Tuple[Path, Optional[Dict]]:
    """
    Generate an image using OpenAI's Edit Image API with a reference image.
    
    Args:
        prompt: The text prompt for image generation
        reference_image_path: Path to the reference image file
        output_path: Where to save the generated image
        model: The model to use (defaults to env variable or gpt-image-1)
    
    Returns:
        Tuple of (output_path, usage_data)
    """
    # Ensure the parent directory exists
    output_path.parent.mkdir(exist_ok=True, parents=True)
    
    # Get API key from environment
    api_key = get_env("OPENAI_API_KEY")
    
    # Get model from environment if not specified
    if not model:
        model = get_env("IMAGE_MODEL", "gpt-image-1")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Check if reference image exists
    if not reference_image_path.exists():
        print(f"Reference image not found: {reference_image_path}")
        return output_path, None
    
    try:
        # Prepare parameters
        params = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": get_env("IMAGE_SIZE", "1024x1024"),
        }
        
        # Add quality and input_fidelity for gpt-image-1
        if model == "gpt-image-1":
            params["input_fidelity"] = "high"
            params["quality"] = "high"
        
        # Open reference image file and make the API call
        print(f"Generating image with reference using {model}...")
        
        with open(reference_image_path, "rb") as f:
            # Set the image parameter
            params["image"] = f
            
            # Make the API call
            response = client.images.edit(**params)
        
        # Process response based on model
        if model == "gpt-image-1":
            # For gpt-image-1, try b64_json first
            if hasattr(response.data[0], "b64_json") and response.data[0].b64_json:
                image_bytes = base64.b64decode(response.data[0].b64_json)
                with open(output_path, "wb") as f:
                    f.write(image_bytes)
            else:
                # If no b64_json, try URL
                import requests
                image_url = response.data[0].url
                image_response = requests.get(image_url)
                with open(output_path, "wb") as f:
                    f.write(image_response.content)
        else:
            # For dall-e models, download from URL
            import requests
            image_url = response.data[0].url
            image_response = requests.get(image_url)
            with open(output_path, "wb") as f:
                f.write(image_response.content)
        
        # Extract and return usage data if available
        usage_data = getattr(response, "usage", None)
        if usage_data:
            usage_dict = {
                "total_tokens": usage_data.total_tokens,
                "input_tokens": usage_data.input_tokens,
                "output_tokens": usage_data.output_tokens
            }
        else:
            usage_dict = None
        
        print(f"Image with reference saved to {output_path}")
        return output_path, usage_dict
        
    except Exception as e:
        print(f"Error generating image with reference: {e}")
        return output_path, None


def create_page_prompt(page_data: Dict, page_num: int, style_guide: Optional[str] = None) -> str:
    """
    Create a prompt for a page image from page data.
    """
    # Extract the page content from various possible formats
    base_prompt = ""
    if isinstance(page_data, dict):
        # For page_prompts from PromptIllustrator
        if "prompt" in page_data:
            base_prompt = page_data["prompt"]
            if style_guide and "Style:" not in base_prompt:
                base_prompt = f"{base_prompt}\n\nStyle: {style_guide}"
        # For image_prompt in pages array
        elif "image_prompt" in page_data:
            base_prompt = page_data["image_prompt"]
            if style_guide and "Style:" not in base_prompt:
                base_prompt = f"{base_prompt}\n\nStyle: {style_guide}"
        # For pages in a different format
        else:
            text = page_data.get("text", "")
            illustration = page_data.get("art_direction", "")
            if illustration:
                base_prompt = illustration
            else:
                # No explicit illustration prompt, use text content
                base_prompt = f"A children's book illustration for the text: {text}"
                if style_guide:
                    base_prompt = f"{base_prompt}\n\nStyle: {style_guide}"
    elif isinstance(page_data, str):
        # String content, assume it's the text for the page
        base_prompt = f"A children's book illustration for the text: {page_data}"
        if style_guide:
            base_prompt = f"{base_prompt}\n\nStyle: {style_guide}"
    else:
        # Fallback for unknown format
        base_prompt = f"A children's book illustration for page {page_num}"
    
    return base_prompt


def generate_storybook_images(story_json_path: str, delay_seconds: int = 10, use_reference: bool = True) -> List[Dict]:
    """
    Generate images for a storybook from extracted story content.
    
    Args:
        story_json_path: Path to the extracted story JSON file
        delay_seconds: Delay between image generations to avoid rate limits
        use_reference: Whether to use the cover image as reference for consistency
        
    Returns:
        List of usage data for each generated image
    """
    print(f"Loading story content from: {story_json_path}")
    
    # Load the story content
    with open(story_json_path, 'r') as f:
        story_content = json.load(f)
    
    # Create output directory
    output_dir = Path(story_json_path).parent
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(exist_ok=True)
    
    # Track usage data for all images
    all_usage_data = []
    
    # Extract title and generate cover image
    title = story_content.get("title", "Untitled Story")
    
    # Get cover prompt from the story content
    cover_prompt = story_content.get("cover_prompt", "")
    
    # If no cover prompt exists, build one from components
    if not cover_prompt:
        style_guide = None
        character_descriptions = []
        
        # Try to extract from story_brief
        if "story_brief" in story_content:
            brief = story_content["story_brief"]
            
            # Get style guide
            if "style_guide" in brief:
                style_guide = brief["style_guide"]
            
            # Get character descriptions
            if "characters" in brief and isinstance(brief["characters"], dict):
                for name, info in brief["characters"].items():
                    if isinstance(info, dict) and "description" in info:
                        character_descriptions.append(f"{name}: {info['description']}")
                    elif isinstance(info, str):
                        character_descriptions.append(f"{name}: {info}")
        
        # Build cover prompt
        cover_prompt = (
            f"Children's storybook cover illustration for '{title}'. "
            f"{'. '.join(character_descriptions)}. "
            f"Style: {style_guide or 'colorful, whimsical, child-friendly illustration'}. "
            f"Bright, cheerful colors with a magical feel."
        )
    
    print("\n--- Generating Cover Image ---")
    print(f"Title: {title}")
    print(f"Prompt: {cover_prompt}")
    
    # Generate the cover image
    cover_path = output_dir / "cover.png"
    cover_path, cover_usage = generate_image(cover_prompt, cover_path)
    if cover_usage:
        all_usage_data.append(cover_usage)
    
    print(f"Cover image saved to: {cover_path}")
    
    # Add a delay before generating page images
    print(f"\nWaiting {delay_seconds} seconds before generating page images...")
    time.sleep(delay_seconds)
    
    # Process page_prompts array if it exists
    if "page_prompts" in story_content and isinstance(story_content["page_prompts"], list):
        for prompt_data in story_content["page_prompts"]:
            if isinstance(prompt_data, dict) and "page" in prompt_data and "prompt" in prompt_data:
                page_num = prompt_data["page"]
                image_prompt = prompt_data["prompt"]
                
                print(f"\n--- Generating Image for Page {page_num} ---")
                print(f"Prompt: {image_prompt}")
                
                # Generate the image using reference if enabled
                image_path = pages_dir / f"page_{page_num:02d}.png"
                if use_reference and cover_path.exists():
                    print(f"Using cover image as reference for consistency")
                    image_path, usage_data = generate_image_with_reference(image_prompt, cover_path, image_path)
                else:
                    image_path, usage_data = generate_image(image_prompt, image_path)
                
                if usage_data:
                    all_usage_data.append(usage_data)
                
                print(f"Image saved to: {image_path}")
                
                # Find the corresponding page in the pages array and update it
                for page in story_content.get("pages", []):
                    if page.get("page") == page_num:
                        page["image_path"] = str(image_path)
                        break
                
                # Wait before generating the next image
                if prompt_data != story_content["page_prompts"][-1]:  # Don't wait after the last page
                    print(f"\nWaiting {delay_seconds} seconds before generating next image...")
                    time.sleep(delay_seconds)
    
    # Fall back to the pages array if no page_prompts
    elif "pages" in story_content and isinstance(story_content["pages"], list):
        for i, page in enumerate(story_content["pages"]):
            page_num = page.get("page", i+1)
            
            # Get or create image prompt
            if "image_prompt" in page:
                image_prompt = page["image_prompt"]
            else:
                # Try to create an image prompt from art_direction or text
                image_prompt = create_page_prompt(page, page_num)
            
            # Skip if no prompt available
            if not image_prompt:
                print(f"No image prompt found for page {page_num}, skipping...")
                continue
            
            print(f"\n--- Generating Image for Page {page_num} ---")
            print(f"Prompt: {image_prompt}")
            
            # Generate the image using reference if enabled
            image_path = pages_dir / f"page_{page_num:02d}.png"
            if use_reference and cover_path.exists():
                print(f"Using cover image as reference for consistency")
                image_path, usage_data = generate_image_with_reference(image_prompt, cover_path, image_path)
            else:
                image_path, usage_data = generate_image(image_prompt, image_path)
            
            if usage_data:
                all_usage_data.append(usage_data)
            
            print(f"Image saved to: {image_path}")
            
            # Update the story content with the image path
            page["image_path"] = str(image_path)
            
            # Wait before generating the next image
            if i < len(story_content["pages"]) - 1:  # Don't wait after the last page
                print(f"\nWaiting {delay_seconds} seconds before generating next image...")
                time.sleep(delay_seconds)
    
    # Save the updated story content with image paths
    updated_story_path = output_dir / "story_with_images.json"
    with open(updated_story_path, 'w') as f:
        json.dump(story_content, f, indent=2)
    
    print(f"\nAll images generated successfully!")
    print(f"Updated story content saved to: {updated_story_path}")
    
    return all_usage_data


if __name__ == "__main__":
    # If run directly, process command line arguments
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate images for a storybook")
    parser.add_argument(
        "--story-json",
        required=True,
        help="Path to the extracted story JSON file"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=10,
        help="Delay in seconds between image generations (default: 10)"
    )
    parser.add_argument(
        "--use-reference",
        action="store_true",
        help="Use the cover image as a reference for consistency in character appearance"
    )
    
    args = parser.parse_args()
    
    # Load environment
    load_environment()
    
    # Generate images
    generate_storybook_images(
        story_json_path=args.story_json,
        delay_seconds=args.delay,
        use_reference=args.use_reference
    ) 