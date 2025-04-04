import React, { useState, useEffect, useRef } from "react";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import { Avatar } from "./ui/avatar";
import { AvatarImage } from "@radix-ui/react-avatar";
import { useWebSocket } from "./WebSocketProvider";
import AudioPlayer from "./AudioPlayer";

interface Message {
  type: string;
  data: any;
  timestamp?: number;
}

const Chat: React.FC = () => {
  const [inputText, setInputText] = useState("");
  const { sendMessage, lastMessage } = useWebSocket();
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

  useEffect(() => {
    if (lastMessage) {
      setMessages(prev => [...prev, {
        ...lastMessage,
        timestamp: Date.now()
      }]);
    }
  }, [lastMessage]);

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
              message.data.sender === "LLM"
                ? "justify-start"
                : "justify-end"
            } items-start space-x-2`}
          >
            {message.data.sender === "LLM" && (
              <Avatar>
                <AvatarImage src="/placeholder-avatar.jpg" />
              </Avatar>
            )}
            <div
              className={`p-3 rounded-lg max-w-[70%] ${
                message.data.sender === "LLM"
                  ? "bg-gray-100 text-gray-800"
                  : "bg-blue-500 text-white"
              }`}
            >
              {message.type === "text" && message.data.text}
              {message.type === "audio" && (
                <AudioPlayer base64Audio={message.data.audio} />
              )}
            </div>
            {message.data.sender !== "LLM" && (
              <Avatar>
                <AvatarImage src="/user-avatar.jpg" />
              </Avatar>
            )}
          </div>
        ))}
        <div ref={chatEndRef} />
      </ScrollArea>
      
    </div>
  );
};

export default Chat;