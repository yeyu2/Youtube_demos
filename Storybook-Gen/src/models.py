from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class StoryRequest(BaseModel):
    child_name: str
    child_age: int
    interests: Optional[str] = None
    page_count: int = Field(default=10, ge=3, le=24)


class PagePlan(BaseModel):
    index: int
    text: str
    illustration_notes: Optional[str] = None
    image_prompt: Optional[str] = None
    image_path: Optional[str] = None


class StoryPlan(BaseModel):
    title: str
    character_bible: str
    cover_prompt: str
    pages: List[PagePlan]
    animation_directions: List[str] = Field(default_factory=list)


class GenerationResult(BaseModel):
    plan: StoryPlan
    cover_image_path: str
    pdf_path: str
    output_dir: str 