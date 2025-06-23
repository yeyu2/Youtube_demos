// Real Gemini Live API implementation
// Based on the reference code provided by the user

console.log("[Gemini Live] Loading real Gemini Live implementation...");

// Real GoogleGenAI class
window.GoogleGenAI = class GoogleGenAI {
  constructor(config) {
    console.log("[GoogleGenAI] Initialized with config:", config);
    this.apiKey = config.apiKey;
    this.apiVersion = config.apiVersion || 'v1alpha';
    this.live = {
      connect: this.createConnection.bind(this)
    };
  }

  async createConnection(config) {
    console.log("[GoogleGenAI] Creating real Gemini Live connection with config:", config);
    
    const session = new GeminiLiveSession(this.apiKey, this.apiVersion, config);
    await session.connect();
    
    return session;
  }
};

// Real Gemini Live Session class
class GeminiLiveSession {
  constructor(apiKey, apiVersion, config) {
    this.apiKey = apiKey;
    this.apiVersion = apiVersion;
    this.model = config.model || 'gemini-2.0-flash-live-001';
    this.config = config.config || {};
    this.callbacks = config.callbacks || {};
    this.ws = null;
    this.isConnected = false;
    this.setupComplete = false;
  }

  async connect() {
    console.log("[GeminiLiveSession] Connecting to Gemini Live API...");
    
    try {
      // Construct WebSocket URL for Gemini Live - using the correct endpoint from demo
      const wsUrl = `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=${this.apiKey}`;
      
      // Note: WebSocket constructor doesn't support custom headers in browsers
      // The demo uses additional_headers in Python websockets library
      // Browser WebSocket API doesn't support this, but the connection should work without it
      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = () => {
        console.log("[GeminiLiveSession] WebSocket connected successfully");
        console.log("[GeminiLiveSession] WebSocket URL:", wsUrl);
        this.isConnected = true;
        
        // Send initial setup message
        this.sendSetupMessage();
        
        if (this.callbacks.onopen) {
          this.callbacks.onopen();
        }
      };
      
      this.ws.onmessage = async (event) => {
        await this.handleMessage(event);
      };
      
      this.ws.onerror = (error) => {
        console.error("[GeminiLiveSession] WebSocket error:", error);
        console.error("[GeminiLiveSession] WebSocket URL was:", wsUrl);
        console.error("[GeminiLiveSession] WebSocket readyState:", this.ws.readyState);
        if (this.callbacks.onerror) {
          this.callbacks.onerror(error);
        }
      };
      
      this.ws.onclose = (event) => {
        console.log("[GeminiLiveSession] WebSocket closed:", event);
        this.isConnected = false;
        this.setupComplete = false;
        if (this.callbacks.onclose) {
          this.callbacks.onclose(event);
        }
      };
      
    } catch (error) {
      console.error("[GeminiLiveSession] Connection error:", error);
      throw error;
    }
  }

  sendSetupMessage() {
    console.log("[GeminiLiveSession] Sending setup message");
    
    // Enhanced setup with transcription enabled
    const setupMessage = {
      setup: {
        model: `models/${this.model}`,
        generationConfig: {
          responseModalities: ["AUDIO"],
          speechConfig: {
            voiceConfig: {
              prebuiltVoiceConfig: {
                voiceName: "Puck"
              }
            }
          }
        },
        systemInstruction: {
          parts: [{
            text: "You are a helpful AI assistant with access to live audio and screen capture. Respond naturally to voice input and describe what you see in screen captures when relevant."
          }]
        },
        // Enable transcription for both input and output
        inputAudioTranscription: {},
        outputAudioTranscription: {}
      }
    };
    
    this.sendMessage(setupMessage);
    
    // Add a timeout to mark setup as complete if no response received
    setTimeout(() => {
      if (!this.setupComplete && this.isConnected) {
        console.log("[GeminiLiveSession] Setup timeout - marking as complete");
        this.setupComplete = true;
        
        if (this.callbacks.onmessage) {
          this.callbacks.onmessage({ setupComplete: true });
        }
      }
    }, 2000); // 2 second timeout
  }

  async handleMessage(event) {
    try {
      let data;
      
      // Handle both text and binary WebSocket messages
      if (event.data instanceof Blob) {
        console.log("[GeminiLiveSession] Received Blob message, converting to text");
        const text = await event.data.text();
        data = JSON.parse(text);
      } else if (typeof event.data === 'string') {
        data = JSON.parse(event.data);
      } else {
        console.warn("[GeminiLiveSession] Received unknown message type:", typeof event.data);
        return;
      }
      
      // Log non-audio messages only
      if (data.serverContent?.modelTurn?.parts?.some(part => part.inlineData?.data)) {
        console.log("[GeminiLiveSession] Received audio message (content hidden)");
      } else {
        console.log("[GeminiLiveSession] Received message:", JSON.stringify(data, null, 2));
      }
      
      // Handle setup complete - look for setup response or any initial response
      if (!this.setupComplete) {
        console.log("[GeminiLiveSession] Setup completed - first response received");
        this.setupComplete = true;
        
        if (this.callbacks.onmessage) {
          this.callbacks.onmessage({ setupComplete: true });
        }
        
        // Continue processing this message if it has content
      }
      
      // Handle server content (responses from Gemini) - match demo format
      if (data.serverContent) {
        console.log("[GeminiLiveSession] Received server content");
        
        // Handle input transcription (user's speech)
        if (data.serverContent.inputTranscription) {
          console.log("[GeminiLiveSession] Input transcription:", data.serverContent.inputTranscription.text);
        }
        
        // Handle output transcription (AI's speech)
        if (data.serverContent.outputTranscription) {
          console.log("[GeminiLiveSession] Output transcription:", data.serverContent.outputTranscription.text);
        }
        
        // Process audio and text responses - match demo structure
        if (data.serverContent.modelTurn && data.serverContent.modelTurn.parts) {
          data.serverContent.modelTurn.parts.forEach(part => {
            if (part.inlineData && part.inlineData.data) {
              console.log("[GeminiLiveSession] Received audio response");
            }
            if (part.text) {
              console.log("[GeminiLiveSession] Received text response:", part.text);
            }
          });
        }
        
        if (this.callbacks.onmessage) {
          this.callbacks.onmessage(data);
        }
      }
      
    } catch (error) {
      console.error("[GeminiLiveSession] Error parsing message:", error);
      console.error("[GeminiLiveSession] Raw message data:", event.data);
    }
  }

  sendRealtimeInput(input) {
    if (!this.isConnected || !this.setupComplete) {
      console.warn("[GeminiLiveSession] Cannot send input - not connected or setup not complete");
      return;
    }
    
    console.log("[GeminiLiveSession] Sending realtime input:", input.media ? `${input.media.mimeType} data` : input);
    
    // Format message according to demo code - use realtime_input and media_chunks
    const message = {
      realtime_input: {
        media_chunks: [{
          mime_type: input.media.mimeType,
          data: input.media.data
        }]
      }
    };
    
    this.sendMessage(message);
  }

  sendMessage(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn("[GeminiLiveSession] Cannot send message - WebSocket not open");
    }
  }

  close() {
    console.log("[GeminiLiveSession] Closing connection");
    this.setupComplete = false;
    
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Modality enum
window.Modality = {
  AUDIO: 'AUDIO',
  TEXT: 'TEXT'
};

console.log("[Gemini Live] Real Gemini Live library loaded successfully"); 