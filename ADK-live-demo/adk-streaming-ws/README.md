# ADK Streaming with Transcript Display

This enhanced ADK streaming application now supports displaying transcript text from agent speech using Gemini Live natural conversation.

## Features

- **Real-time audio streaming** with bidirectional communication
- **Transcript display** showing what the agent is saying in text form
- **Natural conversation** using Gemini Live models
- **Visual distinction** between user messages, agent responses, and transcripts
- **Google Search integration** for enhanced responses

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API key:**
   Create a `.env` file in the project root with your Google AI API key:
   ```
   GOOGLE_API_KEY=your_google_ai_api_key_here
   ```
   
   Get your API key from: https://makersuite.google.com/app/apikey

3. **Run the application:**
   ```bash
   python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Open in browser:**
   Navigate to `http://localhost:8000`

## Usage

1. **Text Mode:** Type messages and receive text responses with transcripts
2. **Audio Mode:** Click "Start Audio" to enable voice conversation
   - Speak into your microphone
   - Listen to agent responses
   - See real-time transcripts of what the agent is saying

## Key Changes Made

### Agent Configuration (`app/google_search_agent/agent.py`)
- Updated to use `gemini-live-2.5-flash-preview` model for natural conversation
- Enhanced instructions for conversational responses

### Server Logic (`app/main.py`)
- Modified to handle both audio and text modalities simultaneously
- Added `output_audio_transcription` configuration in RunConfig
- Enhanced event processing to check for `server_content.output_transcription`
- Added debug logging to understand ADK event structure

### Client Interface (`app/static/`)
- Updated JavaScript to display transcripts with visual indicators
- Added CSS styling for better message distinction
- Enhanced UI with emoji indicators for different message types

## Message Types

- 👤 **You:** User messages
- 🤖 **Agent:** Regular agent text responses  
- 🎤 **Agent (Transcript):** Real-time transcript of agent speech

## Technical Details

The application uses:
- **Gemini Live API** for natural conversation capabilities
- **WebSocket** for real-time bidirectional communication
- **Audio Worklets** for low-latency audio processing
- **Event-driven architecture** for handling streaming responses

## Troubleshooting

If you encounter the "Missing key inputs argument" error:
1. Ensure your `.env` file exists with a valid `GOOGLE_API_KEY`
2. Verify the API key has proper permissions
3. Check that the key is not expired or rate-limited

## Debugging Transcript Issues

The current implementation includes debug logging to understand how ADK exposes the underlying Gemini Live API response. When you run the application:

1. Check the console output for `[DEBUG]` messages
2. Look for event structure information to understand what attributes are available
3. The transcript should come through `event.server_content.output_transcription.text` if ADK exposes it

If transcripts are not appearing, it may be that ADK doesn't currently expose the raw `output_transcription` from the Gemini Live API. In that case, you may need to:
1. Use the raw Gemini Live API directly (as shown in the official example)
2. Or wait for ADK to add support for exposing transcript data
