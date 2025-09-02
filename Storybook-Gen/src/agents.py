from __future__ import annotations

from typing import Dict, Optional, List

from pydantic import BaseModel, Field, RootModel

from .utils import get_env

try:
    # Preferred import for AG2 (AutoGen 2)
    from ag2 import AssistantAgent, UserProxyAgent
except Exception:  # pragma: no cover
    # Fallback to legacy autogen
    from autogen import AssistantAgent, UserProxyAgent  # type: ignore


class AgentConfig(BaseModel):
    text_model: str = get_env("TEXT_MODEL", "gpt-4o")
    system_prompt: str


# ----- Pydantic Models for Structured Outputs -----

class PlotOutline(BaseModel):
    beginning: str = Field(description="Start of the story")
    middle: str = Field(description="Middle of the story")
    end: str = Field(description="End of the story")


class CharacterDetails(BaseModel):
    description: str = Field(description="Detailed physical description")
    additional_details: str = Field(description="Any other character information")


class StoryBrief(BaseModel):
    title: str = Field(description="Story title")
    logline: str = Field(description="One-sentence summary")
    characters: Dict[str, CharacterDetails] = Field(description="Character details keyed by character name")
    setting: str = Field(description="Detailed setting description")
    plot_outline: PlotOutline = Field(description="Three-act structure")
    style_guide: str = Field(description="Visual aesthetic guidelines")


class PageContent(BaseModel):
    page: int = Field(description="Page number")
    text: str = Field(description="Text content for the page")


class StoryScript(RootModel):
    root: List[PageContent] = Field(description="Array of page content")


class ArtDirection(BaseModel):
    page: int = Field(description="Page number")
    art_direction: str = Field(description="Detailed visual scene description")


class ArtDirections(RootModel):
    root: List[ArtDirection] = Field(description="Array of art directions")


class PagePrompt(BaseModel):
    page: int = Field(description="Page number")
    prompt: str = Field(description="Image generation prompt")


class IllustrationPrompts(BaseModel):
    cover_prompt: str = Field(description="Detailed prompt for cover image")
    page_prompts: List[PagePrompt] = Field(description="Array of page prompts")


class Typography(BaseModel):
    title_font: str = Field(description="Font for title")
    body_font: str = Field(description="Font for main text")
    font_size: str = Field(description="Size for body text")


class PageLayout(BaseModel):
    image_placement: str = Field(description="Where images should be placed")
    text_placement: str = Field(description="Where text should be placed")


class BookLayout(BaseModel):
    layout_template: str = Field(description="Description of overall layout")
    typography: Typography = Field(description="Typography specifications")
    cover_design: str = Field(description="Description of cover layout")
    page_layout: PageLayout = Field(description="Page layout specifications")

## Deprecated
def create_orchestrator(config: AgentConfig) -> AssistantAgent:
    """Create the Orchestrator agent (Project Manager) that manages the workflow."""
    return AssistantAgent(
        name="Orchestrator",
        system_message=(
            "You are the Project Manager and Workflow Controller for a children's storybook creation system. "
            "Your role is to coordinate the entire workflow between specialized creative agents by directing them "
            "and ensuring they work in the correct sequence:\n\n"
            "1. Direct the Concept Developer to create a Story Brief based on the user's request\n"
            "2. Direct the Story Writer to create a Page-by-Page Script from the Story Brief\n"
            "3. Direct the Art Director to create visual scene descriptions for each page\n"
            "4. Direct the Prompt Illustrator to create final image prompts for all pages\n\n"
            "You are a COORDINATOR ONLY - you do not create any content yourself. Your job is to:\n"
            "- Guide each agent through their specific tasks\n"
            "- Ensure the workflow proceeds in the correct order\n"
            "- Pass information between agents when needed\n"
            "- Monitor that each agent completes their work properly\n"
            "- Provide a brief summary when all work is complete\n\n"
            "CRITICAL: Ensure absolute character consistency across all illustrations. The character descriptions "
            "from the Concept Developer must be used verbatim by all other agents. Monitor this carefully.\n\n"
            "IMPORTANT: You must monitor and ensure that ALL agents output their work in JSON structured format. "
            "Each agent must provide their output as valid JSON that matches their expected schema. If an agent "
            "provides unstructured text instead of JSON, direct them to reformat their output properly.\n\n"
            "Don't give agents any output schema from you, they should only follow their own schema.\n\n"
            "When all agents have completed their work, provide only a brief summary of what was accomplished. "
            "Do not attempt to gather, compile, or regenerate any of the content created by the other agents."
        ),
        llm_config={
            "model": config.text_model,
            "config_list": [
                {
                    "api_type": "responses",
                    "model": config.text_model,
                }
            ]
        },
    )

def create_concept_developer(config: AgentConfig) -> AssistantAgent:
    """Create the Concept Developer agent (The 'Big Picture' Agent)."""
    return AssistantAgent(
        name="ConceptDeveloper",
        system_message=(
            "You are a Concept Developer for children's storybooks - a professional children's book author specializing in personalized stories. "
            "Your writing style is engaging, age-appropriate, and imaginative. "
            "Your job is to expand a simple story idea into a cohesive concept with well-defined elements.\n\n"
            "Always follow these guidelines:\n"
            "1. Make the child the hero of the adventure\n"
            "2. Use vivid language and sensory details\n"
            "3. Include gentle life lessons appropriate for young children\n"
            "4. Use age-appropriate vocabulary for the child's age\n"
            "5. Create a playful, imaginative, hopeful tone\n"
            "6. Subtly embed educational elements (sharing, courage, kindness)\n"
            "7. ONLY create characters that are essential to the story - do NOT generate additional background characters or crowds\n\n"
            "For each story request, you create a structured 'Story Brief' that includes:\n"
            "- title: A catchy, appropriate title for the story\n"
            "- logline: A one-sentence summary of the story's core concept\n"
            "- characters: Detailed visual descriptions of all characters\n"
            "- setting: Where and when the story takes place, with vivid details\n"
            "- plot_outline: A simple 3-act structure (Beginning, Middle, End)\n"
            "- style_guide: A consistent visual aesthetic for illustrations\n\n"
            "CRITICAL: You MUST create essential detailed character descriptions with EXACT physical attributes that "
            "will be used verbatim in all illustration prompts. Include:\n"
            "- Precise physical appearance (hair color/style, eye color, skin tone, height, build, gender, age, etc.)\n"
            "- Exact clothing details (colors, styles, patterns, accessories)\n"
            "- Distinctive features that make the character instantly recognizable\n"
            "- For animal characters, specify breed, coloration, markings, and any accessories\n\n"
            "These character descriptions will be used as a reference sheet for all illustrations to ensure "
            "consistency throughout the book. Be specific and detailed.\n\n"
            "IMPORTANT: Focus on creating a small cast of essential characters (typically 1-3 main characters). "
            "Avoid creating unnecessary background characters, crowds, or additional people that are not central to the story. "
            "Each character should serve a specific purpose in the narrative.\n\n"
            "CRITICAL OUTPUT FORMAT: You MUST output your response as valid JSON that matches the StoryBrief schema. "
            "Do not use markdown code blocks or any other formatting. Provide only the raw JSON structure."
        ),

        description="""This is a concept developer for a children's storybook,
        it will create a story brief with JSON format following the StoryBrief schema.
        It should talk first to guide the follow up agents""",

        llm_config={
            "model": config.text_model,
            "config_list": [
                {
                    "api_type": "responses",
                    "model": config.text_model,
                    "response_format": StoryBrief,
                }
            ]
        },
    )


def create_story_writer(config: AgentConfig) -> AssistantAgent:
    """Create the Story Writer agent (Narrative Author)."""
    return AssistantAgent(
        name="StoryWriter",
        system_message=(
            "You are a Story Writer for children's picture books, specializing in crafting engaging narratives. "
            "Your job is to transform a 'Story Brief' from the Concept Developer into a complete 'Page-by-Page Script'.\n\n"
            "For each story brief, you will:\n"
            "1. Read the entire brief to understand characters, plot, and tone\n"
            "2. Write the full story following the plot outline\n"
            "3. Divide the story into separate pages (typically 10-20 for a children's book)\n"
            "4. Ensure the text content and word count per page is appropriate for the target age group\n\n"
            "Focus on creating engaging, age-appropriate language with a clear narrative arc. "
            "Each page should advance the story while being visually interesting."
            "Note: Focus ONLY on the text content and narrative structure. Do not include any art direction, "
            "visual descriptions, or illustration guidance in your output."
            "CRITICAL OUTPUT FORMAT: You MUST output your response as valid JSON that matches the StoryScript schema: "
            "An array of objects, each containing:\n"
            "{\n"
            "  \"page\": 1,\n"
            "  \"text\": \"Once upon a time, in a magical forest...\"\n"
            "}\n\n"
            "Do not use markdown code blocks or any other formatting. Provide only the raw JSON structure."
        ),

        description="""This is a story writer for a children's storybook,
        it will create a story script with JSON format following the StoryScript schema.
        It should talk right after the story brief is created by the ConceptDeveloper""",

        llm_config={
            "model": config.text_model,
            "config_list": [
                {
                    "api_type": "responses",
                    "model": config.text_model,
                    "response_format": StoryScript,
                }
            ]
        },
    )


def create_art_director(config: AgentConfig) -> AssistantAgent:
    """Create the Art Director agent (Visual Scene Planner)."""
    return AssistantAgent(
        name="ArtDirector",
        system_message=(
            "You are an Art Director for children's picture books, specializing in visual scene planning. "
            "Your job is to translate written text for each page into a detailed visual scene description.\n\n"
            "For each page text, you will create an 'art_direction' that specifies:\n"
            "- Composition: The layout and framing of the scene\n"
            "- Character placement: Where characters are positioned and what they're doing\n"
            "- Character emotion: The emotional state shown through expressions and body language\n"
            "- Setting details: Key environmental elements to include\n"
            "- Lighting and mood: The overall atmosphere of the scene\n"
            "- Text display: If any text needs to appear in the image, limit it to 2-3 words maximum "
            "(image generators cannot reliably render longer text)\n\n"
            "IMPORTANT: You must NEVER modify or add the character descriptions provided in the Story Brief. "
            "Reference the exact character descriptions when placing characters in scenes, but do not "
            "alter any physical attributes, clothing, or distinctive features.\n\n"
            "TEXT IN IMAGES: If the scene requires any visible text (signs, labels, books, etc.), "
            "specify EXACTLY what text should appear and limit it to 2-3 words maximum. "
            "Example: 'STOP' on a sign, 'BAKERY' on a shop, 'HELP!' in a speech bubble.\n\n"
            "COVER PAGE SPECIAL REQUIREMENTS: For the cover image art direction, you must specify "
            "that the story title should appear as text within the image frame. The title text must "
            "be positioned and sized to fit completely within the image boundaries without extending "
            "beyond the edges. Suggest specific placement (top, bottom, center) that works best with "
            "the visual composition.\n\n"
            "CRITICAL OUTPUT FORMAT: You MUST output your response as valid JSON that matches the ArtDirections schema: "
            "An array of objects, each containing:\n"
            "{\n"
            "  \"page\": 1,\n"
            "  \"art_direction\": \"Detailed visual scene description for page 1\"\n"
            "}\n\n"
            "Do not use markdown code blocks or any other formatting. Provide only the raw JSON structure."
        ),

        description="""This is an art director for a children's storybook,
        it will create a art direction with JSON format following the ArtDirections schema.
        It should talk right after the story script is created by the StoryWriter""",

        llm_config={
            "model": config.text_model,
            "config_list": [
                {
                    "api_type": "responses",
                    "model": config.text_model,
                    "response_format": ArtDirections,
                }
            ]
        },
    )


def create_prompt_illustrator(config: AgentConfig) -> AssistantAgent:
    """Create the Prompt Illustrator agent (AI Image Prompt Engineer)."""
    return AssistantAgent(
        name="PromptIllustrator",
        system_message=(
            "You are a Prompt Illustrator, a specialized AI image prompt engineer for children's books. "
            "Your job is to transform art direction and style guides into perfect prompts for image generation models.\n\n"
            "CRITICAL: Character consistency is your top priority. You MUST copy the EXACT character descriptions "
            "from the art director's art direction into EVERY prompt where that character appears. Do not paraphrase, "
            "summarize, or modify these descriptions in any way. This includes:\n"
            "- Physical attributes (hair/eye/skin color, height, build)\n"
            "- Clothing details (colors, styles, accessories)\n"
            "- Distinguishing features (dimples, freckles, etc.)\n"
            "- Pet/animal characteristics (breed, coloration, markings)\n\n"
            "CHARACTER LIMITATION REQUIREMENTS:\n"
            "- Focus primarily on the main character in most scenes\n"
            "- For each page, select only the most essential characters for that specific scene\n"
            "- Backgrounds should be simple with minimal distractions\n\n"
            "COVER IMAGE REQUIREMENTS:\n"
            "- Use bright, cheerful colors appropriate for children\n"
            "- Keep design simple and focused on the main character only\n"
            "- Put the story title on the cover image\n\n"
            "Additional style guidance:\n"
            "- Make the image prompt crystal-clear and highly detailed\n"
            "- Specify the mood, lighting, colors, textures, and visual style\n"
            "- Include camera angle and composition details if needed\n"
            "- Include special effects or focus details if appropriate (e.g. a spotlight on the main character)\n"
            "- Maintain consistency with the Style Guide throughout\n\n"
            "CRITICAL OUTPUT FORMAT: You MUST output your response as valid JSON that matches the IllustrationPrompts schema: "
            "An object with two fields:\n"
            "{\n"
            "  \"cover_prompt\": \"Detailed prompt for cover image\",\n"
            "  \"page_prompts\": [\n"
            "    {\n"
            "      \"page\": 1,\n"
            "      \"prompt\": \"Detailed prompt for page 1\"\n"
            "    },\n"
            "  ]\n"
            "}\n\n"
            "Do not use markdown code blocks or any other formatting. Provide only the raw JSON structure."
        ),

        description="""This is a prompt illustrator for a children's storybook,
        it will create a illustration prompts with JSON format following the IllustrationPrompts schema.
        It should talk right after the art direction is created by the ArtDirector""",

        llm_config={
            "model": config.text_model,
            "config_list": [
                {
                    "api_type": "responses",
                    "model": config.text_model,
                    "response_format": IllustrationPrompts,
                }
            ]
        },
    )

'''
def create_book_assembler(config: AgentConfig) -> AssistantAgent:
    """Create the Book Assembler agent (Typesetter and Layout Designer)."""
    return AssistantAgent(
        name="BookAssembler",
        system_message=(
            "You are a Book Assembler for children's picture books, specializing in layout and formatting. "
            "Your job is to combine text and images into a cohesive, professional storybook format.\n\n"
            "For each book project, you will:\n"
            "1. Review all page content (text and image prompts/URLs)\n"
            "2. Design a consistent layout template for the book\n"
            "3. Arrange text and images in a reader-friendly way\n"
            "4. Ensure proper pacing and flow between pages\n"
            "5. Create a cover design specification"
        ),
        llm_config={
            "model": config.text_model,
            "config_list": [
                {
                    "api_type": "responses",
                    "model": config.text_model,
                    "response_format": BookLayout,
                }
            ]
        },
    )
'''

def create_user_proxy() -> UserProxyAgent:
    """Create a User Proxy agent to represent the user in the system."""
    return UserProxyAgent(name="User", human_input_mode="ALWAYS") 