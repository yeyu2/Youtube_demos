import React, {
    createContext,
    useContext,
    useEffect,
    useState,
    useRef,
    useCallback,
  } from "react";
  import { Base64 } from 'js-base64';
  
  interface TranscriptionMessage {
    text: string;
    sender: "User" | "Gemini";
    finished: boolean | null;
  }

  interface WebSocketContextType {
    sendMessage: (message: any) => void;
    sendMediaChunk: (chunk: MediaChunk) => void;
    lastTranscription: TranscriptionMessage | null;
    lastAudioData: string | null;
    isConnected: boolean;
    playbackAudioLevel: number;
  }
  
  interface MediaChunk {
    mime_type: string;
    data: string;
  }
  
  interface AudioChunkBuffer {
    data: ArrayBuffer[];
    startTimestamp: number;
  }
  
  const WebSocketContext = createContext<WebSocketContextType | null>(null);
  
  const RECONNECT_TIMEOUT = 5000; // 5 seconds
  const CONNECTION_TIMEOUT = 30000; // 30 seconds
  const AUDIO_BUFFER_DURATION = 2000; // 2 seconds in milliseconds
  const LOOPBACK_DELAY = 3000; // 3 seconds delay matching backend
  
  export const WebSocketProvider: React.FC<{ children: React.ReactNode; url: string }> = ({
    children,
    url,
  }: { children: React.ReactNode; url: string }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [playbackAudioLevel, setPlaybackAudioLevel] = useState(0);
    const [lastTranscription, setLastTranscription] = useState<TranscriptionMessage | null>(null);
    const [lastAudioData, setLastAudioData] = useState<string | null>(null);
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimeoutRef = useRef<NodeJS.Timeout>();
    const connectionTimeoutRef = useRef<NodeJS.Timeout>();
    const audioContextRef = useRef<AudioContext | null>(null);
    const audioBufferQueueRef = useRef<AudioChunkBuffer[]>([]);
    const currentChunkRef = useRef<AudioChunkBuffer | null>(null);
    const playbackIntervalRef = useRef<NodeJS.Timeout>();
    const reconnectAttemptsRef = useRef(0);
    const currentAudioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  
    // Initialize audio context for playback
    const initAudioContext = useCallback(() => {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext({
          sampleRate: 24000, // Match the server's 24kHz sample rate
        });
      }
      return audioContextRef.current;
    }, []);
  
    const connect = () => {
      // Don't reconnect if already connecting or connected
      if (wsRef.current && (wsRef.current.readyState === WebSocket.CONNECTING || 
                            wsRef.current.readyState === WebSocket.OPEN)) {
        console.log("WebSocket already connecting or connected, skipping reconnect");
        return;
      }
  
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;
  
        // Set connection timeout
        connectionTimeoutRef.current = setTimeout(() => {
          if (ws.readyState !== WebSocket.OPEN) {
            ws.close();
            reconnect();
          }
        }, CONNECTION_TIMEOUT);
  
        ws.binaryType = 'arraybuffer'; // Enable binary message support
  
        ws.onopen = () => {
          setIsConnected(true);
          if (connectionTimeoutRef.current) {
            clearTimeout(connectionTimeoutRef.current);
          }
          
          // Send initial setup message only once
          console.log("WebSocket connected, sending initial setup");
          sendMessage({
            setup: {
              // Add any needed config options
            }
          });
        };
  
        ws.onclose = () => {
          setIsConnected(false);
          reconnect();
        };
  
        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          ws.close();
        };
  
        ws.onmessage = async (event) => {
          try {
            const data = JSON.parse(event.data);
            
            if (data.transcription) {
              setLastTranscription({
                text: data.transcription.text,
                sender: data.transcription.sender,
                finished: data.transcription.finished
              });
            }
            
            if (data.interrupted) {
              // Stop current audio playback and clear buffer
              console.log('Received interruption signal, stopping audio playback');
              
              if (currentAudioSourceRef.current) {
                currentAudioSourceRef.current.stop();
                currentAudioSourceRef.current = null;
              }
              audioBufferQueueRef.current = [];
              setPlaybackAudioLevel(0);
            }
            
            if (data.audio) {
              setLastAudioData(data.audio);
              const audioBuffer = Base64.toUint8Array(data.audio);
              
              const now = Date.now();
              const newChunk = {
                data: [audioBuffer.buffer],
                startTimestamp: now
              };
              
              audioBufferQueueRef.current.push(newChunk);
            }
          } catch (error) {
            console.error('Error handling message:', error);
          }
        };
      } catch (error) {
        console.error('WebSocket connection error:', error);
        reconnect();
      }
    };
  
    const sendBinary = (data: ArrayBuffer) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(data);
      }
    };
  
    // Fix the audio playback approach
    useEffect(() => {
      let isPlaybackActive = false;
      
      // Function to play the next chunk when available
      const playNextWhenReady = async () => {
        if (isPlaybackActive || audioBufferQueueRef.current.length === 0) {
          return;
        }
        
        isPlaybackActive = true;
        
        try {
          // Get all available chunks for a single playback
          const allChunks = [...audioBufferQueueRef.current];
          audioBufferQueueRef.current = [];
          
          // Combine all buffers from all chunks
          const allBuffers: ArrayBuffer[] = [];
          allChunks.forEach(chunk => {
            allBuffers.push(...chunk.data);
          });
          
          // Play the combined audio
          await playAudioChunk(allBuffers);
          
          // Check if more chunks arrived during playback
          if (audioBufferQueueRef.current.length > 0) {
            // Continue playing without delay
            playNextWhenReady();
          }
        } catch (error) {
          console.error("Error in audio playback:", error);
        } finally {
          isPlaybackActive = false;
        }
      };
      
      // Set up a polling mechanism instead of overriding push
      const checkInterval = setInterval(() => {
        if (audioBufferQueueRef.current.length > 0 && !isPlaybackActive) {
          playNextWhenReady();
        }
      }, 50);
      
      // Also check when new audio data is received
      const originalPush = Array.prototype.push;
      audioBufferQueueRef.current.push = function(...items) {
        const result = originalPush.apply(this, items);
        setTimeout(playNextWhenReady, 0);
        return result;
      };
      
      return () => {
        clearInterval(checkInterval);
        // Restore original push method
        if (audioBufferQueueRef.current) {
          audioBufferQueueRef.current.push = originalPush;
        }
      };
    }, []);
  
    // New function to play concatenated audio chunks
    const playAudioChunk = useCallback((audioBuffers: ArrayBuffer[]): Promise<void> => {
      return new Promise((resolve, reject) => {
        try {
          const ctx = initAudioContext();
          
          const totalLength = audioBuffers.reduce((acc, buffer) => 
            acc + new Int16Array(buffer).length, 0);
          
          if (totalLength === 0) {
            return resolve();
          }
          
          const combinedInt16Array = new Int16Array(totalLength);
          let offset = 0;
          
          audioBuffers.forEach(buffer => {
            const int16Data = new Int16Array(buffer);
            combinedInt16Array.set(int16Data, offset);
            offset += int16Data.length;
          });
          
          const audioBuffer = ctx.createBuffer(1, totalLength, 24000);
          const channelData = audioBuffer.getChannelData(0);
          
          // Improved smoothing
          for (let i = 0; i < totalLength; i++) {
            channelData[i] = combinedInt16Array[i] / 32768.0;
          }
          
          // Longer fade for smoother transitions
          const fadeSamples = Math.min(200, totalLength / 8);
          
          // Fade in
          for (let i = 0; i < fadeSamples; i++) {
            const factor = Math.sin((i / fadeSamples) * Math.PI / 2); // Smoother sine curve
            channelData[i] *= factor;
          }
          
          // Fade out
          for (let i = 0; i < fadeSamples; i++) {
            const factor = Math.sin((i / fadeSamples) * Math.PI / 2);
            channelData[totalLength - 1 - i] *= factor;
          }
          
          const source = ctx.createBufferSource();
          currentAudioSourceRef.current = source; // Store the current source
          const gainNode = ctx.createGain();
          gainNode.gain.value = 1.5;
          
          source.buffer = audioBuffer;
          source.connect(gainNode);
          gainNode.connect(ctx.destination);
          
          const durationMs = (audioBuffer.length / audioBuffer.sampleRate) * 1000;
          
          source.start();
          
          // Simple random movement simulation for playback level indicator
          const simulateLevel = () => {
            // Generate random number between 20-40 to simulate gentle movement
            const randomLevel = 20 + Math.floor(Math.random() * 20);
            setPlaybackAudioLevel(randomLevel);
          };
          
          // Update level every 200ms while audio is playing
          const levelInterval = setInterval(simulateLevel, 200);
          
          // Clean up interval and reset level when audio finishes
          setTimeout(() => {
            clearInterval(levelInterval);
            setPlaybackAudioLevel(0); // Reset to zero after playback
            currentAudioSourceRef.current = null; // Clear the current source
            resolve();
          }, durationMs);
          
          source.onended = () => {
            clearInterval(levelInterval);
            setPlaybackAudioLevel(0); // Also reset to zero if source ends early
            currentAudioSourceRef.current = null; // Clear the current source
            resolve();
          };
          
        } catch (error) {
          console.error('Error playing audio:', error);
          reject(error);
        }
      });
    }, [initAudioContext]);
  
    const reconnect = () => {
      // Only schedule reconnect if not already scheduled
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      
      // Use exponential backoff for reconnection attempts
      const backoffTime = Math.min(30000, RECONNECT_TIMEOUT * (reconnectAttemptsRef.current || 1));
      console.log(`Scheduling reconnect in ${backoffTime}ms`);
      
      reconnectTimeoutRef.current = setTimeout(() => {
        reconnectAttemptsRef.current = (reconnectAttemptsRef.current || 0) + 1;
        connect();
      }, backoffTime);
    };
  
    useEffect(() => {
      connect();
      return () => {
        if (wsRef.current) {
          wsRef.current.close();
        }
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        if (connectionTimeoutRef.current) {
          clearTimeout(connectionTimeoutRef.current);
        }
      };
    }, [url, playAudioChunk]);
  
    useEffect(() => {
      if (isConnected) {
        reconnectAttemptsRef.current = 0;
      }
    }, [isConnected]);
  
    const sendMessage = (message: any) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(message));
      }
    };
  
    const sendMediaChunk = (chunk: MediaChunk) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          realtime_input: {
            media_chunks: [chunk]
          }
        }));
      }
    };
  
    return (
      <WebSocketContext.Provider 
        value={{ 
          sendMessage,
          sendMediaChunk,
          lastTranscription,
          lastAudioData,
          isConnected,
          playbackAudioLevel
        }}
      >
        {children}
      </WebSocketContext.Provider>
    );
  };
  
  export const useWebSocket = () => {
    const context = useContext(WebSocketContext);
    if (!context) {
      throw new Error("useWebSocket must be used within a WebSocketProvider");
    }
    return context;
  };