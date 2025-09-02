#!/usr/bin/env python3
"""
Storybook Generator (No Reference Images) - Main Application

A simple terminal application to generate personalized children's storybooks with
AI-generated text, images, and PDF output.

This version does NOT use the image edit API for reference - all images are generated
using the create image API, relying solely on prompt consistency.
"""

import os
import time
import sys
import json
import traceback
from pathlib import Path
from typing import Tuple

# Make sure we're in the project directory
project_dir = Path(__file__).parent.absolute()
os.chdir(project_dir)

# Import required modules
from src.models import StoryRequest, PagePlan
from src.utils import load_environment, ensure_output_dir
from agent_orchestration import run_agent_orchestration
from src.pdf_builder import build_pdf
from image_generator import generate_image  # Import only generate_image


def print_header():
    """Print a decorative header for the application."""
    print("\n" + "=" * 80)
    print(" " * 25 + "CHILDREN'S STORYBOOK GENERATOR")
    print(" " * 25 + "(No Reference Images Version)")
    print("=" * 80)
    print("Create a personalized storybook with AI-generated text and illustrations!\n")
    print("NOTE: This version uses prompt-only consistency without reference images.\n")


def get_user_input() -> Tuple[str, int, str, int]:
    """Get user input for the storybook parameters."""
    print("Please provide some details about the child:")
    
    # Get child's name
    while True:
        name = input("Child's name: ").strip()
        if name:
            break
        print("Name cannot be empty. Please try again.")
    
    # Get child's age
    while True:
        try:
            age = input("Child's age (2-12): ").strip()
            age = int(age)
            if 2 <= age <= 12:
                break
            print("Age must be between 2 and 12. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Get child's interests
    interests = input("Child's interests (e.g., dinosaurs, space, cooking): ").strip()
    if not interests:
        interests = "adventure and exploration"
        print(f"Using default interests: {interests}")
    
    # Get number of pages
    while True:
        try:
            pages = input("Number of pages (3-10) [default: 5]: ").strip()
            if not pages:
                pages = 5
                break
            pages = int(pages)
            if 3 <= pages <= 10:
                break
            print("Number of pages must be between 3 and 10. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    return name, age, interests, pages


def show_progress_message(message: str):
    """Display a progress message."""
    print(f"\n--> {message}")


def generate_storybook(req: StoryRequest):
    """Generate the storybook based on the request."""
    try:
        # Run the agent orchestration to create the story content
        show_progress_message("Starting storybook generation. This may take several minutes...")
        show_progress_message("Our AI authors and illustrators are creating a unique story...")
        
        # Generate the story content
        start_time = time.time()
        story_content = run_agent_orchestration(req)
        
        # Ensure the output directory is properly set
        output_dir = Path(story_content.get("output_dir", ""))
        if not output_dir or not output_dir.exists():
            output_dir = ensure_output_dir()
            story_content["output_dir"] = str(output_dir)
        
        # Generate images WITHOUT using reference (key difference from the original)
        show_progress_message("Story created! Now generating images (without reference)...")
        
        # Create the pages directory
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(exist_ok=True)
        
        # Generate the cover image
        cover_prompt = story_content.get("cover_prompt", "")
        if cover_prompt:
            print("\n--- Generating Cover Image ---")
            print(f"Title: {story_content.get('title', 'Untitled Story')}")
            print(f"Prompt: {cover_prompt}")
            
            cover_path = output_dir / "cover.png"
            cover_path, _ = generate_image(cover_prompt, cover_path)
            print(f"Cover image saved to: {cover_path}")
        
        # Wait a bit between image generations
        time.sleep(3)
        
        # Process page prompts
        if "page_prompts" in story_content and isinstance(story_content["page_prompts"], list):
            for prompt_data in story_content["page_prompts"]:
                if isinstance(prompt_data, dict) and "page" in prompt_data and "prompt" in prompt_data:
                    page_num = prompt_data["page"]
                    image_prompt = prompt_data["prompt"]
                    
                    print(f"\n--- Generating Image for Page {page_num} ---")
                    print(f"Prompt: {image_prompt}")
                    
                    # Generate the image WITHOUT reference - just using the prompt
                    image_path = pages_dir / f"page_{page_num:02d}.png"
                    image_path, _ = generate_image(image_prompt, image_path)
                    print(f"Image saved to: {image_path}")
                    
                    # Find the corresponding page in the pages array and update it
                    for page in story_content.get("pages", []):
                        if page.get("page") == page_num:
                            page["image_path"] = str(image_path)
                            break
                    
                    # Wait before generating the next image
                    time.sleep(3)
        
        # Save the updated story content
        updated_story_path = output_dir / "story_with_images_no_reference.json"
        with open(updated_story_path, 'w') as f:
            json.dump(story_content, f, indent=2)
        
        # Load the completed story with images for PDF generation
        show_progress_message("Images generated! Now creating the final PDF storybook...")
        
        # Create PagePlan objects for the PDF
        title = story_content.get("title", "Untitled Story")
        cover_image = output_dir / "cover.png"
        
        # Convert pages to PagePlan objects
        page_plans = []
        for page in story_content.get("pages", []):
            page_num = page.get("page", 0)
            
            # Try to get text content
            text_content = page.get("text", "")
            if not text_content:
                text_content = f"Page {page_num}"
            
            page_plan = PagePlan(
                index=page_num,
                text=text_content,
                illustration_notes=page.get("art_direction", ""),
                image_prompt=page.get("image_prompt", ""),
                image_path=page.get("image_path", "")
            )
            page_plans.append(page_plan)
        
        # Sort pages by index
        page_plans.sort(key=lambda x: x.index)
        
        # Generate the PDF with age-appropriate typography
        pdf_path = output_dir / "storybook_no_reference.pdf"
        pdf_path = build_pdf(
            output_pdf=pdf_path,
            title=title, 
            cover_image=cover_image, 
            pages=page_plans,
            child_age=req.child_age
        )
        
        # Return completion info
        elapsed_time = time.time() - start_time
        minutes, seconds = divmod(int(elapsed_time), 60)
        
        return {
            "title": title,
            "output_dir": output_dir,
            "pdf_path": pdf_path,
            "elapsed_time": (minutes, seconds)
        }
    
    except Exception as e:
        print(f"Error during storybook generation: {e}")
        traceback.print_exc()
        raise


def main():
    """Main entry point for the application."""
    try:
        # Print header
        print_header()
        
        # Load environment variables
        load_environment()
        
        # Get user input
        name, age, interests, pages = get_user_input()
        
        # Confirm details
        print("\n" + "-" * 40)
        print("Storybook details:")
        print(f"- Child's name: {name}")
        print(f"- Age: {age}")
        print(f"- Interests: {interests}")
        print(f"- Number of pages: {pages}")
        print(f"- Image generation: WITHOUT reference (prompt-only consistency)")
        print("-" * 40)
        
        # Ask for confirmation
        confirm = input("\nGenerate storybook with these details? (y/n): ").lower().strip()
        if confirm != "y" and confirm != "yes":
            print("Storybook generation cancelled.")
            return
        
        # Create a story request
        req = StoryRequest(
            child_name=name,
            child_age=age,
            interests=interests,
            page_count=pages
        )
        
        # Generate the storybook
        result = generate_storybook(req)
        
        # Show completion message
        minutes, seconds = result["elapsed_time"]
        output_dir = result["output_dir"]
        
        print("\n" + "=" * 80)
        print(f"Storybook generation complete! (Time taken: {minutes}m {seconds}s)")
        print(f"Title: {result['title']}")
        print("\nOutput files:")
        print(f"- PDF storybook: {result['pdf_path']} (NO REFERENCE VERSION)")
        print(f"- Cover image: {output_dir / 'cover.png'}")
        print(f"- Individual page images: {output_dir / 'pages/'}")
        print("=" * 80)
        print("\nNote: This version did NOT use reference images for consistency.")
        print("To compare with the reference-based version, run generate_storybook.py")
        
    except KeyboardInterrupt:
        print("\nStorybook generation cancelled by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main() 