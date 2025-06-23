/**
 * permission.js
 * Requests user permission for microphone access from within an iframe.
 */

console.log("[Permission] Permission request script loaded");

async function requestMicrophonePermission() {
  try {
    console.log("[Permission] Requesting microphone access...");
    
    // Request microphone access
    const stream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000
      }
    });
    
    console.log("[Permission] Microphone access granted");
    
    // Stop the tracks immediately to prevent recording indicator
    stream.getTracks().forEach(track => {
      track.stop();
    });
    
    // Send success message to parent window
    window.parent.postMessage({
      type: 'MICROPHONE_PERMISSION_RESULT',
      success: true,
      message: 'Microphone permission granted'
    }, '*');
    
  } catch (error) {
    console.error("[Permission] Error requesting microphone permission:", error);
    
    let errorMessage = 'Microphone permission denied';
    
    if (error.name === 'NotAllowedError') {
      errorMessage = 'Microphone access denied by user';
    } else if (error.name === 'NotFoundError') {
      errorMessage = 'No microphone found';
    } else if (error.name === 'NotReadableError') {
      errorMessage = 'Microphone is being used by another application';
    } else {
      errorMessage = `Microphone error: ${error.message}`;
    }
    
    // Send error message to parent window
    window.parent.postMessage({
      type: 'MICROPHONE_PERMISSION_RESULT',
      success: false,
      error: errorMessage
    }, '*');
  }
}

// Start the permission request when the script loads
requestMicrophonePermission(); 