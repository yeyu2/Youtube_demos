import React, { useRef, useState, useEffect } from "react";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Progress } from "./ui/progress";
import { useWebSocket } from "./WebSocketProvider";
import { Base64 } from 'js-base64';

interface ChatMessage {
  text: string;
  sender: "User" | "Gemini";
  timestamp: string;
  isComplete: boolean;
}

const ScreenShare: React.FC = () => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const audioWorkletNodeRef = useRef<AudioWorkletNode | null>(null);
  const setupInProgressRef = useRef(false);
  const [isSharing, setIsSharing] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [messages, setMessages] = useState<ChatMessage[]>([{
    text: "Screen sharing session started. I'll transcribe what I see.",
    sender: "Gemini",
    timestamp: new Date().toLocaleTimeString(),
    isComplete: true
  }]);
  const { sendMessage, sendMediaChunk, isConnected, playbackAudioLevel, lastTranscription } = useWebSocket();
  const captureIntervalRef = useRef<NodeJS.Timeout>();

  // Handle incoming transcriptions
  useEffect(() => {
    if (lastTranscription) {
      setMessages(prev => {
        const lastMessage = prev[prev.length - 1];
        
        // Check if the last message is from the same sender and is incomplete
        const shouldUpdateLast = lastMessage && 
                               lastMessage.sender === lastTranscription.sender &&
                               !lastMessage.isComplete;

        if (shouldUpdateLast) {
          // Update the last message by appending new text and updating completion status
          const updatedMessages = [...prev];
          updatedMessages[updatedMessages.length - 1] = {
            ...lastMessage,
            text: lastMessage.text + lastTranscription.text, // Append new text
            isComplete: lastTranscription.finished === true
          };
          return updatedMessages;
        }
        
        // Otherwise, add a new message entry
        const newMessage = {
          text: lastTranscription.text,
          sender: lastTranscription.sender,
          timestamp: new Date().toLocaleTimeString(),
          isComplete: lastTranscription.finished === true
        };
        return [...prev, newMessage];
      });
    }
  }, [lastTranscription]);

  const startSharing = async () => {
    if (isSharing) return;

    try {
      // Get screen stream
      const screenStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: false
      });
      
      // Get audio stream
      const audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 16000
        }
      });

      // Set up audio context and processing
      audioContextRef.current = new AudioContext({
        sampleRate: 16000,
        latencyHint: 'interactive'
      });

      const ctx = audioContextRef.current;
      await ctx.audioWorklet.addModule('/worklets/audio-processor.js');
      
      const source = ctx.createMediaStreamSource(audioStream);
      audioWorkletNodeRef.current = new AudioWorkletNode(ctx, 'audio-processor', {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        processorOptions: {
          sampleRate: 16000,
          bufferSize: 4096,
        },
        channelCount: 1,
        channelCountMode: 'explicit',
        channelInterpretation: 'speakers'
      });

      // Set up audio processing
      audioWorkletNodeRef.current.port.onmessage = (event) => {
        const { pcmData, level } = event.data;
        setAudioLevel(level);
        
        if (pcmData) {
          const base64Data = Base64.fromUint8Array(new Uint8Array(pcmData));
          sendMediaChunk({
            mime_type: "audio/pcm",
            data: base64Data
          });
        }
      };

      source.connect(audioWorkletNodeRef.current);
      audioStreamRef.current = audioStream;

      // Set up video stream and capture
      if (videoRef.current) {
        videoRef.current.srcObject = screenStream;
        
        // Start screen capture interval
        captureIntervalRef.current = setInterval(() => {
          if (videoRef.current) {
            const canvas = document.createElement('canvas');
            canvas.width = videoRef.current.videoWidth;
            canvas.height = videoRef.current.videoHeight;
            
            const ctx = canvas.getContext('2d');
            if (ctx) {
              ctx.drawImage(videoRef.current, 0, 0);
              const imageData = canvas.toDataURL('image/jpeg', 0.8).split(',')[1];
              
              sendMediaChunk({
                mime_type: "image/jpeg",
                data: imageData
              });
            }
          }
        }, 3000);
      }

      // Send initial setup message
      sendMessage({
        setup: {
          // Add any needed config options
        }
      });

      setIsSharing(true);
    } catch (err) {
      console.error('Failed to start sharing:', err);
      stopSharing();
    }
  };

  const stopSharing = () => {
    // Stop video stream
    if (videoRef.current?.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }

    // Stop audio stream
    if (audioStreamRef.current) {
      audioStreamRef.current.getTracks().forEach(track => track.stop());
      audioStreamRef.current = null;
    }

    // Stop screen capture interval
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = undefined;
    }

    // Clean up audio processing
    if (audioWorkletNodeRef.current) {
      audioWorkletNodeRef.current.disconnect();
      audioWorkletNodeRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setIsSharing(false);
    setAudioLevel(0);
  };

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-3xl">
      {/* Welcome Header */}
      <div className="text-center space-y-2">
        <h1 className="scroll-m-20 text-4xl font-extrabold tracking-tight lg:text-5xl">
          Gemini Learning Assistant with Memory
        </h1>
        <p className="text-xl text-muted-foreground">
          Share your screen and talk to me
        </p>
      </div>

      {/* Screen Preview */}
      <Card className="w-full md:w-[640px] mx-auto">
        <CardContent className="p-6">
          <div className="flex flex-col items-center space-y-4">
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="w-full aspect-video rounded-md border bg-muted"
            />
            {/* Combined Audio Level Indicator */}
            {isSharing && (
              <div className="w-full space-y-2">
                <Progress 
                  value={Math.max(audioLevel, playbackAudioLevel)} 
                  className="h-1 bg-white" 
                  indicatorClassName="bg-black" 
                />
              </div>
            )}
            {!isSharing ? (
              <Button 
                size="lg" 
                onClick={startSharing}
                disabled={!isConnected}
                variant={isConnected ? "default" : "outline"}
                className={!isConnected ? "border-red-300 text-red-700" : ""}
              >
                {isConnected ? "Start Screen Share" : "Connecting to server..."}
              </Button>
            ) : (
              <Button size="lg" variant="destructive" onClick={stopSharing}>
                Stop Sharing
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Chat History */}
      <Card className="w-full md:w-[640px] mx-auto">
        <CardHeader>
          <CardTitle>Chat History</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[400px] pr-4">
            <div className="space-y-4">
              {messages.map((message, index) => (
                <div 
                  key={index} 
                  className="flex items-start space-x-4 rounded-lg p-4 bg-muted/50"
                >
                  <div className="h-8 w-8 rounded-full flex items-center justify-center bg-primary">
                    <span className="text-xs font-medium text-primary-foreground">
                      {message.sender === "Gemini" ? "AI" : "You"}
                    </span>
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm leading-loose">{message.text}</p>
                    <p className="text-xs text-muted-foreground">
                      {message.timestamp}
                      {!message.isComplete && " (typing...)"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
};

export default ScreenShare;