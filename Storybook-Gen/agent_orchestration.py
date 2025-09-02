#!/usr/bin/env python3
"""
Agent-based orchestration for storybook generation using AG2/AutoGen.
This script uses a dedicated Orchestrator agent to direct the workflow.
"""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
import traceback

try:
    # Preferred import for AG2
    from ag2 import GroupChat, GroupChatManager
except ImportError:
    # Fallback to legacy autogen
    from autogen import GroupChat, GroupChatManager  # type: ignore

from src.models import StoryRequest, PagePlan, StoryPlan
from src.utils import load_environment, ensure_output_dir, get_env, write_json
from src.agents import (
    AgentConfig, 
    create_orchestrator,
    create_concept_developer,
    create_story_writer,
    create_art_director,
    create_prompt_illustrator,
    create_user_proxy
)
from src.costs import (
    summarize_agent_usage,
    compute_text_cost,
    aggregate_tokens,
    estimate_tokens,
    compute_image_prompt_cost,
    compute_image_cost,
)
from src.pdf_builder import build_pdf


def run_agent_orchestration(req: StoryRequest) -> Dict:
    """Run the storybook generation using agent-based orchestration."""
    output_dir = ensure_output_dir()
    print(f"Output directory: {output_dir}")
    
    # Create config with model from environment
    config = AgentConfig(text_model=get_env("TEXT_MODEL", "gpt-4o"), system_prompt="")
    print(f"Using model: {config.text_model}")
    
    # Create all agents
    user = create_user_proxy()
    orchestrator = create_orchestrator(config)
    concept_developer = create_concept_developer(config)
    story_writer = create_story_writer(config)
    art_director = create_art_director(config)
    prompt_illustrator = create_prompt_illustrator(config)
    
    # Reset usage tracking for all agents
    for agent in [orchestrator, concept_developer, story_writer, art_director, prompt_illustrator, user]:
        if hasattr(agent, "reset"):
            agent.reset()
    
    # Set up group chat with orchestrator as manager
    group_chat = GroupChat(
        agents=[
            user, 
            #orchestrator, 
            concept_developer, 
            story_writer, 
            art_director, 
            prompt_illustrator
        ],
        messages=[],
        max_round=20,  # Increased to accommodate the more complex workflow
    )
    
    manager = GroupChatManager(
        groupchat=group_chat,
        llm_config={"model": config.text_model}
    )
    
    # Start the conversation with request details
    initial_message = (
        f"I need to create a children's storybook with these requirements:\n"
        f"- Child's name: {req.child_name}\n"
        f"- Child's age: {req.child_age}\n"
        f"- Interests: {req.interests or 'adventure and exploration'}\n"
        f"- Number of pages: {req.page_count}\n\n"
        f"Please orchestrate the creation of this storybook,"
        f"please begin by asking the ConceptDeveloper to create a Story Brief with detailed character descriptions."
    )
    
    # Save chat log to file for analysis
    chat_log_path = output_dir / "chat_log.txt"
    
    # Run the group chat
    with open(chat_log_path, "w") as chat_log:
        chat_log.write(f"INITIAL REQUEST:\n{initial_message}\n\n{'='*80}\n\n")
        
        # Start the chat and capture messages as they happen
        print("Starting multi-agent conversation...")
        result = user.initiate_chat(manager, message=initial_message)
        
        # After the chat completes, save all messages
        messages = group_chat.messages
        for msg in messages:
            agent = msg.get("name", "Unknown")
            content = msg.get("content", "")
            chat_log.write(f"AGENT: {agent}\n\n{content}\n\n{'='*80}\n\n")

    # --- Agent token usage and cost summary ---
    try:
        # Import gather_usage_summary from autogen
        from autogen import gather_usage_summary  # type: ignore
        
        # Get all agents
        agents = [orchestrator, concept_developer, story_writer, art_director, prompt_illustrator, user]
        
        # Print individual agent usage
        print("\n--- Agent Usage Summary ---")
        for agent in agents:
            name = getattr(agent, "name", "Unknown")
            print(f"\nAgent '{name}':")
            if hasattr(agent, "print_usage_summary"):
                agent.print_usage_summary()
            else:
                print("No usage data available")
        
        # Gather usage summary for all agents
        usage_summary = gather_usage_summary(agents)
        
        # Extract the combined usage data
        combined_usage = {
            "actual": usage_summary.get("usage_excluding_cached_inference", {}),
            "total": usage_summary.get("usage_including_cached_inference", {})
        }
        
        # Format for our cost report
        per_agent_costs = {}
        for agent in agents:
            name = getattr(agent, "name", "Unknown")
            # Get actual usage (non-cached)
            usage = None
            if hasattr(agent, "get_actual_usage"):
                usage = agent.get_actual_usage()
            
            if usage:
                # Extract model name and token counts
                model_name = next(iter(usage.keys()), config.text_model)
                if model_name == "total_cost":
                    # Find the actual model name
                    for key in usage.keys():
                        if key != "total_cost":
                            model_name = key
                            break
                
                tokens = {
                    "input": usage.get(model_name, {}).get("prompt_tokens", 0),
                    "cached_input": 0,  # We don't track cached separately in this report
                    "output": usage.get(model_name, {}).get("completion_tokens", 0)
                }
                cost = usage.get("total_cost", 0.0)
                
                per_agent_costs[name] = {
                    "model": model_name,
                    "tokens": tokens,
                    "cost_usd": round(cost, 6)
                }
        
        # Calculate totals
        total_tokens = {
            "input": combined_usage["actual"].get("prompt_tokens", 0),
            "cached_input": 0,  # We don't track cached separately in this report
            "output": combined_usage["actual"].get("completion_tokens", 0)
        }
        total_cost = combined_usage["actual"].get("total_cost", 0.0)
        
        # Create the final report
        agents_cost_report = {
            "per_agent": per_agent_costs,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
        }
        
        # Save the report
        write_json(output_dir / "agents_cost_report.json", agents_cost_report)
        print(f"Saved agents cost report: {output_dir / 'agents_cost_report.json'}")
        
    except Exception as e:
        print(f"Usage summary not available: {e}")

    # Log the final group chat state before extraction
    print("\n--- FINAL GROUP CHAT STATE BEFORE EXTRACTION ---")
    messages = group_chat.messages
    print(f"Total messages: {len(messages)}")
    agent_message_counts = {}
    for msg in messages:
        agent = msg.get("name", "Unknown")
        agent_message_counts[agent] = agent_message_counts.get(agent, 0) + 1
    print("Messages per agent:")
    for agent, count in agent_message_counts.items():
        print(f"  {agent}: {count} messages")
    
    # Log the last message from each agent
    print("\nLast message from each agent:")
    last_messages = {}
    for msg in messages:
        agent = msg.get("name", "Unknown")
        last_messages[agent] = msg
    
    for agent, msg in last_messages.items():
        content = msg.get("content", "")
        content_size = len(content)
        content_preview = content[:100] + "..." if content_size > 100 else content
        print(f"  {agent} (size: {content_size} chars): {content_preview}")
    
    # Log the final message specifically
    final_msg = messages[-1] if messages else {}
    final_agent = final_msg.get("name", "None")
    final_content = final_msg.get("content", "")
    final_size = len(final_content)
    print(f"\nFinal message was from: {final_agent} (size: {final_size} chars)")
    
    # Save the final message content to a separate file for analysis
    final_message_path = output_dir / "final_message.txt"
    with open(final_message_path, "w") as f:
        f.write(f"AGENT: {final_agent}\n\n{final_content}")
    print(f"Final message saved to: {final_message_path}")
    print("--- END OF GROUP CHAT STATE LOG ---\n")

    # Extract the final plan from the conversation
    messages = group_chat.messages
    
    # Save raw messages for debugging
    write_json(output_dir / "raw_messages.json", [m.copy() for m in messages])
    
    # Extract story content
    story_content = extract_story_from_messages(messages)
    
    # Check for character consistency across prompts
    character_descriptions = extract_character_descriptions(story_content)
    consistency_report = check_character_consistency(story_content, character_descriptions)
    
    # Save the extracted content
    with open(output_dir / "extracted_story.json", "w") as f:
        json.dump(story_content, f, indent=2)
        
    # Save character descriptions separately for reference
    with open(output_dir / "character_descriptions.json", "w") as f:
        json.dump(character_descriptions, f, indent=2)
        
    # Save consistency report
    with open(output_dir / "consistency_report.json", "w") as f:
        json.dump(consistency_report, f, indent=2)
    
    print(f"Chat log saved to: {chat_log_path}")
    print(f"Extracted story saved to: {output_dir / 'extracted_story.json'}")
    print(f"Character descriptions saved to: {output_dir / 'character_descriptions.json'}")
    print(f"Consistency report saved to: {output_dir / 'consistency_report.json'}")
    
    # Ensure output_dir is included in the return value
    story_content["output_dir"] = str(output_dir)
    return story_content


def extract_character_descriptions(story_content: Dict) -> Dict:
    """Extract character descriptions from the story brief."""
    character_descriptions = {}
    
    # Try to extract from story_brief
    if "story_brief" in story_content and isinstance(story_content["story_brief"], dict):
        brief = story_content["story_brief"]
        
        # Look for characters in different possible formats
        if "characters" in brief and isinstance(brief["characters"], list):
            for char in brief["characters"]:
                if isinstance(char, dict) and "name" in char and "description" in char:
                    character_descriptions[char["name"]] = char["description"]
        
        # Alternative format
        if "characters" in brief and isinstance(brief["characters"], dict):
            for name, desc in brief["characters"].items():
                if isinstance(desc, dict) and "description" in desc:
                    character_descriptions[name] = desc["description"]
                elif isinstance(desc, str):
                    character_descriptions[name] = desc
                
        # Look for character_bible or characterBible
        for key in ["character_bible", "characterBible", "character_descriptions", "characterDescriptions"]:
            if key in brief and isinstance(brief[key], dict):
                for name, desc in brief[key].items():
                    character_descriptions[name] = desc
    
    return character_descriptions


def check_character_consistency(story_content: Dict, character_descriptions: Dict) -> Dict:
    """Check if character descriptions are consistently used across all prompts."""
    consistency_report = {
        "consistent": True,
        "issues": [],
        "character_presence": {}
    }
    
    # Initialize character presence tracking
    for char_name in character_descriptions:
        consistency_report["character_presence"][char_name] = []
    
    # Check each page's image prompt
    if "pages" in story_content and isinstance(story_content["pages"], list):
        for i, page in enumerate(story_content["pages"]):
            page_num = page.get("page", i+1)
            
            if "image_prompt" in page and page["image_prompt"]:
                prompt = page["image_prompt"].lower()
                
                # Check each character
                for char_name, description in character_descriptions.items():
                    char_name_lower = char_name.lower()
                    
                    # Check if character is mentioned in the prompt
                    if char_name_lower in prompt:
                        consistency_report["character_presence"][char_name].append(page_num)
                        
                        # Check if description elements are included
                        desc_lower = description.lower()
                        key_elements = extract_key_elements(desc_lower)
                        
                        for element in key_elements:
                            if element not in prompt:
                                consistency_report["consistent"] = False
                                consistency_report["issues"].append({
                                    "page": page_num,
                                    "character": char_name,
                                    "missing_element": element,
                                    "prompt": page["image_prompt"]
                                })
    
    return consistency_report


def extract_key_elements(description: str) -> List[str]:
    """Extract key elements from a character description."""
    key_elements = []
    
    # Common physical attributes to look for
    attributes = [
        "hair", "eyes", "skin", "height", "build", 
        "wearing", "clothes", "outfit", "dressed",
        "color", "style", "pattern"
    ]
    
    # For animals
    animal_attributes = [
        "breed", "fur", "coat", "markings", "color", "pattern"
    ]
    
    # Extract sentences or phrases containing these attributes
    sentences = description.split(". ")
    for sentence in sentences:
        for attr in attributes + animal_attributes:
            if attr in sentence.lower():
                # Clean up and add the key element
                element = sentence.strip().rstrip(".").lower()
                if element and len(element) > 10:  # Minimum meaningful length
                    key_elements.append(element)
                break
    
    return key_elements


def extract_story_from_messages(messages: List[Dict]) -> Dict:
    """Extract story content from the chat messages by directly using each agent's output."""
    story_content = {
        "title": "Untitled Story",
        "story_brief": {},
        "pages": [],
        "cover_prompt": "",
    }
    
    # Helper function to extract JSON from content
    def extract_json_from_content(content):
        # First, check if the content is already valid JSON (from structured output)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # If not, try to find JSON in code blocks (for backward compatibility)
            json_matches = re.findall(r'```(?:json)?\s*([\s\S]*?)```', content)
            for json_str in json_matches:
                try:
                    return json.loads(json_str.strip())
                except json.JSONDecodeError:
                    continue
            return None
    
    # Track the most recent message from each agent
    agent_outputs = {
        "ConceptDeveloper": None,
        "StoryWriter": None,
        "ArtDirector": None,
        "PromptIllustrator": None,
    }
    
    # First pass: collect the latest output from each agent
    for msg in messages:
        role = msg.get("name", "")
        if role in agent_outputs:
            agent_outputs[role] = msg.get("content", "")
    
    # Process ConceptDeveloper output for title and story brief
    if agent_outputs["ConceptDeveloper"]:
        concept_json = extract_json_from_content(agent_outputs["ConceptDeveloper"])
        if concept_json:
            # Extract story brief
            story_content["story_brief"] = concept_json
            
            # Extract title - look in multiple possible locations
            if "title" in concept_json:
                story_content["title"] = concept_json["title"]
            elif "project_title" in concept_json:
                story_content["title"] = concept_json["project_title"]
            elif "story_brief" in concept_json and "title" in concept_json["story_brief"]:
                story_content["title"] = concept_json["story_brief"]["title"]
    
    # Process StoryWriter output for page texts
    if agent_outputs["StoryWriter"]:
        writer_json = extract_json_from_content(agent_outputs["StoryWriter"])
        if writer_json:
            # Handle both list directly or RootModel structure with 'root' field
            pages_list = writer_json
            if isinstance(writer_json, dict):
                if "root" in writer_json:  # RootModel structure
                    pages_list = writer_json["root"]
                elif "pages" in writer_json:  # Alternative format
                    pages_list = writer_json["pages"]
                
            if isinstance(pages_list, list):
                # Process the page array
                for page in pages_list:
                    if isinstance(page, dict) and "page" in page and "text" in page:
                        # Create or update page in story_content
                        story_content["pages"].append({
                            "page": page["page"],
                            "text": page["text"]
                        })
    
    # Process ArtDirector output for art directions
    if agent_outputs["ArtDirector"]:
        art_json = extract_json_from_content(agent_outputs["ArtDirector"])
        if art_json:
            # Handle both list directly or RootModel structure with 'root' field
            art_directions = art_json
            if isinstance(art_json, dict) and "root" in art_json:
                art_directions = art_json["root"]
                
            if isinstance(art_directions, list):
                # Process the art directions list
                for art_dir in art_directions:
                    if isinstance(art_dir, dict) and "page" in art_dir and "art_direction" in art_dir:
                        page_num = art_dir["page"]
                        
                        # Find the corresponding page
                        for page in story_content["pages"]:
                            if page.get("page") == page_num:
                                page["art_direction"] = art_dir["art_direction"]
                                break
    
    # Process PromptIllustrator output for image prompts
    if agent_outputs["PromptIllustrator"]:
        prompt_json = extract_json_from_content(agent_outputs["PromptIllustrator"])
        if prompt_json and isinstance(prompt_json, dict):
            # Direct use of PromptIllustrator's cover_prompt
            if "cover_prompt" in prompt_json:
                story_content["cover_prompt"] = prompt_json["cover_prompt"]
                
                # Extract title from cover prompt if not already set
                if story_content["title"] == "Untitled Story" and story_content["cover_prompt"]:
                    # Look for title in the cover prompt
                    title_match = re.search(r'Title text: ["\']([^"\']+)["\']', story_content["cover_prompt"])
                    if title_match:
                        story_content["title"] = title_match.group(1)
                    else:
                        # Try another pattern
                        title_match = re.search(r'title: ["\']([^"\']+)["\']', story_content["cover_prompt"], re.IGNORECASE)
                        if title_match:
                            story_content["title"] = title_match.group(1)
            
            # Direct use of PromptIllustrator's page_prompts
            if "page_prompts" in prompt_json and isinstance(prompt_json["page_prompts"], list):
                story_content["page_prompts"] = prompt_json["page_prompts"]  # Store the complete page_prompts array
                for prompt in prompt_json["page_prompts"]:
                    if isinstance(prompt, dict) and "page" in prompt and "prompt" in prompt:
                        page_num = prompt["page"]
                        
                        # Find the corresponding page
                        for page in story_content["pages"]:
                            if page.get("page") == page_num:
                                page["image_prompt"] = prompt["prompt"]
                                break
    
    # Sort pages by page number
    story_content["pages"] = sorted(story_content["pages"], key=lambda x: x.get("page", 999))
    
    # Ensure all pages have the required fields
    for page in story_content["pages"]:
        if "text" not in page:
            page["text"] = f"Text for page {page.get('page', '?')}"
        if "image_prompt" not in page:
            if "art_direction" in page:
                page["image_prompt"] = f"Children's storybook illustration. {page['art_direction']}"
            else:
                page["image_prompt"] = f"Children's storybook illustration for page {page.get('page', '?')}"
    
    # Add a note about the extraction method
    story_content["extraction_method"] = "direct_from_agents"
    
    # If pages array is empty but we have page_prompts, create pages from the prompts
    if not story_content["pages"] and "page_prompts" in story_content and isinstance(story_content["page_prompts"], list):
        for prompt in story_content["page_prompts"]:
            if isinstance(prompt, dict) and "page" in prompt and "prompt" in prompt:
                page_num = prompt["page"]
                story_content["pages"].append({
                    "page": page_num,
                    "text": f"Text for page {page_num}",  # Default text
                    "image_prompt": prompt["prompt"]
                })
        
        # Sort pages by page number
        story_content["pages"] = sorted(story_content["pages"], key=lambda x: x.get("page", 999))
    
    return story_content


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Generate a personalized children's storybook")
    parser.add_argument(
        "--name", "-n", 
        help="Child's name for the storybook"
    )
    parser.add_argument(
        "--age", "-a", 
        type=int, 
        help="Child's age"
    )
    parser.add_argument(
        "--interests", "-i", 
        help="Child's interests (comma separated)"
    )
    parser.add_argument(
        "--pages", "-p", 
        type=int, 
        default=5,
        help="Number of pages in the storybook (default: 5)"
    )
    parser.add_argument(
        "--use-reference", "-r",
        action="store_true",
        help="Use cover image as reference for character consistency in all page images"
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    # Load environment variables
    load_environment()
    
    # Parse command line arguments
    args = parse_args()

    # Create a story request from arguments or prompt for input
    req = StoryRequest(
        child_name=args.name or input("Child's name: "),
        child_age=args.age or int(input("Child's age: ")),
        interests=args.interests or input("Child's interests (optional): "),
        page_count=args.pages
    )

    # Run the agent orchestration
    story_content = run_agent_orchestration(req)
    
    # Get the output directory from story_content
    output_dir = Path(story_content.get("output_dir", ""))
    if not output_dir or not output_dir.exists():
        output_dir = ensure_output_dir()
    
    # Extract character descriptions and check consistency
    character_descriptions = extract_character_descriptions(story_content)
    write_json(output_dir / "character_descriptions.json", character_descriptions)
    
    # Check character consistency in prompts
    consistency_report = check_character_consistency(story_content, character_descriptions)
    write_json(output_dir / "consistency_report.json", consistency_report)
    
    # Save extracted story content
    write_json(output_dir / "extracted_story.json", story_content)
    
    # --- Image prompt token and cost estimation (input-side only) ---
    try:
        image_prompts = []
        if story_content.get("cover_prompt"):
            image_prompts.append(story_content["cover_prompt"])
        for p in story_content.get("pages", []):
            if p.get("image_prompt"):
                image_prompts.append(p["image_prompt"])
        
        # Use the new compute_image_cost function for each prompt
        image_model = get_env("IMAGE_MODEL", "gpt-image-1")
        prompt_details = []
        for prompt in image_prompts:
            cost_info = compute_image_cost(image_model, prompt=prompt)
            prompt_details.append(cost_info)
        
        # Aggregate costs
        total_input_tokens = sum(cost["input_tokens"] for cost in prompt_details)
        total_cost = sum(cost["total_cost_usd"] for cost in prompt_details)
        
        image_cost_report = {
            "model": image_model,
            "prompts_count": len(image_prompts),
            "prompt_details": prompt_details,
            "total_input_tokens": total_input_tokens,
            "total_cost_usd": round(total_cost, 6),
            "note": "This is an estimate based on prompt tokens only. Actual costs may vary."
        }
        
        write_json(output_dir / "image_cost_report.pre_generation.json", image_cost_report)
        print(f"Saved image cost estimate (prompts): {output_dir / 'image_cost_report.pre_generation.json'}")
    except Exception as e:
        print(f"Failed to estimate image prompt costs: {e}")
        traceback.print_exc()
    
    # Generate images using image_generator.py (imported as a module)
    from image_generator import generate_storybook_images
    image_usages = generate_storybook_images(
        str(output_dir / "extracted_story.json"),
        delay_seconds=3,
        use_reference=args.use_reference
    )
    
    # Re-load story_with_images.json to finalize image prompt cost report
    try:
        with open(output_dir / "story_with_images.json", "r") as f:
            story_with_images = json.load(f)
        
        # If we have actual usage data from the API, use it
        if image_usages:
            # Create new report with actual usage data
            image_model = get_env("IMAGE_MODEL", "gpt-image-1")
            image_details = []
            for usage in image_usages:
                cost_info = compute_image_cost(image_model, api_usage=usage)
                image_details.append(cost_info)
            
            # Aggregate costs
            total_input_tokens = sum(cost["input_tokens"] for cost in image_details)
            total_output_tokens = sum(cost["output_tokens"] for cost in image_details)
            total_cost = sum(cost["total_cost_usd"] for cost in image_details)
            
            image_cost_report = {
                "model": image_model,
                "images_count": len(image_details),
                "image_details": image_details,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "total_cost_usd": round(total_cost, 6)
            }
        else:
            # Fall back to estimating from prompts
            image_prompts = []
            if story_with_images.get("cover_prompt"):
                image_prompts.append(story_with_images["cover_prompt"])
            for p in story_with_images.get("pages", []):
                if p.get("image_prompt"):
                    image_prompts.append(p["image_prompt"])
            
            # Use the new compute_image_cost function for each prompt
            image_model = get_env("IMAGE_MODEL", "gpt-image-1")
            prompt_details = []
            for prompt in image_prompts:
                cost_info = compute_image_cost(image_model, prompt=prompt)
                prompt_details.append(cost_info)
            
            # Aggregate costs
            total_input_tokens = sum(cost["input_tokens"] for cost in prompt_details)
            total_cost = sum(cost["total_cost_usd"] for cost in prompt_details)
            
            image_cost_report = {
                "model": image_model,
                "prompts_count": len(image_prompts),
                "prompt_details": prompt_details,
                "total_input_tokens": total_input_tokens,
                "total_cost_usd": round(total_cost, 6),
                "note": "Image output token costs are not included; only prompt (input) tokens estimated."
            }
        
        write_json(output_dir / "image_cost_report.json", image_cost_report)
        print(f"Saved image cost report: {output_dir / 'image_cost_report.json'}")
        
        # Build PDF from the story_with_images.json
        try:
            # Create PagePlan objects from the story pages
            title = story_with_images.get("title", "Untitled Story")
            cover_image = output_dir / "cover.png"
            
            # Get the child's age for appropriate font sizing
            child_age = req.child_age if hasattr(req, "child_age") else 8
            
            # Convert pages to PagePlan objects
            page_plans = []
            for page in story_with_images.get("pages", []):
                page_num = page.get("page", 0)
                
                # Try to get text content - might be in different formats
                text_content = page.get("text", "")
                if not text_content and isinstance(page.get("content"), dict):
                    # Alternative format where content is a nested object
                    text_content = page.get("content", {}).get("text", "")
                
                # If still no text, provide a placeholder
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
            pdf_path = build_pdf(
                output_pdf=output_dir / "storybook.pdf", 
                title=title, 
                cover_image=cover_image, 
                pages=page_plans,
                child_age=child_age
            )
            print(f"PDF storybook generated with age-appropriate typography for a {child_age}-year-old child: {pdf_path}")
        except Exception as e:
            print(f"Failed to build PDF: {e}")
            traceback.print_exc()
        
    except Exception as e:
        print(f"Failed to finalize image cost report: {e}")
        traceback.print_exc()
    
    print("\n== Story Generation Complete ==")
    print(f"Output saved to: {output_dir}")
    
    # Ask if the user wants to continue or finish
    user_choice = input("\nWould you like to continue or finish this chat? (continue/finish): ")
    if user_choice.lower().startswith("f"):
        print("Chat finished. Thank you for using the storybook generator!")


if __name__ == "__main__":
    main() 