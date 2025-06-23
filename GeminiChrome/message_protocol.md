# Gemini Live Message Protocol

## 1. Connection

**URL:** `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=YOUR_API_KEY`

## 2. The Initial "Setup" Message

```json
{
  "setup": {
    "model": "models/gemini-2.0-flash-live-001",
    "generationConfig": {
      "responseModalities": ["AUDIO"],
      "speechConfig": {
        "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "Puck" } }
      }
    },
    "systemInstruction": {
      "parts": [{
        "text": "You are a helpful AI assistant..."
      }]
    },
    "inputAudioTranscription": {},
    "outputAudioTranscription": {}
  }
}
```


## 3. Sending Input (Audio and Images)

### Sending Audio

The audio from our worklet is 16-bit PCM data. We Base64-encode it and send it with the correct MIME type.

```json
{
  "realtime_input": {
    "media_chunks": [{
      "mime_type": "audio/pcm;rate=16000",
      "data": "BASE64_ENCODED_AUDIO_CHUNK"
    }]
  }
}
```

### Sending an Image

```json
{
  "realtime_input": {
    "media_chunks": [{
      "mime_type": "image/png",
      "data": "BASE64_ENCODED_IMAGE_DATA"
    }]
  }
}
```

## 4. Receiving Output

```json
{
  "serverContent": {
    // User's speech-to-text
    "inputTranscription": {
      "text": "Hello, can you see my screen?"
    },
    // AI's speech-to-text
    "outputTranscription": {
      "text": "Yes, I can. I see a webpage about..."
    },
    // AI's response (audio and/or text)
    "modelTurn": {
      "parts": [
        {
          "text": "Yes, I can. I see a webpage about..."
        },
        {
          "inlineData": {
            "mime_type": "audio/mp3",
            "data": "BASE64_ENCODED_AUDIO_RESPONSE"
          }
        }
      ]
    },
    // Shows the end of a conversational turn
    "turnComplete": true
  }
}
```
