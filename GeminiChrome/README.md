# Gemini Live Assistant Chrome Extension

A powerful Chrome extension that provides real-time multimodal AI assistance through Google's Gemini Live API. Features include voice conversations, screen capture, and live visual context sharing.

## 🚀 Features

### Core Functionality
- **Real-time Voice Chat**: Talk naturally with Gemini AI using voice input and audio responses
- **Screen Capture**: Share your current tab or entire desktop with the AI for visual context
- **Live Screen Sharing**: Continuously send screen updates during voice conversations
- **Secure API Key Storage**: Your Gemini API key is stored locally and securely

### User Interface
- **Modern Side Panel**: Clean, intuitive interface with status indicators
- **Voice Controls**: Large, accessible record button with visual feedback
- **Screen Capture Controls**: Easy-to-use buttons for tab and desktop capture
- **Chat History**: View conversation history with clear message distinction
- **Real-time Status**: Connection status and activity indicators

### Technical Features
- **Audio Processing**: Custom audio worklet for high-quality 16kHz PCM audio
- **Image Processing**: Automatic frame capture and base64 encoding
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Chrome Extension APIs**: Full integration with Chrome's capture APIs

## 📋 Prerequisites

1. **Chrome Browser**: Version 114 or higher (for Side Panel API support)
2. **Gemini API Key**: Get your free API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
3. **Microphone Access**: Required for voice input
4. **Screen Recording Permission**: Required for screen capture features

## 🛠️ Installation

### Step 1: Download/Clone the Extension
- Download or clone this repository to your local machine
- Make sure all files are in the `my-gemini-assistant-ext` folder

### Step 2: Load the Extension in Chrome
1. Open Chrome browser
2. Navigate to `chrome://extensions`
3. Enable "Developer mode" (toggle in the top right)
4. Click "Load unpacked"
5. Select the `my-gemini-assistant-ext` folder
6. The extension should appear with a blue robot icon

### Step 3: Set Up Your API Key
1. Click the extension icon in Chrome's toolbar
2. The side panel will open showing the setup screen
3. Enter your Gemini API key in the input field
4. Click "Save" to store the key securely

## 🎯 How to Use

### Basic Voice Chat
1. **Start Conversation**: Click the blue "Talk" button
2. **Speak Naturally**: The AI will listen and respond with voice
3. **End Conversation**: Click the red "Stop" button

### Screen Capture & Visual Context
1. **Capture Current Tab**: Click "Current Tab" to share the active browser tab
2. **Capture Desktop**: Click "Desktop" to share your entire screen or specific windows
3. **Live Sharing**: During voice chat, screen content is automatically shared every 5 seconds
4. **Stop Capture**: Click "Stop Capture" to end screen sharing

### Advanced Usage
- **Simultaneous Use**: Use voice chat and screen capture together for multimodal conversations
- **Tab-Specific**: Each browser tab has its own assistant instance
- **Persistent Settings**: API key and preferences are saved between sessions

## 🔧 Technical Details

### File Structure
```
my-gemini-assistant-ext/
├── manifest.json       # Extension configuration and permissions
├── background.js       # Service worker for screen capture handling
├── sidepanel.html      # Modern UI with all interface elements
├── sidepanel.css       # Comprehensive styling with animations
├── sidepanel.js        # Complete Gemini Live integration
├── content.js          # Page injection for quick access
├── content.css         # Content script styling
└── icons/              # Extension icons (16px, 48px, 128px)
```

### Permissions Used
- `activeTab`: Access to current tab for capture
- `scripting`: Content script injection
- `sidePanel`: Modern side panel interface
- `tabCapture`: Tab screen capture
- `desktopCapture`: Desktop screen capture
- `storage`: Secure API key storage

### Audio Processing
- **Sample Rate**: 16kHz PCM (Gemini requirement)
- **Buffer Size**: 4096 samples for optimal latency
- **Resampling**: Automatic resampling from native audio rate
- **Playback**: 24kHz audio response playback

### Image Processing
- **Format**: JPEG with 0.8 quality for optimal size/quality balance
- **Frequency**: Screen capture every 5 seconds during conversations
- **Resolution**: Native screen resolution maintained
- **Encoding**: Base64 encoding for API transmission

## 🛠️ Troubleshooting

### Common Issues

**"Please enter your API key"**
- Get a free API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
- Make sure to save the key using the "Save" button

**"Audio system failed to initialize"**
- Ensure microphone permissions are granted
- Try refreshing the page or restarting Chrome
- Check that no other applications are blocking microphone access

**"Error capturing tab/desktop"**
- Grant screen recording permissions when prompted
- Try reloading the extension
- Make sure Chrome has screen recording permissions in system settings

**"Connection failed"**
- Check your internet connection
- Verify your API key is valid and has quota remaining
- Try refreshing the extension

### Performance Tips
- Close unused tabs to improve screen capture performance
- Use tab capture instead of desktop capture when possible
- Monitor API usage to avoid quota limits

## 🔒 Privacy & Security

- **API Key**: Stored locally in Chrome's secure storage, never transmitted to third parties
- **Audio Data**: Processed locally and sent directly to Google's Gemini API
- **Screen Capture**: Images are captured locally and sent directly to Gemini API
- **No Data Storage**: No conversation data is stored by the extension
- **Google Privacy**: Subject to Google's Gemini API privacy policy

## 📝 Development

### Adding Features
The extension is designed to be extensible. Key areas for enhancement:
- Additional capture modes (audio, specific applications)
- Custom prompts and conversation starters
- Integration with other AI services
- Advanced audio processing options

### Debugging
- **Content Script**: Open DevTools (F12) on any webpage
- **Background Script**: Visit `chrome://extensions` and click "Service worker"
- **Side Panel**: Right-click in side panel and select "Inspect"

## 🤝 Contributing

Contributions are welcome! Please consider:
- Bug fixes and improvements
- Additional capture modes
- UI/UX enhancements
- Performance optimizations

## 📄 License

This project is provided as-is for educational and development purposes.

## 🔗 Links

- [Google AI Studio](https://makersuite.google.com/app/apikey) - Get your API key
- [Gemini API Documentation](https://ai.google.dev/docs) - API reference
- [Chrome Extension APIs](https://developer.chrome.com/docs/extensions/) - Extension development guide 