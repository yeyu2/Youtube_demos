/**
 * audio-processor.js
 * AudioWorklet processor for real-time audio processing and resampling
 */

class AudioProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.sampleRate = sampleRate;
    this.targetSampleRate = options.processorOptions.targetSampleRate || 16000;
    this.bufferSize = options.processorOptions.bufferSize || 4096;
    const minInternalBufferSize = Math.ceil(this.bufferSize * (this.sampleRate / this.targetSampleRate)) + 128;
    this._internalBuffer = new Float32Array(Math.max(minInternalBufferSize, this.bufferSize * 2));
    this._internalBufferIndex = 0;
    this.isProcessing = false;
    this.lastSendTime = 0;
    this.MAX_BUFFER_AGE_SECONDS = 0.5;
    this.resampleRatio = this.sampleRate / this.targetSampleRate;
    this.processCallCount = 0;
    this.port.postMessage({ 
      debug: `Worklet Initialized. NativeSR: ${this.sampleRate}, TargetSR: ${this.targetSampleRate}, Ratio: ${this.resampleRatio}` 
    });
  }
  
  process(inputs, outputs, parameters) {
    this.processCallCount++;
    
    // Log first few process calls to confirm it's being called
    if (this.processCallCount <= 5) {
      this.port.postMessage({ debug: `Process call #${this.processCallCount}, inputs: ${inputs.length}, input[0]: ${inputs[0] ? inputs[0].length : 'none'}` });
    }
    
    const inputChannel = inputs[0] && inputs[0][0];
    if (inputChannel && inputChannel.length > 0) {
      // Debug: Check if we're receiving audio data
      if (!this.hasLoggedInput) {
        this.port.postMessage({ debug: `First audio input received: ${inputChannel.length} samples` });
        this.hasLoggedInput = true;
      }
      
      if (this._internalBufferIndex + inputChannel.length <= this._internalBuffer.length) {
        this._internalBuffer.set(inputChannel, this._internalBufferIndex);
        this._internalBufferIndex += inputChannel.length;
      } else {
        const remainingSpace = this._internalBuffer.length - this._internalBufferIndex;
        if (remainingSpace > 0) {
          this._internalBuffer.set(inputChannel.slice(0, remainingSpace), this._internalBufferIndex);
          this._internalBufferIndex += remainingSpace;
        }
      }
    } else if (!this.hasLoggedNoInput) {
      this.port.postMessage({ debug: "No audio input received" });
      this.hasLoggedNoInput = true;
    }
    
    const minInputSamplesForOneOutputBuffer = Math.floor(this.bufferSize * this.resampleRatio);
    const shouldSendByTime = (currentTime - this.lastSendTime > this.MAX_BUFFER_AGE_SECONDS && this._internalBufferIndex > 0);
    const shouldSendByFill = (this._internalBufferIndex >= minInputSamplesForOneOutputBuffer);
    
    if ((shouldSendByFill || shouldSendByTime) && !this.isProcessing) {
      this.sendResampledBuffer(currentTime);
    }
    
    return true;
  }
  
  sendResampledBuffer(currentTime) {
    if (this._internalBufferIndex === 0) return;
    
    this.isProcessing = true;
    
    try {
      const inputData = this._internalBuffer.slice(0, this._internalBufferIndex);
      const outputLength = Math.floor(inputData.length / this.resampleRatio);
      const outputData = new Float32Array(outputLength);
      
      // Simple linear interpolation resampling
      for (let i = 0; i < outputLength; i++) {
        const srcIndex = i * this.resampleRatio;
        const srcIndexFloor = Math.floor(srcIndex);
        const srcIndexCeil = Math.min(srcIndexFloor + 1, inputData.length - 1);
        const fraction = srcIndex - srcIndexFloor;
        
        outputData[i] = inputData[srcIndexFloor] * (1 - fraction) + inputData[srcIndexCeil] * fraction;
      }
      
      // Convert to Int16Array for transmission
      const int16Data = new Int16Array(outputLength);
      for (let i = 0; i < outputLength; i++) {
        const sample = Math.max(-1, Math.min(1, outputData[i]));
        int16Data[i] = sample * 32767;
      }
      
      // Send the processed audio data
      this.port.postMessage({
        audioData: int16Data.buffer,
        sampleRate: this.targetSampleRate,
        length: outputLength
      }, [int16Data.buffer]);
      
      this.lastSendTime = currentTime || 0;
      
    } catch (error) {
      this.port.postMessage({ error: `Processing error: ${error.message}` });
    }
    
    // Reset buffer
    this._internalBufferIndex = 0;
    this.isProcessing = false;
  }
}

registerProcessor('audio-processor', AudioProcessor); 