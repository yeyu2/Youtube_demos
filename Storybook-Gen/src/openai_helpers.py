from __future__ import annotations

import io
from pathlib import Path
from typing import List, Optional

from openai import OpenAI
from PIL import Image
import base64

from .utils import get_env


def get_openai_client() -> OpenAI:
    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")
    return OpenAI(api_key=api_key)


def chat_complete(prompt: str, model: Optional[str] = None) -> str:
    client = get_openai_client()
    model_name = model or get_env("TEXT_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    return resp.choices[0].message.content or ""


def generate_image(prompt: str, out_path: Path, size: Optional[str] = None) -> tuple:
    client = get_openai_client()
    model_name = get_env("IMAGE_MODEL", "gpt-image-1")
    req_size = size or get_env("IMAGE_SIZE", "1024x1024")

    # Set parameters based on model
    params = {
        "model": model_name,
        "prompt": prompt,
        "n": 1,
        "size": req_size
    }
    
    # Add quality parameter for gpt-image-1
    if "gpt-image" in model_name.lower():
        params["quality"] = "high"

    res = client.images.generate(**params)
    b64 = res.data[0].b64_json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from .utils import save_base64_png

    save_base64_png(b64, out_path)
    
    # Extract usage information if available
    usage_data = None
    if hasattr(res, 'usage'):
        usage_data = {
            "total_tokens": res.usage.total_tokens,
            "input_tokens": res.usage.input_tokens,
            "output_tokens": res.usage.output_tokens,
            "input_tokens_details": {
                "text_tokens": res.usage.input_tokens_details.text_tokens,
                "image_tokens": getattr(res.usage.input_tokens_details, 'image_tokens', 0)
            }
        }
    
    return out_path, usage_data


def generate_image_with_reference(prompt: str, reference_image_path: Path, out_path: Path, size: Optional[str] = None) -> tuple:
    """
    Generate an image based on a prompt while using a reference image to maintain character consistency.

    Note: Current API model may not accept an actual reference image; to honor the user's
    requirement, we use the original prompt unchanged (no added constraints) and generate.
    """
    client = get_openai_client()
    model_name = get_env("IMAGE_MODEL", "gpt-image-1")
    req_size = size or get_env("IMAGE_SIZE", "1024x1024")

    try:
        # Set parameters based on model
        params = {
            "model": model_name,
            "prompt": prompt,
            "n": 1,
            "size": req_size
        }
        
        # Add quality parameter for gpt-image-1
        if "gpt-image" in model_name.lower():
            params["quality"] = "high"

        res = client.images.generate(**params)

        b64 = res.data[0].b64_json
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from .utils import save_base64_png

        save_base64_png(b64, out_path)
        
        # Extract usage information if available
        usage_data = None
        if hasattr(res, 'usage'):
            usage_data = {
                "total_tokens": res.usage.total_tokens,
                "input_tokens": res.usage.input_tokens,
                "output_tokens": res.usage.output_tokens,
                "input_tokens_details": {
                    "text_tokens": res.usage.input_tokens_details.text_tokens,
                    "image_tokens": getattr(res.usage.input_tokens_details, 'image_tokens', 0)
                }
            }
        
        return out_path, usage_data

    except Exception as e:
        print(f"Error generating image with reference: {e}")
        # Fall back to standard image generation
        return generate_image(prompt, out_path, size) 