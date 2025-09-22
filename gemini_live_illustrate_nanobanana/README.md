# Gemini Illustrate Banana

A backend service that provides real-time voice interaction with Gemini models and image annotation capabilities.

## Features

- Real-time voice interaction with Gemini models
- Image annotation and editing using Gemini
- WebSocket-based communication for low-latency responses

## Requirements

- Python 3.10+
- Virtual environment (recommended)
- Google API key (for Gemini)
- OpenRouter API key (for image editing)

## Installation

1. Clone the repository
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the root directory with the following variables:

```
# Required API keys
GOOGLE_API_KEY=your_google_api_key_here
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional configuration
CLEAR_PROXY=1
OPENROUTER_REFERER=https://your-app-domain.com
OPENROUTER_TITLE=Your Application Name
```

## Usage

Run the server:

```bash
python main_update_openrouter.py
```

The WebSocket server will start on `0.0.0.0:9090`.

## API Overview

The service provides a WebSocket interface for:
- Sending/receiving audio for voice interaction
- Sending images for analysis
- Receiving annotated/edited images
- Receiving transcriptions of both user and Gemini responses

## Models Used

- `gemini-2.0-flash-live-001` - For multimodal voice interaction
- `gemini-2.5-flash` - For generating edit prompts (text)
- `google/gemini-2.5-flash-image-preview` (via OpenRouter) - For image editing
