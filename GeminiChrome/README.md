# Gemini Live Assistant Chrome Extension

A Chrome extension that lets you talk to Google's Gemini AI with voice and share your screen for visual context.

## Features

- **Voice Chat**: Talk to AI with your voice and get audio responses
- **Screen Sharing**: Share your current tab or screen with the AI
- **Live Conversations**: Voice + screen sharing together for smart assistance

## Setup

### 1. Get a Gemini API Key
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Sign in with your Google account
3. Click "Create API Key"
4. Copy the API key

### 2. Replace the API Key in Code
1. Open `sidepanel.js` file
2. Find line 48 that says:
   ```javascript
   this.apiKey = 'Your_API_Key';
   ```
3. Replace the text between quotes with your own API key:
   ```javascript
   this.apiKey = 'YOUR_API_KEY_HERE';
   ```
4. Save the file

### 3. Install Extension
1. Open Chrome and go to `chrome://extensions`
2. Turn on "Developer mode" (top right toggle)
3. Click "Load unpacked"
4. Select the `my-gemini-assistant-ext` folder
5. The extension will appear with a blue icon

## How to Use

### Voice Chat
1. Click the extension icon to open the side panel
2. Click the blue "Talk" button
3. Allow microphone access when prompted
4. Start speaking - the AI will respond with voice
5. Click the red "Stop" button to end

### Screen Sharing
1. During voice chat, your screen is automatically captured every 3 seconds
2. The AI can see what's on your screen and help accordingly
3. Grant screen capture permission when prompted

## Troubleshooting

**"Please enter your API key"** - Make sure you replaced the API key in `sidepanel.js`

**Microphone not working** - Allow microphone permission in Chrome settings

**Screen capture fails** - Allow screen recording permission when Chrome asks

**Connection errors** - Check your internet and verify your API key is valid

## Privacy

- Your API key stays on your computer
- Voice and screen data go directly to Google's Gemini API
- Nothing is stored by this extension

## Need Help?

- Get API key: [Google AI Studio](https://makersuite.google.com/app/apikey)
- Chrome Extensions: `chrome://extensions`
- Check browser console (F12) for error messages 