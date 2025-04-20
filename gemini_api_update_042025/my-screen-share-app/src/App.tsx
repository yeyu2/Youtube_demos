// src/App.tsx
import React from "react";
import ScreenShare from "./components/ScreenShare";
import { WebSocketProvider } from "./components/WebSocketProvider";

const App: React.FC = () => {
  return (

    <WebSocketProvider url="ws://38.150.6.172:9084">
    
      <div className="container mx-auto p-4">
        <ScreenShare />
      </div>
    </WebSocketProvider>
  );
};

export default App;