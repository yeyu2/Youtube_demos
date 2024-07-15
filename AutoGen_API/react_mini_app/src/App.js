import React, { useState, useEffect, useRef } from 'react';
import './App.css'

function App() {
  const [userInput, setUserInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [chatStatus, setChatStatus] = useState('ended'); 

  const messagesEndRef = useRef(null);

  // Initial chat request structure
  const initialChatRequest = {
    "message": "Write a quick manuscript", 
    "agents_info": [
        {
            "name": "Personal_Assistant",
            "type": "AssistantAgent",
            "llm": {
                "model": "gpt-4o"
            },
            "system_message": "You are a personal assistant who can answer questions.",
            "description": "This is a personal assistant who can answer questions."
        }
    ],
    "task_info": {
        "id": 0,
        "name": "Personal Assistant",
        "description": "This is a powerful personal assistant.",
        "maxMessages": 5,
        "speakSelMode": "auto"
    }
  };

  // Function to send message/start chat
  const handleSend = async () => {
    let apiEndpoint, requestBody;

    if (chatStatus === 'Chat ongoing' || chatStatus === 'inputting') {
      // Send message request
      apiEndpoint = 'http://yeyu.life:5008/api/send_message';
      requestBody = { message: userInput };
    } else {
      // Start chat request
      apiEndpoint = 'http://yeyu.life:5008/api/start_chat';
      requestBody = { ...initialChatRequest, message: userInput }; 
    }

    try {
      const response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });
      
      if (!response.ok) {
        throw new Error('Failed to send request');
      }

      setUserInput(''); // Clear input field
    } catch (error) {
      console.error('Error sending request:', error);
    }
  };

  // Function to fetch messages from the backend
  const fetchMessages = async () => {
    try {
      const response = await fetch('http://yeyu.life:5008/api/get_message');
      if (!response.ok) {
        throw new Error('Failed to fetch messages');
      }

      const data = await response.json();
      if (data.message) {
        setMessages([...messages, data.message]);
        
      }
      setChatStatus(data.chat_status); 
    } catch (error) {
      console.error('Error fetching messages:', error);
    }
  };

  // Use useEffect to poll for new messages
  useEffect(() => {
    const intervalId = setInterval(fetchMessages, 1000); 
    return () => clearInterval(intervalId);
  }, [messages]); 

  // Scroll to bottom when new messages are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="App">

      <div className="chat-window">
        <div className="messages">
          {messages.map((msg, index) => (
            <div key={index} className={`message ${msg.user === 'User_Proxy' ? 'user' : 'agent'}`}>
              <strong>{msg.user}:</strong> {msg.message}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        <div className="input-area">
          <input
            type="text"
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            placeholder="Type your message..."
          />
          <button onClick={handleSend}>Send</button> 
        </div>
        <p className="chat-status">Chat Status: {chatStatus}</p>
      </div>
    </div>
  );
}

export default App;