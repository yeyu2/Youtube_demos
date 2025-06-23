// sidepanel.js
console.log("Gemini Live Assistant - Side panel script loaded.");

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log("Side panel received message:", request.action, request);
  
  if (request.action === "closeSidePanel") {
    // Handle close request from background script
    console.log("Side panel received close request");
    // Close the side panel by closing the window/tab (for side panels, this closes the panel)
    window.close();
    return true;
  }
  
  return true;
});

// Import the Gemini AI library via CDN in HTML or use bundled version
// For now, we'll use dynamic import or script tag in HTML

const TARGET_SAMPLE_RATE = 16000; // Gemini expects 16kHz PCM
const WORKLET_BUFFER_SIZE = 4096; // How many 16kHz samples to buffer in worklet before sending
const IMAGE_SEND_INTERVAL_MS = 5000; // Send image every 5 seconds

// Helper function to encode ArrayBuffer to Base64
function arrayBufferToBase64(buffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

// Helper function to decode Base64 to ArrayBuffer
function base64ToArrayBuffer(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

class GeminiLiveAssistant {
  constructor() {
    // Hardcoded API key for testing - REPLACE WITH YOUR KEY
    this.apiKey = 'Your_API_Key';
    this.session = null;
    this.isRecording = false;
    this.isSetupComplete = false;
    this.isCapturingScreen = false;
    this.captureStream = null;
    this.captureCanvas = null;
    this.captureContext = null;
    this.imageSendIntervalId = null;
    this.currentImageBase64 = null;
    this.currentImageMimeType = null;
    
    // Auto screenshot state
    this.isAutoCapturing = false;
    this.autoScreenshotInterval = null;
    this.autoScreenshotIntervalMs = 3000; // 3 seconds
    
    // Live chat state
    this.isLiveChatActive = false;
    
    // Transcript streaming state
    this.currentInputTranscript = null;
    this.currentOutputTranscript = null;
    this.currentInputAccumulated = '';
    this.currentOutputAccumulated = '';

    // Audio system
    this.audioContext = null;
    this.micStream = null;
    this.micSourceNode = null;
    this.audioWorkletNode = null;
    this.audioQueue = [];
    this.isPlayingAudio = false;

    // UI Elements
    this.initializeUIElements();
    this.setupEventListeners();
    
    // Skip API key loading and go straight to main interface
    this.showMainInterface();
    this.initializeGeminiAI();
  }

  initializeUIElements() {
    // Header elements
    this.statusText = document.getElementById('statusText');
    this.statusSubtitle = document.getElementById('statusSubtitle');
    this.breathingIndicator = document.getElementById('breathingIndicator');
    this.chatActionBtn = document.getElementById('chatActionBtn');
    this.chatActionIcon = document.getElementById('chatActionIcon');
    
    // API Key elements
    this.apiKeySection = document.getElementById('apiKeySection');
    this.mainInterface = document.getElementById('mainInterface');
    this.apiKeyInput = document.getElementById('apiKeyInput');
    this.saveApiKeyBtn = document.getElementById('saveApiKeyBtn');
    
    // Live chat elements (hidden)
    this.startLiveChatBtn = document.getElementById('startLiveChatBtn');
    this.stopLiveChatBtn = document.getElementById('stopLiveChatBtn');
    this.imagePreviewContainer = document.getElementById('imagePreviewContainer');
    this.imagePreview = document.getElementById('imagePreview');
    this.removeImageBtn = document.getElementById('removeImageBtn');
    
    // Chat elements
    this.chatMessages = document.getElementById('chatMessages');
    
    // Transcript elements
    this.transcriptMessages = document.getElementById('transcriptMessages');
    
    // Audio visualization elements
    this.audioVisualizer = document.getElementById('audioVisualizer');
    this.audioLevelFill = document.getElementById('audioLevelFill');
    this.audioLevelText = document.getElementById('audioLevelText');
    this.audioWaveform = document.getElementById('audioWaveform');
    this.waveformCtx = this.audioWaveform ? this.audioWaveform.getContext('2d') : null;
    
    // Audio visualization state
    this.audioLevelHistory = new Array(60).fill(0); // Store last 60 samples for waveform
    this.currentAudioLevel = 0;
    this.animationFrameId = null;
  }

  setupEventListeners() {
    this.saveApiKeyBtn.addEventListener('click', () => this.saveApiKey());
    this.apiKeyInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') {
        this.saveApiKey();
      }
    });
    
    // Connect new chat action button to original functionality
    this.chatActionBtn.addEventListener('click', () => {
      if (this.isLiveChatActive) {
        this.stopLiveChat();
      } else {
        this.startLiveChat();
      }
    });
    
    this.startLiveChatBtn.addEventListener('click', () => this.startLiveChat());
    this.stopLiveChatBtn.addEventListener('click', () => this.stopLiveChat());
    this.removeImageBtn.addEventListener('click', () => this.removeImage());
  }

  async loadApiKey() {
    try {
      // Try direct chrome.storage access first
      if (chrome?.storage?.local) {
        const result = await chrome.storage.local.get(['geminiApiKey']);
        if (result.geminiApiKey) {
          this.apiKey = result.geminiApiKey;
          this.showMainInterface();
          this.updateStatus('Ready to chat');
        } else {
          this.updateStatus('Please enter your API key');
        }
      } else {
        // Fallback: use background script messaging
        const response = await chrome.runtime.sendMessage({
          action: 'getStoredData',
          key: 'geminiApiKey'
        });
        
        if (response && response.success && response.value) {
          this.apiKey = response.value;
          this.showMainInterface();
          this.updateStatus('Ready to chat');
        } else {
          this.updateStatus('Please enter your API key');
        }
      }
    } catch (error) {
      console.error('Error loading API key:', error);
      this.updateStatus('Please enter your API key');
    }
  }

  async saveApiKey() {
    const apiKey = this.apiKeyInput.value.trim();
    if (!apiKey) {
      this.updateStatus('Please enter a valid API key', true);
      return;
    }

    console.log('[saveApiKey] Starting to save API key...');
    this.updateStatus('Saving API key...');
    
    try {
      let saved = false;
      
      // Try direct chrome.storage access first
      if (chrome?.storage?.local) {
        console.log('[saveApiKey] Using direct chrome.storage.local');
        await chrome.storage.local.set({ geminiApiKey: apiKey });
        saved = true;
      } else {
        // Fallback: use background script messaging
        console.log('[saveApiKey] Using background script messaging');
        const response = await chrome.runtime.sendMessage({
          action: 'setStoredData',
          key: 'geminiApiKey',
          value: apiKey
        });
        
        console.log('[saveApiKey] Background response:', response);
        
        if (!response || !response.success) {
          throw new Error(response?.error || 'Failed to save via background script');
        }
        saved = true;
      }
      
      if (saved) {
        console.log('[saveApiKey] API key saved successfully');
        this.apiKey = apiKey;
        this.apiKeyInput.value = '';
        this.showMainInterface();
        this.updateStatus('API key saved! Initializing...');
        
        // Initialize Gemini AI library
        await this.initializeGeminiAI();
      }
    } catch (error) {
      console.error('[saveApiKey] Error saving API key:', error);
      this.updateStatus('Error saving API key. Please try again.', true);
    }
  }

  showMainInterface() {
    this.apiKeySection.style.display = 'none';
    this.mainInterface.style.display = 'block';
  }

  async initializeGeminiAI() {
    try {
      // Load Gemini AI library dynamically
      if (!window.GoogleGenAI) {
        await this.loadGeminiLibrary();
      }
      
      this.genAI = new window.GoogleGenAI({ 
        apiKey: this.apiKey, 
        apiVersion: 'v1alpha' 
      });
      
      this.updateStatus('Ready to chat');
      if (this.startLiveChatBtn) {
        this.startLiveChatBtn.disabled = false;
      }
      
      // Check microphone permission status
      await this.checkMicrophonePermission();
      
    } catch (error) {
      console.error('Error initializing Gemini AI:', error);
      this.updateStatus('Error initializing Gemini AI', true);
    }
  }

  async checkMicrophonePermission() {
    try {
      const permissionStatus = await navigator.permissions.query({ name: 'microphone' });
      console.log("[checkMicrophonePermission] Current status:", permissionStatus.state);
      
      // Microphone permission status logged but not displayed to user
      
      // Listen for permission changes
      permissionStatus.onchange = () => {
        console.log("[checkMicrophonePermission] Permission changed to:", permissionStatus.state);
      };
      
    } catch (error) {
      console.log("[checkMicrophonePermission] Permission API not available:", error);
      // Permission will be requested when needed
    }
  }

  async loadGeminiLibrary() {
    console.log("[loadGeminiLibrary] Checking for Gemini Live library...");
    
    // Check if library is already loaded
    if (window.GoogleGenAI) {
      console.log("[loadGeminiLibrary] Gemini Live library already available");
      return Promise.resolve();
    }
    
    // If no library is available, there's an issue with our implementation
    console.error("[loadGeminiLibrary] No Gemini Live library found - should be loaded from HTML");
    throw new Error('Gemini Live library not available');
  }

  updateStatus(message, isError = false) {
    if (this.statusText) {
      this.statusText.textContent = message;
    }
    
    // Update breathing indicator and UI state
    this.updateBreathingIndicator(message, isError);
    
    // Update chat action button
    this.updateChatActionButton();
    
    // Only add important status messages to transcript during live chat
    if (this.isLiveChatActive && message && this.shouldShowInTranscript(message)) {
      this.addTranscriptSystemMessage(message);
    }
    
    console.log(`[Status] ${message}`);
  }

  updateBreathingIndicator(message, isError) {
    if (!this.breathingIndicator) return;
    
    // Reset classes
    this.breathingIndicator.className = 'breathing-indicator';
    
    if (isError) {
      this.breathingIndicator.classList.add('error');
    } else if (this.isLiveChatActive) {
      if (this.isRecording) {
        this.breathingIndicator.classList.add('recording');
      } else if (message.includes('Playing') || message.includes('thinking')) {
        this.breathingIndicator.classList.add('thinking');
      } else {
        this.breathingIndicator.classList.add('recording');
      }
    }
  }

  updateChatActionButton() {
    if (!this.chatActionBtn || !this.chatActionIcon) return;
    
    // Reset classes
    this.chatActionBtn.className = 'chat-action-btn';
    
    if (this.isLiveChatActive) {
      this.chatActionIcon.className = 'fas fa-stop';
      this.chatActionBtn.classList.add('recording');
      if (this.statusSubtitle) {
        this.statusSubtitle.textContent = 'Live conversation active';
      }
    } else {
      this.chatActionIcon.className = 'fas fa-play';
      if (this.statusSubtitle) {
        this.statusSubtitle.textContent = 'Click to start live conversation with your browsing assistant';
      }
    }
  }

  shouldShowInTranscript(message) {
    // Filter out noisy status messages
    const filterOut = [
      'Playing response...',
      'Listening...',
      'Connected! Finalizing setup...',
      'Connecting to Gemini...',
      'Ready to chat',
      'Requesting microphone...',
      'Auto-screenshot started',
      'Auto-screenshot stopped',
      'Live chat stopped'
    ];
    
    return !filterOut.some(filter => message.includes(filter));
  }

  addChatMessage(content, isUser = false) {
    const messageDiv = document.createElement('div');
    messageDiv.className = isUser ? 'user-message' : 'assistant-message';
    messageDiv.textContent = content;
    
    this.chatMessages.appendChild(messageDiv);
    this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
  }

  addTranscriptMessage(text, isUser = false, isStreaming = false) {
    if (!this.transcriptMessages) return;
    
    // Remove info message if it exists
    const infoMsg = this.transcriptMessages.querySelector('.transcript-info');
    if (infoMsg) {
      infoMsg.remove();
    }
    
    // For streaming, accumulate text in existing message or create new one
    if (isStreaming) {
      const currentTranscriptRef = isUser ? 'currentInputTranscript' : 'currentOutputTranscript';
      const currentAccumulatedRef = isUser ? 'currentInputAccumulated' : 'currentOutputAccumulated';
      
      if (!this[currentTranscriptRef]) {
        // Create new transcript box for this conversation turn
        const messageDiv = document.createElement('div');
        messageDiv.className = `transcript-message ${isUser ? 'user' : 'ai'}`;
        
        const speakerDiv = document.createElement('div');
        speakerDiv.className = 'speaker';
        speakerDiv.textContent = isUser ? 'You' : 'AI';
        
        const textDiv = document.createElement('div');
        textDiv.className = 'text';
        textDiv.textContent = text;
        
        messageDiv.appendChild(speakerDiv);
        messageDiv.appendChild(textDiv);
        
        this.transcriptMessages.appendChild(messageDiv);
        this[currentTranscriptRef] = textDiv; // Store reference to text div
        this[currentAccumulatedRef] = text; // Store accumulated text
              } else {
          // Accumulate new words (API may be sending incremental updates)
          if (text && text.trim()) {
            // Check if this is new text we haven't seen before
            const currentText = this[currentAccumulatedRef] || '';
            if (!currentText.includes(text)) {
              // Append new text as-is (no artificial spacing)
              this[currentAccumulatedRef] = currentText + text;
            } else {
              // This text is already included, might be a repeat or full text
              // Keep the longer version
              if (text.length > currentText.length) {
                this[currentAccumulatedRef] = text;
              }
            }
            this[currentTranscriptRef].textContent = this[currentAccumulatedRef];
          }
        }
    } else {
      // Non-streaming message (create new box each time)
      const messageDiv = document.createElement('div');
      messageDiv.className = `transcript-message ${isUser ? 'user' : 'ai'}`;
      
      const speakerDiv = document.createElement('div');
      speakerDiv.className = 'speaker';
      speakerDiv.textContent = isUser ? 'You' : 'AI';
      
      const textDiv = document.createElement('div');
      textDiv.className = 'text';
      textDiv.textContent = text;
      
      messageDiv.appendChild(speakerDiv);
      messageDiv.appendChild(textDiv);
      
      this.transcriptMessages.appendChild(messageDiv);
    }
    
    // Auto-scroll to bottom with smooth behavior
    this.scrollTranscriptToBottom();
    console.log(`[Transcript] ${isUser ? 'User' : 'AI'}: ${text}`);
  }

  addTranscriptSystemMessage(text) {
    if (!this.transcriptMessages) return;
    
    // Remove info message if it exists
    const infoMsg = this.transcriptMessages.querySelector('.transcript-info');
    if (infoMsg) {
      infoMsg.remove();
    }
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'transcript-system';
    messageDiv.innerHTML = `<i class="fas fa-info-circle"></i> ${text}`;
    
    this.transcriptMessages.appendChild(messageDiv);
    this.scrollTranscriptToBottom();
  }

  finishTranscriptTurn(isUser = false) {
    // Mark the current transcript turn as complete
    const currentTranscriptRef = isUser ? 'currentInputTranscript' : 'currentOutputTranscript';
    const currentAccumulatedRef = isUser ? 'currentInputAccumulated' : 'currentOutputAccumulated';
    this[currentTranscriptRef] = null;
    this[currentAccumulatedRef] = '';
  }

  clearTranscript() {
    if (!this.transcriptMessages) return;
    
    this.transcriptMessages.innerHTML = `
      <div class="transcript-info">
        <i class="fas fa-info-circle"></i>
        <span>Real-time transcription of your voice and AI responses will appear here during live chat.</span>
      </div>
    `;
  }

  scrollTranscriptToBottom() {
    if (!this.transcriptMessages) return;
    
    // Use requestAnimationFrame to ensure the DOM has been updated
    requestAnimationFrame(() => {
      // Check if user has scrolled up manually (allowing them to read older messages)
      const isNearBottom = this.transcriptMessages.scrollTop + this.transcriptMessages.clientHeight >= this.transcriptMessages.scrollHeight - 50;
      
      // Only auto-scroll if user is near the bottom or if this is the first message
      if (isNearBottom || this.transcriptMessages.children.length <= 2) {
        this.transcriptMessages.scrollTop = this.transcriptMessages.scrollHeight;
      }
    });
  }

  // Live Chat Methods
  async startLiveChat() {
    if (this.isLiveChatActive) {
      return; // Already active
    }
    
    console.log("[startLiveChat] Starting live screen share chat...");
    this.isLiveChatActive = true;
    
    // Update UI
    if (this.startLiveChatBtn) {
      this.startLiveChatBtn.style.display = 'none';
    }
    if (this.stopLiveChatBtn) {
      this.stopLiveChatBtn.style.display = 'inline-flex';
    }
    this.updateStatus('Starting live chat...');
    this.clearTranscript(); // Clear previous transcript
    
    try {
      // Step 1: Start screenshot capture
      await this.startScreenshotCapture();
      
      // Step 2: Start voice recording
      await this.startVoiceRecording();
      
      // Step 3: Show audio visualizer
      this.showAudioVisualizer();
      
      this.updateStatus('Live chat active - Voice + Screen sharing');
      
    } catch (error) {
      console.error('[startLiveChat] Error occurred:', error);
      console.error('[startLiveChat] Error stack:', error.stack);
      this.updateStatus(`Error starting live chat: ${error.message}`, true);
      
      // Error messages will be shown via status updates, no need for chat messages
      
      console.log('[startLiveChat] Calling stopLiveChat due to error');
      this.stopLiveChat(); // Clean up on error
    }
  }

  async stopLiveChat() {
    if (!this.isLiveChatActive) {
      return; // Not active
    }
    
    console.log("[stopLiveChat] Stopping live screen share chat...");
    this.isLiveChatActive = false;
    
    // Update UI
    if (this.startLiveChatBtn) {
      this.startLiveChatBtn.style.display = 'inline-flex';
    }
    if (this.stopLiveChatBtn) {
      this.stopLiveChatBtn.style.display = 'none';
    }
    
    // Stop screenshot capture
    this.stopAutoScreenshot();
    
    // Stop voice recording
    this.stopRecording();
    
    // Hide audio visualizer
    this.hideAudioVisualizer();
    
    // Update status
    this.updateStatus('Live chat stopped');
    this.updateLiveStatus();
  }

  async startScreenshotCapture() {
    console.log("[startScreenshotCapture] Starting screenshot capture...");
    
    // Request screenshot through background script
    const response = await chrome.runtime.sendMessage({
      action: 'captureScreenshot'
    });
    
    if (response && response.success && response.dataUrl) {
      // Display the screenshot
      this.displayScreenshot(response.dataUrl, response.tabUrl);
      
      // Start auto-capture
      this.startAutoScreenshot();
      
      // Update status
      this.updateLiveStatus();
      
    } else {
      throw new Error(response.error || 'Failed to capture screenshot');
    }
  }

  async startVoiceRecording() {
    console.log("[startVoiceRecording] Starting voice recording...");
    
    try {
      if (!this.genAI) {
        throw new Error('Gemini AI not initialized');
      }
      
      // Request microphone permission first
      console.log("[startVoiceRecording] Requesting microphone permission...");
      const hasPermission = await this.requestMicrophonePermission();
      console.log("[startVoiceRecording] Microphone permission result:", hasPermission);
      
      if (!hasPermission) {
        throw new Error("Microphone permission denied");
      }
      
      console.log("[startVoiceRecording] Initializing audio system...");
      const audioSystemReady = await this.initializeAudioSystem();
      console.log("[startVoiceRecording] Audio system ready:", audioSystemReady);
      
      if (!audioSystemReady) {
        throw new Error("Audio system failed to initialize");
      }
      
      console.log("[startVoiceRecording] Starting recording...");
      this.isRecording = true;
      await this.startRecording();
      this.updateLiveStatus();
      console.log("[startVoiceRecording] Voice recording started successfully");
      
    } catch (error) {
      console.error("[startVoiceRecording] Error in voice recording:", error);
      console.error("[startVoiceRecording] Error stack:", error.stack);
      throw error; // Re-throw to be caught by startLiveChat
    }
  }

  async requestMicrophonePermission() {
    try {
      // First check if we already have permission
      try {
        const permissionStatus = await navigator.permissions.query({ name: 'microphone' });
        if (permissionStatus.state === 'granted') {
          console.log("[requestMicrophonePermission] Microphone permission already granted");
          return true;
        }
      } catch (e) {
        console.log("[requestMicrophonePermission] Permission API not available, continuing with other methods");
      }
      
      console.log("[requestMicrophonePermission] Requesting microphone access via iframe...");
      
      // Add timeout to prevent hanging
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Iframe permission request timeout')), 5000); // 5 second timeout
      });
      
      // Request microphone permission through background script iframe injection
      const responsePromise = chrome.runtime.sendMessage({
        action: 'requestMicrophonePermission'
      });
      
      const response = await Promise.race([responsePromise, timeoutPromise]);
      
      console.log("[requestMicrophonePermission] Response:", response);
      
      if (response && response.success) {
        console.log("[requestMicrophonePermission] Microphone permission granted via iframe");
        return true;
      } else {
        // If iframe method fails, try direct permission request as fallback
        console.log("[requestMicrophonePermission] Iframe method failed, trying direct permission request...");
        return await this.requestMicrophonePermissionDirect();
      }
      
    } catch (error) {
      console.error("[requestMicrophonePermission] Error:", error);
      // Try direct permission request as fallback
      console.log("[requestMicrophonePermission] Trying direct permission request as fallback...");
      return await this.requestMicrophonePermissionDirect();
    }
  }

  async requestMicrophonePermissionDirect() {
    try {
      console.log("[requestMicrophonePermissionDirect] Requesting microphone access directly...");
      
      // Direct getUserMedia call as fallback
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          sampleRate: 16000
        } 
      });
      
      // Stop the test stream immediately - we just needed to get permission
      stream.getTracks().forEach(track => track.stop());
      
      console.log("[requestMicrophonePermissionDirect] Microphone permission granted directly");
      return true;
      
    } catch (error) {
      console.error("[requestMicrophonePermissionDirect] Permission denied or error:", error);
      
      if (error.name === 'NotAllowedError') {
        throw new Error("Microphone access denied. Please allow microphone access and try again.");
      } else if (error.name === 'NotFoundError') {
        throw new Error("No microphone found. Please connect a microphone and try again.");
      } else {
        throw new Error(`Microphone error: ${error.message}`);
      }
    }
  }

  updateLiveStatus() {
    // Status updates are now handled through updateStatus() and transcript system messages
    // This method is kept for compatibility but no longer displays status indicators
  }

  // Legacy screen capture methods (kept for compatibility but not used in live chat)

  async startCaptureProcessing(streamId, type) {
    try {
      // Get the media stream from the streamId
      this.captureStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          mandatory: {
            chromeMediaSource: type === 'desktop' ? 'desktop' : 'tab',
            chromeMediaSourceId: streamId
          }
        }
      });

      // Create canvas for frame capture
      this.captureCanvas = document.createElement('canvas');
      this.captureContext = this.captureCanvas.getContext('2d');
      
      // Create video element to process stream
      const video = document.createElement('video');
      video.srcObject = this.captureStream;
      video.play();
      
      video.onloadedmetadata = () => {
        this.captureCanvas.width = video.videoWidth;
        this.captureCanvas.height = video.videoHeight;
        
        // Capture first frame immediately
        this.captureFrame(video);
        
        this.isCapturingScreen = true;
        this.updateCaptureUI();
        this.updateStatus(`${type} capture started`);
        
        // Start periodic image sending if recording is active
        if (this.isRecording) {
          this.startPeriodicImageSending();
        }
      };
      
      // Store video element for frame capture
      this.captureVideo = video;
      
    } catch (error) {
      console.error('Error processing capture stream:', error);
      this.updateStatus('Error processing capture', true);
    }
  }

  captureFrame(video) {
    if (!this.captureContext || !video) return;
    
    try {
      // Draw video frame to canvas
      this.captureContext.drawImage(video, 0, 0);
      
      // Convert to base64 image
      const dataURL = this.captureCanvas.toDataURL('image/jpeg', 0.8);
      this.currentImageBase64 = dataURL.substring(dataURL.indexOf(',') + 1);
      this.currentImageMimeType = 'image/jpeg';
      
      // Update preview
      this.imagePreview.src = dataURL;
      this.imagePreviewContainer.style.display = 'block';
      
    } catch (error) {
      console.error('Error capturing frame:', error);
    }
  }

  updateCaptureUI() {
    if (this.isCapturingScreen) {
      this.captureScreenshotBtn.style.display = 'none';
      this.captureTabBtn.style.display = 'none';
      this.captureThisTabBtn.style.display = 'none';
      this.captureScreenBtn.style.display = 'none';
      this.stopCaptureBtn.style.display = 'inline-flex';
    } else {
      this.captureScreenshotBtn.style.display = 'inline-flex';
      this.captureTabBtn.style.display = 'inline-flex';
      this.captureThisTabBtn.style.display = 'inline-flex';
      this.captureScreenBtn.style.display = 'inline-flex';
      this.stopCaptureBtn.style.display = 'none';
    }
  }

  stopCapture() {
    if (this.captureStream) {
      this.captureStream.getTracks().forEach(track => track.stop());
      this.captureStream = null;
    }
    
    if (this.captureVideo) {
      this.captureVideo.srcObject = null;
      this.captureVideo = null;
    }
    
    this.isCapturingScreen = false;
    this.stopPeriodicImageSending();
    this.stopAutoScreenshot(); // Also stop auto-screenshot
    this.updateCaptureUI();
    this.updateStatus('Screen capture stopped');
  }

  displayScreenshot(dataUrl, tabUrl) {
    this.imagePreview.src = dataUrl;
    this.imagePreviewContainer.style.display = 'block';
    
    // Convert dataUrl to base64 for Gemini
    this.currentImageBase64 = dataUrl.substring(dataUrl.indexOf(',') + 1);
    this.currentImageMimeType = 'image/png';
    
    // Update the image header to show it's a screenshot
    const imageHeader = this.imagePreviewContainer.querySelector('.image-header span');
    if (imageHeader) {
      try {
        const url = new URL(tabUrl);
        imageHeader.textContent = `Screenshot: ${url.hostname}`;
      } catch (e) {
        imageHeader.textContent = 'Screenshot';
      }
    }
  }

  startAutoScreenshot() {
    if (this.isAutoCapturing) {
      return; // Already running
    }
    
    console.log("[startAutoScreenshot] Starting auto-screenshot every", this.autoScreenshotIntervalMs, "ms");
    this.isAutoCapturing = true;
    
    // Update UI to show auto-capture is active
    this.updateStatus(`Auto-screenshot started (every ${this.autoScreenshotIntervalMs/1000}s)`);
    
    // Update live status instead of button (button is now handled by live chat)
    this.updateLiveStatus();
    
    // Start the interval
    this.autoScreenshotInterval = setInterval(() => {
      this.captureScreenshotSilent();
    }, this.autoScreenshotIntervalMs);
  }

  stopAutoScreenshot() {
    if (!this.isAutoCapturing) {
      return; // Not running
    }
    
    console.log("[stopAutoScreenshot] Stopping auto-screenshot");
    this.isAutoCapturing = false;
    
    // Clear the interval
    if (this.autoScreenshotInterval) {
      clearInterval(this.autoScreenshotInterval);
      this.autoScreenshotInterval = null;
    }
    
    // Update UI
    this.updateStatus('Auto-screenshot stopped');
    
    // Update live status
    this.updateLiveStatus();
  }

  async captureScreenshotSilent() {
    try {
      // Request screenshot through background script (without status updates)
      const response = await chrome.runtime.sendMessage({
        action: 'captureScreenshot'
      });
      
      if (response && response.success && response.dataUrl) {
        // Update the screenshot silently
        this.displayScreenshot(response.dataUrl, response.tabUrl);
        
        // Store the current image for sending to Gemini
        this.currentImage = response.dataUrl;
        
        // Send to Gemini if recording
        if (this.isRecording && this.session && this.currentImageBase64) {
          try {
            const imageBlob = {
              data: this.currentImageBase64,
              mimeType: this.currentImageMimeType
            };
            this.session.sendRealtimeInput({ media: imageBlob });
            console.log("[captureScreenshotSilent] Sent screenshot to Gemini");
          } catch (e) {
            console.error("[captureScreenshotSilent] Error sending to Gemini:", e);
          }
        }
        
      } else {
        console.warn('[captureScreenshotSilent] Failed to capture:', response?.error);
        // Don't stop auto-capture for temporary failures - just skip this capture
        // This allows the periodic capture to continue even when tabs change focus
      }
    } catch (error) {
      console.warn('[captureScreenshotSilent] Capture failed, continuing auto-capture:', error.message);
      // Continue auto-capture even if individual captures fail
      // This prevents stopping the entire feature due to temporary tab focus issues
    }
  }

  removeImage() {
    this.currentImageBase64 = null;
    this.currentImageMimeType = null;
    this.imagePreviewContainer.style.display = 'none';
    this.stopCapture();
    this.stopAutoScreenshot(); // Also stop auto-screenshot when removing image
  }

  // Periodic image sending for live screen share
  startPeriodicImageSending() {
    if (this.imageSendIntervalId) {
      clearInterval(this.imageSendIntervalId);
    }
    
    if (!this.session || !this.isSetupComplete || !this.isRecording) {
      console.log("[startPeriodicImageSending] Conditions not met");
      return;
    }

    console.log("[startPeriodicImageSending] Starting periodic image sending");
    
    // Send immediately
    if (this.isCapturingScreen && this.captureVideo) {
      this.captureFrame(this.captureVideo);
    }
    this.sendPeriodicImageData();
    
    // Set up interval for continuous sending
    this.imageSendIntervalId = setInterval(() => {
      if (this.isCapturingScreen && this.captureVideo) {
        this.captureFrame(this.captureVideo);
      }
      this.sendPeriodicImageData();
    }, IMAGE_SEND_INTERVAL_MS);
  }

  stopPeriodicImageSending() {
    if (this.imageSendIntervalId) {
      console.log("[stopPeriodicImageSending] Stopping periodic image sending");
      clearInterval(this.imageSendIntervalId);
      this.imageSendIntervalId = null;
    }
  }

  sendPeriodicImageData() {
    if (this.currentImageBase64 && this.currentImageMimeType && this.session && this.isRecording && this.isSetupComplete) {
      console.log(`[sendPeriodicImageData] Sending image. MimeType: ${this.currentImageMimeType}`);
      const imageBlob = {
        data: this.currentImageBase64,
        mimeType: this.currentImageMimeType
      };
      try {
        this.session.sendRealtimeInput({ media: imageBlob });
      } catch (e) {
        console.error("[sendPeriodicImageData] Error sending image:", e);
      }
    }
  }

  // Voice recording methods (continued in next part...)
  async toggleRecording() {
    console.log(`[toggleRecording] Current state isRecording: ${this.isRecording}`);
    
    if (!this.genAI) {
      this.updateStatus('Please initialize Gemini AI first', true);
      return;
    }
    
    const audioSystemReady = await this.initializeAudioSystem();
    if (!audioSystemReady) {
      this.updateStatus("Audio system failed to initialize.", true);
      return;
    }
    
    if (this.isRecording) {
      this.stopRecording();
    } else {
      this.isRecording = true;
      this.updateButtonUI();
      await this.startRecording();
    }
  }

  // Initialize audio system with worklet
  async initializeAudioSystem() {
    console.log("[initializeAudioSystem] Initializing...");
    
    if (!this.audioContext) {
      try {
        this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
        console.log(`[initializeAudioSystem] AudioContext created. Sample Rate: ${this.audioContext.sampleRate}`);
        
        if (this.audioContext.state === 'suspended') {
          await this.audioContext.resume();
        }
        
      } catch (error) {
        console.error('[initializeAudioSystem] Error creating AudioContext:', error);
        this.updateStatus('Error initializing audio system', true);
        return false;
      }
    } else {
      console.log(`[initializeAudioSystem] AudioContext already exists. Sample Rate: ${this.audioContext.sampleRate}`);
      
      if (this.audioContext.state === 'suspended') {
        try {
          await this.audioContext.resume();
          console.log("[initializeAudioSystem] AudioContext resumed");
        } catch (error) {
          console.error('[initializeAudioSystem] Error resuming:', error);
          return false;
        }
      }
    }
    
    // Always ensure AudioWorklet is loaded (whether AudioContext is new or existing)
    try {
      console.log("[initializeAudioSystem] Ensuring AudioWorklet is loaded...");
      await this.addAudioWorklet();
    } catch (error) {
      console.error('[initializeAudioSystem] Error loading AudioWorklet:', error);
      this.updateStatus('Error loading audio processor', true);
      return false;
    }
    
    console.log("[initializeAudioSystem] Audio system ready");
    return true;
  }

  async addAudioWorklet() {
    try {
      console.log("[addAudioWorklet] Loading AudioWorklet module...");
      
      // Use the external audio processor file instead of inline code to avoid CSP issues
      const workletURL = chrome.runtime.getURL('audio-processor.js');
      await this.audioContext.audioWorklet.addModule(workletURL);
      
      console.log("[addAudioWorklet] Audio worklet added successfully");
    } catch (error) {
      // Check if the error is because the module is already loaded
      if (error.name === 'InvalidStateError' && error.message.includes('already exists')) {
        console.log("[addAudioWorklet] AudioWorklet module already loaded");
        return; // This is fine, module is already available
      }
      
      console.error('[addAudioWorklet] Error:', error);
      throw error;
    }
  }

  // Rest of the voice recording methods will be continued in the next message due to length...
  async startRecording() {
    console.log("[startRecording] Starting recording...");
    
    if (!this.audioContext) {
      this.updateStatus("Audio system not ready.", true);
      this.isRecording = false;
      this.updateButtonUI();
      return;
    }
    
    // Connect to Gemini
    const connected = await this.connectToGeminiIfNeeded();
    if (!connected) {
      this.updateStatus("Connection failed", true);
      this.isRecording = false;
      this.updateButtonUI();
      return;
    }
    
    // Wait for setup to complete if it hasn't already
    if (!this.isSetupComplete) {
      console.log("[startRecording] Waiting for setup to complete...");
      let attempts = 0;
      while (!this.isSetupComplete && attempts < 20) { // Wait up to 10 seconds
        await new Promise(resolve => setTimeout(resolve, 500));
        attempts++;
        console.log(`[startRecording] Setup wait attempt ${attempts}/20`);
      }
      
      if (!this.isSetupComplete) {
        this.updateStatus("Setup timeout - please try again", true);
        this.isRecording = false;
        this.updateButtonUI();
        return;
      }
    }
    
    if (!this.isRecording) {
      console.warn("[startRecording] Recording was cancelled");
      return;
    }
    
    this.updateStatus('Requesting microphone...');
    
    try {
      console.log("[startRecording] Requesting microphone access...");
      this.micStream = await navigator.mediaDevices.getUserMedia({ 
        audio: { 
          channelCount: 1,
          sampleRate: 48000, // Request high sample rate
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        } 
      });
      
      console.log("[startRecording] Microphone stream created:", this.micStream);
      console.log("[startRecording] Audio tracks:", this.micStream.getAudioTracks().map(track => ({
        label: track.label,
        enabled: track.enabled,
        muted: track.muted,
        readyState: track.readyState
      })));
      
      this.micSourceNode = this.audioContext.createMediaStreamSource(this.micStream);
      console.log("[startRecording] Created MediaStreamSource node");
      
      this.audioWorkletNode = new AudioWorkletNode(this.audioContext, 'audio-processor', {
        processorOptions: {
          targetSampleRate: TARGET_SAMPLE_RATE,
          bufferSize: WORKLET_BUFFER_SIZE
        }
      });
      console.log("[startRecording] Created AudioWorklet node");
      
      this.audioWorkletNode.port.onmessage = (event) => {
        if (event.data.debug) {
          console.log(`[AudioWorklet] ${event.data.debug}`);
          return;
        }
        
        if (event.data.error) {
          console.error(`[AudioWorklet] Error: ${event.data.error}`);
          return;
        }
        
        if (event.data.audioData && this.session && this.isRecording) {
          const audioArrayBuffer = event.data.audioData;
          if (audioArrayBuffer.byteLength === 0) {
            console.log("[AudioWorklet] Received empty audio buffer");
            return;
          }
          
                          // Audio data received (removed verbose logging)
          
          // Calculate audio level for visualization
          const int16Array = new Int16Array(audioArrayBuffer);
          let sum = 0;
          for (let i = 0; i < int16Array.length; i++) {
            sum += Math.abs(int16Array[i]);
          }
          const averageLevel = sum / int16Array.length / 32768; // Normalize to 0-1
          console.log(`[AudioWorklet] Audio level: ${(averageLevel * 100).toFixed(1)}%`);
          this.updateAudioLevel(averageLevel);
          
          const base64AudioData = arrayBufferToBase64(audioArrayBuffer);
          const audioMediaBlob = {
            data: base64AudioData,
            mimeType: `audio/pcm;rate=${TARGET_SAMPLE_RATE}`
          };
          
          if (this.session && this.isRecording) {
                            // Sending audio data to Gemini (removed verbose logging)
            this.session.sendRealtimeInput({ media: audioMediaBlob });
          } else {
            console.warn("[AudioWorklet] Cannot send audio - session not ready or not recording");
          }
                    }
      };
      
      this.micSourceNode.connect(this.audioWorkletNode);
      
      // Connect AudioWorklet to destination to ensure it processes audio
      // (Some browsers require this for AudioWorklet to actually run)
      const gainNode = this.audioContext.createGain();
      gainNode.gain.value = 0; // Mute the output so we don't hear feedback
      this.audioWorkletNode.connect(gainNode);
      gainNode.connect(this.audioContext.destination);
      
      console.log("[startRecording] Microphone connected to AudioWorklet");
      console.log("[startRecording] Audio pipeline: Microphone -> MediaStreamSource -> AudioWorklet -> GainNode(muted) -> Destination");
      console.log("[startRecording] AudioContext state:", this.audioContext.state);
      console.log("[startRecording] AudioContext sample rate:", this.audioContext.sampleRate);
      
      // Add an AnalyserNode to test if we're getting any audio signal
      const analyser = this.audioContext.createAnalyser();
      analyser.fftSize = 256;
      this.micSourceNode.connect(analyser);
      
      // Test if microphone is actually producing audio
      setTimeout(() => {
        const tracks = this.micStream.getAudioTracks();
        tracks.forEach((track, index) => {
          console.log(`[startRecording] Audio track ${index}:`, {
            label: track.label,
            enabled: track.enabled,
            muted: track.muted,
            readyState: track.readyState,
            settings: track.getSettings()
          });
        });
        
        // Test audio levels with AnalyserNode
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);
        const average = dataArray.reduce((a, b) => a + b) / dataArray.length;
        console.log(`[startRecording] AnalyserNode audio level test: ${average.toFixed(2)} (should be > 0 if microphone is working)`);
        
        // Continue testing for a few seconds
        let testCount = 0;
        const testInterval = setInterval(() => {
          analyser.getByteFrequencyData(dataArray);
          const avg = dataArray.reduce((a, b) => a + b) / dataArray.length;
          console.log(`[startRecording] Audio level test ${testCount + 1}: ${avg.toFixed(2)}`);
          testCount++;
          if (testCount >= 5) {
            clearInterval(testInterval);
          }
        }, 1000);
      }, 1000);
      
      this.updateStatus('Listening...');
      this.startPeriodicImageSending();
      
    } catch (error) {
      console.error('[startRecording] Error:', error);
      this.updateStatus(`Microphone error: ${error.message}`, true);
      this.isRecording = false;
      this.updateButtonUI();
      this.cleanupAudioNodes();
    }
  }

  async connectToGeminiIfNeeded() {
    if (this.session && this.isSetupComplete) {
      console.log("[connectToGeminiIfNeeded] Already connected and setup complete");
      return true;
    }
    
    if (this.session && !this.isSetupComplete) {
      console.log("[connectToGeminiIfNeeded] Connection exists, waiting for setup to complete");
      // Wait a bit for setup to complete
      let attempts = 0;
      while (!this.isSetupComplete && attempts < 10) {
        await new Promise(resolve => setTimeout(resolve, 500));
        attempts++;
      }
      return this.isSetupComplete;
    }
    
    console.log("[connectToGeminiIfNeeded] Connecting...");
    this.isSetupComplete = false;
    return this.connectToGemini();
  }

  async connectToGemini() {
    this.updateStatus('Connecting to Gemini...');
    console.log("[connectToGemini] Connecting...");
    this.isSetupComplete = false;
    
    try {
      if (this.session) {
        try { this.session.close(); } catch (e) { console.warn("Error closing previous session:", e); }
        this.session = null;
      }
      
      this.session = await this.genAI.live.connect({
        model: 'gemini-2.0-flash-live-001',
        config: {
          responseModalities: ['AUDIO']
        },
        callbacks: {
          onopen: () => {
            console.log("[connectToGemini] Connection established");
            this.updateStatus('Connected! Finalizing setup...');
          },
          onmessage: (eventMessage) => {
            const response = eventMessage;
            
            if (response?.setupComplete) {
              console.log("[connectToGemini] Setup complete");
              this.isSetupComplete = true;
              this.updateStatus('Ready to chat');
              
              // Don't call startRecording again - it's already running
              if (this.isRecording) {
                console.log("[connectToGemini] Setup complete, recording can continue");
              }
            }
            
            if (response?.serverContent) {
              // Handle input transcription (user's speech) - streaming
              if (response.serverContent.inputTranscription) {
                console.log("[TRANSCRIPT] INPUT:", JSON.stringify(response.serverContent.inputTranscription.text));
                console.log("[TRANSCRIPT] INPUT LENGTH:", response.serverContent.inputTranscription.text.length);
                console.log("[TRANSCRIPT] INPUT CURRENT ACCUMULATED LENGTH:", (this.currentInputAccumulated || '').length);
                this.addTranscriptMessage(response.serverContent.inputTranscription.text, true, true);
              }
              
              // Handle output transcription (AI's speech) - streaming
              if (response.serverContent.outputTranscription) {
                console.log("[TRANSCRIPT] OUTPUT:", JSON.stringify(response.serverContent.outputTranscription.text));
                console.log("[TRANSCRIPT] OUTPUT LENGTH:", response.serverContent.outputTranscription.text.length);
                console.log("[TRANSCRIPT] OUTPUT CURRENT ACCUMULATED LENGTH:", (this.currentOutputAccumulated || '').length);
                this.addTranscriptMessage(response.serverContent.outputTranscription.text, false, true);
              }
              
              // Handle model turn (text and audio responses)
              if (response.serverContent.modelTurn?.parts) {
                response.serverContent.modelTurn.parts.forEach(part => {
                  if (part.text) {
                    console.log(`[Gemini Text]: ${part.text}`);
                    // Text responses now handled via transcription only
                  }
                  
                  if (part.inlineData?.data && typeof part.inlineData.data === 'string') {
                    try {
                      const audioArrayBuffer = base64ToArrayBuffer(part.inlineData.data);
                      this.enqueueAudio(audioArrayBuffer);
                    } catch (e) {
                      console.error("[connectToGemini] Error decoding audio:", e);
                    }
                  }
                });
              }
              
              if (response.serverContent.turnComplete) {
                console.log('[connectToGemini] Turn complete');
                // Finalize both input and output transcripts for this turn
                this.finishTranscriptTurn(true);  // User turn
                this.finishTranscriptTurn(false); // AI turn
                if (!this.isRecording && this.isSetupComplete) {
                  this.updateStatus('Ready to chat');
                }
              }
            }
          },
          onerror: (errorEvent) => {
            const errorMessage = errorEvent.message || errorEvent.error?.message || 'WebSocket error';
            console.error("[connectToGemini] Error:", errorEvent, "Message:", errorMessage);
            this.updateStatus(`Connection error: ${errorMessage}`, true);
            this.cleanupAfterErrorOrClose(true);
          },
          onclose: (closeEvent) => {
            let statusMsg = 'Disconnected';
            if (!closeEvent.wasClean && this.isRecording) {
              statusMsg = `Disconnected unexpectedly (Code: ${closeEvent.code})`;
              this.updateStatus(statusMsg, true);
            } else if (closeEvent.code === 1000 && !this.isRecording) {
              statusMsg = 'Call ended';
              this.updateStatus(statusMsg);
            } else if (closeEvent.code !== 1000) {
              statusMsg = `Disconnected (Code: ${closeEvent.code})`;
              this.updateStatus(statusMsg, true);
            } else {
              this.updateStatus(statusMsg);
            }
            
            console.warn(`[connectToGemini] Closed: Code ${closeEvent.code}, Reason: ${closeEvent.reason}`);
            this.cleanupAfterErrorOrClose(false);
          }
        }
      });
      
      console.log("[connectToGemini] Connection initiated");
      return true;
      
    } catch (error) {
      console.error("[connectToGemini] Error:", error);
      this.updateStatus(`Connection failed: ${error.message}`, true);
      this.cleanupAfterErrorOrClose(true);
      return false;
    }
  }

  cleanupAfterErrorOrClose(isErrorOrigin = false) {
    console.log(`[cleanupAfterErrorOrClose] Cleaning up. Error origin: ${isErrorOrigin}`);
    
    if (this.isRecording) {
      this.isRecording = false;
    }
    
    this.isSetupComplete = false;
    this.stopPeriodicImageSending();
    this.cleanupAudioNodes();
    
    if (this.session) {
      this.session = null;
    }
    
    this.clearAudioQueueAndStopPlayback();
    this.updateLiveStatus();
    if (this.startLiveChatBtn) {
      this.startLiveChatBtn.disabled = false;
    }
    
    if (!isErrorOrigin && !this.statusText.textContent.toLowerCase().includes("error")) {
      if (this.statusText.textContent !== 'Call ended') {
        this.updateStatus('Ready to chat');
      }
    }
  }

  enqueueAudio(audioArrayBuffer) {
    this.audioQueue.push(audioArrayBuffer);
    if (!this.isPlayingAudio) {
      this.playNextInQueue();
    }
  }

  async playNextInQueue() {
    if (this.audioQueue.length === 0) {
      this.isPlayingAudio = false;
      if (!this.isRecording && this.isSetupComplete) {
        this.updateStatus('Ready to chat');
      } else if (this.isRecording) {
        this.updateStatus('Listening...');
      }
      return;
    }
    
    this.isPlayingAudio = true;
    const audioArrayBuffer = this.audioQueue.shift();
    
    if (audioArrayBuffer.byteLength < 2) {
      console.warn('[playNextInQueue] Audio buffer too short');
      this.isPlayingAudio = false;
      this.playNextInQueue();
      return;
    }
    
    if (!this.audioContext || this.audioContext.state !== 'running') {
      const audioSystemReady = await this.initializeAudioSystem();
      if (!audioSystemReady || !this.audioContext) {
        this.updateStatus('Audio playback error', true);
        this.isPlayingAudio = false;
        this.audioQueue.unshift(audioArrayBuffer);
        return;
      }
    }
    
    try {
      const PLAYBACK_SAMPLE_RATE = 24000;
      const int16Array = new Int16Array(audioArrayBuffer);
      const float32Array = new Float32Array(int16Array.length);
      
      for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
      }
      
      const audioBuffer = this.audioContext.createBuffer(1, float32Array.length, PLAYBACK_SAMPLE_RATE);
      audioBuffer.copyToChannel(float32Array, 0);
      
      const source = this.audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.audioContext.destination);
      source.start();
      
      this.updateStatus('Playing response...');
      
      source.onended = () => {
        this.playNextInQueue();
      };
      
    } catch (error) {
      console.error("[playNextInQueue] Error:", error);
      this.updateStatus(`Audio playback error: ${error.message}`, true);
      this.isPlayingAudio = false;
      this.playNextInQueue();
    }
  }

  clearAudioQueueAndStopPlayback() {
    this.audioQueue = [];
    this.isPlayingAudio = false;
    console.log("[clearAudioQueueAndStopPlayback] Audio queue cleared");
  }

  stopRecording() {
    console.log("[stopRecording] Stopping recording");
    
    if (!this.isRecording && !this.session) {
      this.isRecording = false;
      this.updateButtonUI();
      this.cleanupAudioNodes();
      return;
    }
    
    this.isRecording = false;
    this.stopPeriodicImageSending();
    this.updateLiveStatus();
    this.cleanupAudioNodes();
    
    if (this.session) {
      this.updateStatus('Ending call...');
      try {
        this.session.close();
      } catch (e) {
        console.warn("[stopRecording] Error closing session:", e);
        this.cleanupAfterErrorOrClose(true);
      }
    } else {
      this.updateStatus('Ready to chat');
    }
  }

  cleanupAudioNodes() {
    if (this.audioWorkletNode) {
      this.audioWorkletNode.port.onmessage = null;
      this.audioWorkletNode.disconnect();
      this.audioWorkletNode = null;
    }
    
    if (this.micSourceNode) {
      this.micSourceNode.disconnect();
      this.micSourceNode = null;
    }
    
    if (this.micStream) {
      this.micStream.getTracks().forEach(track => track.stop());
      this.micStream = null;
    }
    
    console.log("[cleanupAudioNodes] Audio cleanup complete");
  }

  // Legacy method - replaced by updateLiveStatus
  updateButtonUI() {
    // This method is no longer used in the streamlined live chat interface
    // Status updates are now handled by updateLiveStatus()
  }

  // Audio Visualization Methods
  showAudioVisualizer() {
    if (this.audioVisualizer) {
      this.audioVisualizer.style.display = 'block';
      this.startAudioVisualization();
    }
  }

  hideAudioVisualizer() {
    if (this.audioVisualizer) {
      this.audioVisualizer.style.display = 'none';
      this.stopAudioVisualization();
    }
  }

  startAudioVisualization() {
    if (this.animationFrameId) return; // Already running
    
    const animate = () => {
      this.updateAudioVisualization();
      this.animationFrameId = requestAnimationFrame(animate);
    };
    animate();
  }

  stopAudioVisualization() {
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
      this.animationFrameId = null;
    }
    
    // Reset visualization
    if (this.audioLevelFill) {
      this.audioLevelFill.style.width = '0%';
    }
    if (this.audioLevelText) {
      this.audioLevelText.textContent = '0%';
    }
    if (this.waveformCtx) {
      this.waveformCtx.clearRect(0, 0, this.audioWaveform.width, this.audioWaveform.height);
    }
  }

  updateAudioLevel(level) {
    // Normalize level to 0-100 range
    this.currentAudioLevel = Math.min(100, Math.max(0, level * 100));
    
    // Update breathing indicator intensity based on audio level
    if (this.breathingIndicator && this.isLiveChatActive) {
      const intensity = Math.max(0.7, 0.7 + (this.currentAudioLevel / 100) * 0.3); // Range 0.7-1.0
      this.breathingIndicator.style.transform = `scale(${intensity})`;
    }
    
    // Add to history for waveform
    this.audioLevelHistory.shift();
    this.audioLevelHistory.push(this.currentAudioLevel);
  }

  updateAudioVisualization() {
    // Update level bar
    if (this.audioLevelFill && this.audioLevelText) {
      const smoothedLevel = this.currentAudioLevel * 0.8; // Smooth the display
      this.audioLevelFill.style.width = `${smoothedLevel}%`;
      this.audioLevelText.textContent = `${Math.round(smoothedLevel)}%`;
    }

    // Update waveform
    if (this.waveformCtx && this.audioWaveform) {
      const ctx = this.waveformCtx;
      const canvas = this.audioWaveform;
      const width = canvas.width;
      const height = canvas.height;
      
      // Clear canvas
      ctx.clearRect(0, 0, width, height);
      
      // Draw waveform
      ctx.strokeStyle = '#007bff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      
      const stepX = width / (this.audioLevelHistory.length - 1);
      
      for (let i = 0; i < this.audioLevelHistory.length; i++) {
        const x = i * stepX;
        const y = height - (this.audioLevelHistory[i] / 100) * height;
        
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      
      ctx.stroke();
      
      // Draw baseline
      ctx.strokeStyle = '#e0e0e0';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, height - 1);
      ctx.lineTo(width, height - 1);
      ctx.stroke();
    }
  }
}

// Initialize the assistant when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  console.log('Initializing Gemini Live Assistant');
  new GeminiLiveAssistant();
}); 