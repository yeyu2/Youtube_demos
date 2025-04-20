class AudioProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.sampleRate = options.processorOptions.sampleRate || 16000;
    this.bufferSize = options.processorOptions.bufferSize || 4096;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
    this.isProcessing = false;
    
    // Add a timer to ensure buffers are sent even if not full
    this.lastSendTime = currentTime;
    this.MAX_BUFFER_AGE = 0.5; // Send buffer after 500ms even if not full
  }

  process(inputs, outputs, parameters) {
    // Get the first channel of the first input
    const input = inputs[0][0];
    
    // Always process, even with empty input (send silence)
    if (!input || input.length === 0) {
      // If we haven't sent data in a while, send what we have (even if buffer not full)
      if (currentTime - this.lastSendTime > this.MAX_BUFFER_AGE && this.bufferIndex > 0) {
        this.sendBuffer();
      }
      return true;
    }

    // Fill the buffer with input samples
    for (let i = 0; i < input.length; i++) {
      if (this.bufferIndex < this.bufferSize) {
        // Apply a gentle limiter to prevent clipping
        const sample = Math.max(-0.95, Math.min(0.95, input[i]));
        this.buffer[this.bufferIndex++] = sample;
      }
    }

    // If buffer is full or it's been too long since last send, send the buffer
    if ((this.bufferIndex >= this.bufferSize || 
         currentTime - this.lastSendTime > this.MAX_BUFFER_AGE) && 
        !this.isProcessing) {
      this.sendBuffer();
    }
    
    return true;
  }
  
  sendBuffer() {
    if (this.bufferIndex === 0) return;
    
    this.isProcessing = true;
    this.lastSendTime = currentTime;
    
    // Calculate audio level (RMS)
    let sumSquares = 0;
    for (let i = 0; i < this.bufferIndex; i++) {
      sumSquares += this.buffer[i] * this.buffer[i];
    }
    const rms = Math.sqrt(sumSquares / this.bufferIndex);
    const level = Math.min(rms * 100 * 5, 100);
    
    // Convert to 16-bit PCM
    const pcmData = new Int16Array(this.bufferIndex);
    for (let i = 0; i < this.bufferIndex; i++) {
      // Convert float32 (-1.0 to 1.0) to int16 (-32768 to 32767)
      pcmData[i] = Math.max(-32768, Math.min(32767, Math.round(this.buffer[i] * 32767)));
    }
    
    // Send the PCM data to the main thread
    this.port.postMessage({
      pcmData: pcmData.buffer,
      level: level
    }, [pcmData.buffer]);
    
    // Reset buffer
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
    this.isProcessing = false;
  }
}

registerProcessor('audio-processor', AudioProcessor); 