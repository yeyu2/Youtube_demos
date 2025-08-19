# LiveKit Vision Agent

A voice AI assistant with vision capabilities built on LiveKit Agents. This project includes two main components:

- **`vision_agent.py`** - A vision-enabled AI assistant that can analyze images and video feeds
- **`agent.py`** - A basic LiveKit agent implementation

## Features

### Vision Agent (`vision_agent.py`)
- **Voice Interaction**: Speech-to-text and text-to-speech capabilities
- **Vision Analysis**: Can process images shared by users and analyze video camera feeds
- **Real-time Communication**: Built on LiveKit for real-time audio/video communication
- **Multilingual Support**: Supports multiple languages for voice detection
- **Noise Cancellation**: Built-in noise cancellation for better audio quality
- **Image Processing**: Handles both uploaded images and live video streams

### Basic Agent (`agent.py`)
- **Voice Interaction**: Speech-to-text and text-to-speech capabilities
- **Real-time Communication**: Built on LiveKit for real-time audio communication
- **Multilingual Support**: Supports multiple languages for voice detection
- **Noise Cancellation**: Built-in noise cancellation for better audio quality
- **Simple Assistant**: Basic voice AI assistant without vision capabilities

## Prerequisites

- Python 3.8+
- LiveKit server instance
- OpenAI API key (for GPT-4o vision model)
- Deepgram API key (for speech-to-text)
- Cartesia API key (for text-to-speech)

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy `env.example` to `.env` and fill in your API keys:
   ```bash
   cp env.example .env
   ```

4. Edit `.env` with your actual API keys and LiveKit configuration

## Usage

### Running the Vision Agent

```bash
python vision_agent.py
```

The vision agent will:
- Join a LiveKit room
- Listen for voice input
- Process images shared by users
- Analyze video camera feeds
- Provide AI-powered responses

### Running the Basic Agent

```bash
python agent.py
```

## Environment Variables

See `env.example` for all required environment variables. Key ones include:

- `OPENAI_API_KEY` - Your OpenAI API key for GPT-4o
- `DEEPGRAM_API_KEY` - Your Deepgram API key for speech recognition
- `CARTESIA_API_KEY` - Your Cartesia API key for text-to-speech
- `LIVEKIT_URL` - Your LiveKit server URL
- `LIVEKIT_API_KEY` - Your LiveKit API key
- `LIVEKIT_API_SECRET` - Your LiveKit API secret

## Architecture

Both agents use the same core technologies:
- **Deepgram** for speech-to-text with multilingual support
- **OpenAI** for AI reasoning (GPT-4o for vision, GPT-4o-mini for basic agent)
- **Cartesia** for natural-sounding text-to-speech
- **Silero** for voice activity detection
- **LiveKit** for real-time communication infrastructure

The vision agent additionally includes:
- **Image Processing**: Handles base64-encoded images and video frames
- **Video Stream Management**: Processes live camera feeds in real-time
- **Enhanced Context**: Integrates visual information with conversational context

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

[Add your license here] 