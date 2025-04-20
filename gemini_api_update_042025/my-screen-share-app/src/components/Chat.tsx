import React, { useState, useEffect, useRef } from "react";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Avatar } from "./ui/avatar";
import { AvatarImage } from "@radix-ui/react-avatar";
import { useWebSocket } from "./WebSocketProvider";
import AudioPlayer from "./AudioPlayer";

interface Message {
  text: string;
  sender: "User" | "Gemini";
  timestamp: number;
  isComplete: boolean;
  type: "text" | "audio";
  audioData?: string;
}

const Chat: React.FC = () => {
  const [inputText, setInputText] = useState("");
  const { sendMessage, lastTranscription, lastAudioData } = useWebSocket();
  const [messages, setMessages] = useState<Message[]>([]);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setInputText(event.target.value);
  };

  const handleSendMessage = () => {
    if (inputText.trim() !== "") {
      sendMessage({ type: "text", data: { text: inputText } });
      setInputText("");
    }
  };

  // Handle transcription updates
  useEffect(() => {
    if (lastTranscription) {
      setMessages(prev => {
        const lastMessage = prev.findLast(m => m.type === 'text'); // Find the last text message
        
        // Check if the last text message is from the same sender and is incomplete
        const shouldUpdateLast = lastMessage && 
                               lastMessage.sender === lastTranscription.sender &&
                               !lastMessage.isComplete;

        if (shouldUpdateLast) {
          // Update the last message by appending new text and updating completion status
          const updatedMessages = prev.map(msg => 
            msg === lastMessage 
              ? { ...lastMessage, text: lastMessage.text + lastTranscription.text, isComplete: lastTranscription.finished === true } // Append
              : msg
          );
          return updatedMessages;
        }
        
        // Otherwise, add a new message entry
        const newMessage = {
          text: lastTranscription.text,
          sender: lastTranscription.sender,
          timestamp: Date.now(),
          isComplete: lastTranscription.finished === true,
          type: "text" as const // Explicitly type as "text"
        };
        return [...prev, newMessage];
      });
    }
  }, [lastTranscription]);

  // Handle audio data
  useEffect(() => {
    if (lastAudioData) {
      setMessages(prev => [...prev, {
        text: "",
        sender: "Gemini",
        timestamp: Date.now(),
        isComplete: true,
        type: "audio",
        audioData: lastAudioData
      }]);
    }
  }, [lastAudioData]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col h-full">
      <ScrollArea className="flex-1 p-4 space-y-4">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${
              message.sender === "Gemini"
                ? "justify-start"
                : "justify-end"
            } items-start space-x-2`}
          >
            {message.sender === "Gemini" && (
              <Avatar>
                <AvatarImage src="/placeholder-avatar.jpg" />
              </Avatar>
            )}
            <div
              className={`p-3 rounded-lg max-w-[70%] ${
                message.sender === "Gemini"
                  ? "bg-gray-100 text-gray-800"
                  : "bg-blue-500 text-white"
              }`}
            >
              {message.type === "text" && (
                <>
                  <p>{message.text}</p>
                  {!message.isComplete && (
                    <span className="text-xs text-gray-500">(typing...)</span>
                  )}
                </>
              )}
              {message.type === "audio" && message.audioData && (
                <AudioPlayer base64Audio={message.audioData} />
              )}
            </div>
            {message.sender !== "Gemini" && (
              <Avatar>
                <AvatarImage src="/user-avatar.jpg" />
              </Avatar>
            )}
          </div>
        ))}
        <div ref={chatEndRef} />
      </ScrollArea>
      
      <div className="p-4 border-t flex space-x-2">
        <Input
          value={inputText}
          onChange={handleInputChange}
          onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
          placeholder="Type a message..."
        />
        <Button onClick={handleSendMessage}>Send</Button>
      </div>
    </div>
  );
};

export default Chat;