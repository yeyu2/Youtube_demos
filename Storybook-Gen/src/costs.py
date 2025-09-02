import re
import json
from typing import Dict, List, Union, Optional
import tiktoken

# Price tables for different models (per 1M tokens)
TEXT_PRICE_PER_MILLION = {
    # GPT-5 models
    "gpt-5": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached_input": 0.005, "output": 0.40},
    "gpt-5-chat-latest": {"input": 1.25, "cached_input": 0.125, "output": 10.00},
    
    # GPT-4.1 models
    "gpt-4.1": {"input": 2.00, "cached_input": 0.50, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "cached_input": 0.025, "output": 0.40},
    
    # GPT-4o models
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-2024-05-13": {"input": 5.00, "output": 15.00},
    "gpt-4o-audio-preview": {"input": 2.50, "output": 10.00},
    "gpt-4o-realtime-preview": {"input": 5.00, "cached_input": 2.50, "output": 20.00},
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "gpt-4o-mini-audio-preview": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini-realtime-preview": {"input": 0.60, "cached_input": 0.30, "output": 2.40},
    "gpt-4o-mini-search-preview": {"input": 0.15, "output": 0.60},
    "gpt-4o-search-preview": {"input": 2.50, "output": 10.00},
    
    # o-series models
    "o1": {"input": 15.00, "cached_input": 7.50, "output": 60.00},
    "o1-pro": {"input": 150.00, "output": 600.00},
    "o3-pro": {"input": 20.00, "output": 80.00},
    "o3": {"input": 2.00, "cached_input": 0.50, "output": 8.00},
    "o3-deep-research": {"input": 10.00, "cached_input": 2.50, "output": 40.00},
    "o4-mini": {"input": 1.10, "cached_input": 0.275, "output": 4.40},
    "o4-mini-deep-research": {"input": 2.00, "cached_input": 0.50, "output": 8.00},
    "o3-mini": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
    "o1-mini": {"input": 1.10, "cached_input": 0.55, "output": 4.40},
    
    # Other models
    "codex-mini-latest": {"input": 1.50, "cached_input": 0.375, "output": 6.00},
    "computer-use-preview": {"input": 3.00, "output": 12.00},
    
    # Legacy models (keeping for backward compatibility)
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5},
}

# Image model prices (per 1M tokens)
IMAGE_PRICE_PER_MILLION = {
    "gpt-image-1": {"input": 5.00, "cached_input": 1.25, "output": 40.00},
    "dall-e-3": {"input": 40.00, "output": 80.00},  # Approximate
}

def normalize_model_name(model_name: str) -> str:
    """Normalize model name to match price table keys"""
    if not model_name:
        return "gpt-3.5-turbo"  # Default model
    
    model_name = model_name.lower()
    
    # Direct match
    if model_name in TEXT_PRICE_PER_MILLION or model_name in IMAGE_PRICE_PER_MILLION:
        return model_name
    
    # GPT-5 models
    if "gpt-5" in model_name:
        if "mini" in model_name:
            return "gpt-5-mini"
        if "nano" in model_name:
            return "gpt-5-nano"
        return "gpt-5"
    
    # GPT-4.1 models
    if "gpt-4.1" in model_name:
        if "mini" in model_name:
            return "gpt-4.1-mini"
        if "nano" in model_name:
            return "gpt-4.1-nano"
        return "gpt-4.1"
    
    # GPT-4o models
    if "gpt-4o" in model_name:
        if "mini" in model_name:
            if "audio" in model_name:
                return "gpt-4o-mini-audio-preview"
            if "realtime" in model_name:
                return "gpt-4o-mini-realtime-preview"
            if "search" in model_name:
                return "gpt-4o-mini-search-preview"
            return "gpt-4o-mini"
        if "audio" in model_name:
            return "gpt-4o-audio-preview"
        if "realtime" in model_name:
            return "gpt-4o-realtime-preview"
        if "search" in model_name:
            return "gpt-4o-search-preview"
        if "2024-05-13" in model_name:
            return "gpt-4o-2024-05-13"
        return "gpt-4o"
    
    # O-series models
    if model_name.startswith("o1"):
        if "pro" in model_name:
            return "o1-pro"
        if "mini" in model_name:
            return "o1-mini"
        return "o1"
    if model_name.startswith("o3"):
        if "pro" in model_name:
            return "o3-pro"
        if "deep" in model_name or "research" in model_name:
            return "o3-deep-research"
        if "mini" in model_name:
            return "o3-mini"
        return "o3"
    if model_name.startswith("o4"):
        if "deep" in model_name or "research" in model_name:
            return "o4-mini-deep-research"
        if "mini" in model_name:
            return "o4-mini"
    
    # Legacy GPT-4 models
    if "gpt-4-" in model_name and "turbo" in model_name:
        return "gpt-4-turbo"
    if "gpt-4" in model_name:
        return "gpt-4"
    
    # GPT-3.5 models
    if "gpt-3.5" in model_name:
        return "gpt-3.5-turbo"
    
    # Image models
    if "dall-e-3" in model_name:
        return "dall-e-3"
    if "gpt-image" in model_name:
        return "gpt-image-1"
    
    # Other models
    if "codex" in model_name:
        return "codex-mini-latest"
    if "computer" in model_name:
        return "computer-use-preview"
    
    # Default fallback
    return "gpt-3.5-turbo"

def price_per_token(model_name: str, token_type: str = "input") -> float:
    """Get price per token for a model"""
    model_name = normalize_model_name(model_name)
    
    # Check if it's an image model
    if model_name in IMAGE_PRICE_PER_MILLION:
        price_table = IMAGE_PRICE_PER_MILLION
    else:
        price_table = TEXT_PRICE_PER_MILLION
        
    # Default to gpt-3.5-turbo if model not found
    if model_name not in price_table:
        model_name = "gpt-3.5-turbo"
    
    # Get price per million tokens
    model_prices = price_table[model_name]
    
    # Check if the token type exists for this model
    if token_type not in model_prices:
        # Fall back to input for models that don't have cached_input
        if token_type == "cached_input" and "input" in model_prices:
            token_type = "input"
            # Apply a discount factor for models without explicit cached_input price
            return model_prices[token_type] / 1_000_000 * 0.25
        else:
            # Default to input if the token type doesn't exist
            token_type = "input"
    
    price_per_million = model_prices[token_type]
    
    # Convert to price per token
    return price_per_million / 1_000_000

def estimate_tokens(text: str) -> int:
    """Estimate token count for a text string"""
    try:
        # Try to use tiktoken for accurate count
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except:
        # Fallback to approximation
        return len(text) // 4

def summarize_agent_usage(usage_dict: Dict) -> Dict:
    """Normalize AG2 usage dicts to a standard format"""
    if not usage_dict:
        return {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "cached_prompt_tokens": 0,
            "completion_tokens": 0
        }
    
    # Extract token counts with fallbacks
    prompt_tokens = usage_dict.get("prompt_tokens", 0)
    cached_prompt_tokens = usage_dict.get("cached_prompt_tokens", 0)
    completion_tokens = usage_dict.get("completion_tokens", 0)
    
    # AG2 usage format
    if "total_tokens" in usage_dict:
        return {
            "total_tokens": usage_dict.get("total_tokens", 0),
            "prompt_tokens": prompt_tokens,
            "cached_prompt_tokens": cached_prompt_tokens,
            "completion_tokens": completion_tokens
        }
    
    # OpenAI API format
    if "total" in usage_dict:
        return {
            "total_tokens": usage_dict.get("total", 0),
            "prompt_tokens": usage_dict.get("prompt", 0),
            "cached_prompt_tokens": usage_dict.get("cached_prompt", 0),
            "completion_tokens": usage_dict.get("completion", 0)
        }
    
    # Calculate total if not provided
    total_tokens = prompt_tokens + cached_prompt_tokens + completion_tokens
    
    return {
        "total_tokens": total_tokens,
        "prompt_tokens": prompt_tokens,
        "cached_prompt_tokens": cached_prompt_tokens,
        "completion_tokens": completion_tokens
    }

def compute_text_cost(model: str, usage: Dict) -> float:
    """Calculate cost for text models based on token usage"""
    usage = summarize_agent_usage(usage)
    
    input_price = price_per_token(model, "input")
    cached_input_price = price_per_token(model, "cached_input")
    output_price = price_per_token(model, "output")
    
    # Calculate costs for different token types
    input_cost = usage.get("prompt_tokens", 0) * input_price
    cached_input_cost = usage.get("cached_prompt_tokens", 0) * cached_input_price
    output_cost = usage.get("completion_tokens", 0) * output_price
    
    return input_cost + cached_input_cost + output_cost

def compute_image_prompt_cost(model: str, prompt: str) -> Dict:
    """Calculate cost for image prompt input tokens"""
    token_count = estimate_tokens(prompt)
    token_price = price_per_token(model, "input")
    cost = token_count * token_price
    
    return {
        "tokens": token_count,
        "cost_usd": cost
    }

def compute_image_cost(model: str, api_usage: Optional[Dict] = None, prompt: Optional[str] = None) -> Dict:
    """Calculate cost for image generation based on API usage or prompt"""
    result = {
        "model": model,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "input_cost_usd": 0.0,
        "cached_input_cost_usd": 0.0,
        "output_cost_usd": 0.0,
        "total_cost_usd": 0.0,
        "input_tokens_details": {
            "text_tokens": 0,
            "image_tokens": 0
        }
    }
    
    # If API usage is provided, use that
    if api_usage:
        result["input_tokens"] = api_usage.get("input_tokens", 0)
        result["cached_input_tokens"] = api_usage.get("cached_input_tokens", 0)
        result["output_tokens"] = api_usage.get("output_tokens", 0)
        result["total_tokens"] = api_usage.get("total_tokens", 0)
        
        # Calculate costs
        input_price = price_per_token(model, "input")
        cached_input_price = price_per_token(model, "cached_input")
        output_price = price_per_token(model, "output")
        
        result["input_cost_usd"] = result["input_tokens"] * input_price
        result["cached_input_cost_usd"] = result["cached_input_tokens"] * cached_input_price
        result["output_cost_usd"] = result["output_tokens"] * output_price
        result["total_cost_usd"] = result["input_cost_usd"] + result["cached_input_cost_usd"] + result["output_cost_usd"]
        
        # Add token details if available
        if "input_tokens_details" in api_usage:
            result["input_tokens_details"] = {
                "text_tokens": api_usage["input_tokens_details"].get("text_tokens", 0),
                "image_tokens": api_usage["input_tokens_details"].get("image_tokens", 0)
            }
    
    # If prompt is provided, estimate tokens and cost
    elif prompt:
        token_estimate = estimate_tokens(prompt)
        result["input_tokens"] = token_estimate
        result["input_tokens_details"]["text_tokens"] = token_estimate
        result["total_tokens"] = token_estimate  # Just input tokens
        
        # Calculate cost
        input_price = price_per_token(model, "input")
        result["input_cost_usd"] = token_estimate * input_price
        result["total_cost_usd"] = result["input_cost_usd"]
    
    return result

def aggregate_tokens(items: List[Dict], key: str = "tokens") -> int:
    """Sum up token counts from multiple items"""
    return sum(item.get(key, 0) for item in items) 