from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .agents import (
    AgentConfig,
    create_animator,
    create_book_validator,
    create_illustration_director,
    create_storyboarder,
    create_user_proxy,
    create_writer,
)
from .models import GenerationResult, PagePlan, StoryPlan, StoryRequest
from .openai_helpers import chat_complete, generate_image
from .pdf_builder import build_pdf
from .utils import ensure_output_dir, write_json


def run_pipeline(req: StoryRequest) -> GenerationResult:
    output_dir = ensure_output_dir()
    pages_dir = output_dir / "pages"

    from .utils import get_env
    config = AgentConfig(text_model=get_env("TEXT_MODEL", "gpt-4o-mini"), system_prompt="")

    user = create_user_proxy()
    writer = create_writer(config)
    storyboarder = create_storyboarder(config)
    validator = create_book_validator(config)
    illustrator = create_illustration_director(config)
    animator = create_animator(config)

    # 1) Writer: produce full story with title
    writer_prompt = (
        f"Write a children's picture book story for {req.child_name}, age {req.child_age}. "
        f"Interests: {req.interests or 'adventure and exploration'}. "
        f"Use {req.page_count} pages worth of content. Title the story on the first line."
    )
    story_text = chat_complete(writer_prompt, model=config.text_model)

    # Extract title and body heuristically
    title_line, *body_lines = [l.strip() for l in story_text.splitlines() if l.strip()]
    if title_line.lower().startswith("title:"):
        title = title_line.split(":", 1)[1].strip()
    else:
        title = title_line
        body_lines = body_lines
    body_text = "\n".join(body_lines).strip()

    # 2) Validator: split into N pages and generate character bible
    validator_prompt = (
        "You will receive a story and constraints. Split into pages and produce strict JSON.\n"
        f"PAGES: {req.page_count}\n"
        "JSON KEYS: title, character_bible, pages (array of {text}).\n"
        "Return only JSON.\n\n"
        f"STORY TITLE: {title}\n"
        f"STORY BODY:\n{body_text}"
    )
    plan_json_str = chat_complete(validator_prompt, model=config.text_model)
    try:
        plan_json = json.loads(plan_json_str)
    except Exception:
        # Fallback: naive chunking
        chunks = naive_chunk(body_text, req.page_count)
        plan_json = {
            "title": title,
            "character_bible": f"Main child: {req.child_name}, age {req.child_age}. Interests: {req.interests or 'adventure'}.",
            "pages": [{"text": t} for t in chunks],
        }

    pages: List[PagePlan] = []
    for idx, p in enumerate(plan_json.get("pages", [])[: req.page_count]):
        pages.append(PagePlan(index=idx + 1, text=p.get("text", "")))

    character_bible = plan_json.get("character_bible", f"Child named {req.child_name}.")

    # 3) Storyboarder: illustration notes per page
    for p in pages:
        sb_prompt = (
            "Create concise illustration notes for this page in a children's picture book.\n"
            f"CHARACTER BIBLE: {character_bible}\n"
            f"PAGE TEXT: {p.text}\n"
            "Return 3-5 bullet points, no extra text."
        )
        p.illustration_notes = chat_complete(sb_prompt, model=config.text_model)

    # 4) IllustratorSingleCall: image prompt per page
    for p in pages:
        ill_prompt = (
            "Craft a single image generation prompt for consistent character depiction across the book.\n"
            f"CHARACTER BIBLE: {character_bible}\n"
            f"PAGE TEXT: {p.text}\n"
            f"STORYBOARD NOTES:\n{p.illustration_notes}\n"
            "Return only the prompt, no quotes."
        )
        p.image_prompt = chat_complete(ill_prompt, model=config.text_model)

    # 5) Animator: high-level animation directions
    anim_prompt = (
        "Provide 1-2 sentence animation directions per page, numbered list."
    )
    animation_directions = chat_complete(anim_prompt, model=config.text_model).splitlines()

    # 6) Generate images (cover + pages)
    cover_prompt = (
        f"Children's book cover, whimsical, bright colors. Title: {title}. "
        f"Main character: {req.child_name}, age {req.child_age}. Interests: {req.interests or 'adventure'}. "
        "No text overlay."
    )
    cover_path = output_dir / "cover.png"
    generate_image(cover_prompt, cover_path)

    for p in pages:
        img_path = pages_dir / f"page_{p.index:02d}.png"
        if p.image_prompt:
            generate_image(p.image_prompt, img_path)
            p.image_path = str(img_path)

    # 7) Build PDF
    pdf_path = output_dir / "storybook.pdf"
    build_pdf(pdf_path, title, cover_path, pages)

    # 8) Save plan JSON
    plan = StoryPlan(
        title=title,
        character_bible=character_bible,
        cover_prompt=cover_prompt,
        pages=pages,
        animation_directions=[l for l in animation_directions if l.strip()],
    )
    write_json(output_dir / "plan.json", json.loads(plan.model_dump_json()))

    return GenerationResult(
        plan=plan,
        cover_image_path=str(cover_path),
        pdf_path=str(pdf_path),
        output_dir=str(output_dir),
    )


def naive_chunk(text: str, n: int) -> List[str]:
    words = text.split()
    size = max(1, len(words) // n)
    chunks = []
    for i in range(0, len(words), size):
        chunks.append(" ".join(words[i : i + size]))
    if len(chunks) > n:
        chunks = chunks[:n - 1] + [" ".join(chunks[n - 1 :])]
    while len(chunks) < n:
        chunks.append("")
    return chunks 