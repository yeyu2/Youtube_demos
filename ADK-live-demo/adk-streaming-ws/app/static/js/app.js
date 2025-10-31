/**
* Copyright 2025 Google LLC
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*     http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/

/**
 * app.js: JS code for the adk-streaming sample app.
 */

/**
 * WebSocket handling
 */

// Connect the server with a WebSocket connection
const sessionId = Math.random().toString().substring(10);
const ws_url =
  "ws://" + window.location.host + "/ws/" + sessionId;
let websocket = null;
let is_audio = false;

// Get DOM elements
const messagesDiv = document.getElementById("messages");
const statusBar = document.getElementById("statusBar");

// Debug: Check if elements are found
console.log("[INIT] messagesDiv:", messagesDiv);
console.log("[INIT] statusBar:", statusBar);

let currentMessageId = null;
let currentInputTranscriptId = null;
let currentOutputTranscriptId = null;
let currentTurnDiv = null;
let turnCounter = 0;
let reconnectImmediately = false;
let detailPending = false; // after turn_complete, waiting for detail JSON
let nextTurnShouldCreateNewContainer = false; // set after detail JSON handled

// Status indicator helpers
function showStatus(message, type) {
  console.log("[STATUS] Showing:", message, "Type:", type);
  if (!statusBar) {
    console.error("[STATUS] statusBar element not found!");
    return;
  }
  statusBar.textContent = message;
  statusBar.className = "status-bar " + type;
  console.log("[STATUS] Applied class:", statusBar.className);
}

function hideStatus() {
  console.log("[STATUS] Hiding status");
  if (!statusBar) return;
  statusBar.className = "status-bar ready";
  statusBar.textContent = "Ready";
}

function createTurnContainer() {
  turnCounter += 1;
  const turnId = "turn-" + Date.now();
  const turnDiv = document.createElement("div");
  turnDiv.className = "turn";
  turnDiv.dataset.turnId = turnId;

  const header = document.createElement("div");
  header.className = "turn-header";
  header.textContent = "Conversation " + turnCounter;
  turnDiv.appendChild(header);

  const content = document.createElement("div");
  content.className = "turn-content";
  turnDiv.appendChild(content);

  const transcripts = document.createElement("div");
  transcripts.className = "transcripts";
  content.appendChild(transcripts);

  const analysisPanel = document.createElement("div");
  analysisPanel.className = "analysis-panel";
  content.appendChild(analysisPanel);

  messagesDiv.appendChild(turnDiv);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  return turnDiv;
}

function showLoadingIndicator() {
  if (!currentTurnDiv) return;
  const analysisPanel = currentTurnDiv.querySelector(".analysis-panel");
  if (!analysisPanel) return;
  
  // Remove existing loading indicator if any
  const existing = analysisPanel.querySelector(".loading-indicator");
  if (existing) return;
  
  const loader = document.createElement("div");
  loader.className = "loading-indicator";
  loader.innerHTML = '<div class="loading-spinner"></div><span>Generating trend analysis...</span>';
  analysisPanel.appendChild(loader);
  
  showStatus("🔄 Analyzing trend data...", "processing");
}

function hideLoadingIndicator() {
  if (!currentTurnDiv) return;
  const analysisPanel = currentTurnDiv.querySelector(".analysis-panel");
  if (!analysisPanel) return;
  
  const loader = analysisPanel.querySelector(".loading-indicator");
  if (loader) {
    loader.remove();
  }
}

// WebSocket handlers
function connectWebsocket() {
  // Connect websocket
  websocket = new WebSocket(ws_url + "?is_audio=" + is_audio);

  // Handle connection open
  websocket.onopen = function () {
    // Connection opened messages
    console.log("WebSocket connection opened.");
  };

  // Handle incoming messages
  websocket.onmessage = function (event) {
    // Parse the incoming message
    const message_from_server = JSON.parse(event.data);
    console.log("[AGENT TO CLIENT] ", message_from_server);

    // Check if the turn is complete
    // if turn complete, reset message IDs for new turn
    if (
      message_from_server.turn_complete &&
      message_from_server.turn_complete == true
    ) {
      currentMessageId = null;
      currentInputTranscriptId = null;
      currentOutputTranscriptId = null;
      // Keep currentTurnDiv for detail analysis; mark pending
      detailPending = true;
      // Show loading indicator for trend analysis
      showLoadingIndicator();
      return;
    }

    // Check for interrupt message
    if (
      message_from_server.interrupted &&
      message_from_server.interrupted === true
    ) {
      // Stop audio playback if it's playing
      if (audioPlayerNode) {
        audioPlayerNode.port.postMessage({ command: "endOfAudio" });
      }
      return;
    }

    // If it's audio, play it
    if (message_from_server.mime_type == "audio/pcm" && audioPlayerNode) {
      audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));
    }

    // If it's detailed analysis with chart data (JSON)
    if (message_from_server.mime_type == "application/json" && message_from_server.is_detailed_analysis) {
      try {
        // Strip markdown code blocks if present (```json ... ```)
        let jsonString = message_from_server.data.trim();
        if (jsonString.startsWith('```')) {
          // Remove ```json from start and ``` from end
          jsonString = jsonString.replace(/^```(?:json)?\s*\n?/, '').replace(/\n?```\s*$/, '');
        }
        
        const chartData = JSON.parse(jsonString);
        
        // Check if this is a skip marker
        if (chartData.skip) {
          console.log("[DETAIL AGENT] Skipping detail analysis - simple question already answered");
          return;
        }
        
        // Ensure a turn container exists (detail should attach to the last turn)
        if (!currentTurnDiv) {
          currentTurnDiv = createTurnContainer();
        }

        // Create or update detailed analysis section within this turn
        const analysisPanel = currentTurnDiv.querySelector(".analysis-panel");
        let analysisDiv = analysisPanel.querySelector(".detailed-analysis");
        if (!analysisDiv) {
          analysisDiv = document.createElement("div");
          analysisDiv.className = "detailed-analysis";

          // Add header
          const header = document.createElement("div");
          header.className = "analysis-header";
          header.textContent = "📊 " + (chartData.title || "Trend Analysis");
          analysisDiv.appendChild(header);

          // Add content div
          const contentEl = document.createElement("div");
          contentEl.className = "analysis-content";
          analysisDiv.appendChild(contentEl);

          analysisPanel.appendChild(analysisDiv);
        }

        const content = analysisDiv.querySelector(".analysis-content");
        
        // Add summary if provided
        if (chartData.summary) {
          const summaryP = document.createElement("p");
          summaryP.innerHTML = "<strong>Summary:</strong> " + chartData.summary;
          content.appendChild(summaryP);
        }
        
        // Create chart if data provided
        if (chartData.labels && chartData.values) {
          const chartContainer = document.createElement("div");
          chartContainer.className = "chart-container";
          
          const canvas = document.createElement("canvas");
          const chartId = "chart-" + Date.now();
          canvas.id = chartId;
          chartContainer.appendChild(canvas);
          content.appendChild(chartContainer);
          
          // Create Chart.js chart
          new Chart(canvas, {
            type: 'line',
            data: {
              labels: chartData.labels,
              datasets: [{
                label: chartData.data_label || 'Value',
                data: chartData.values,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.3,
                fill: true
              }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: true,
              plugins: {
                title: {
                  display: true,
                  text: chartData.chart_title || chartData.title
                },
                legend: {
                  display: false
                }
              },
              scales: {
                y: {
                  beginAtZero: false,
                  title: {
                    display: true,
                    text: chartData.y_label || 'Value'
                  }
                }
              }
            }
          });
        }
        
        // Add insights if provided
        if (chartData.insights && chartData.insights.length > 0) {
          const insightsDiv = document.createElement("div");
          insightsDiv.innerHTML = "<strong>Key Insights:</strong>";
          const ul = document.createElement("ul");
          chartData.insights.forEach(insight => {
            const li = document.createElement("li");
            li.textContent = insight;
            ul.appendChild(li);
          });
          insightsDiv.appendChild(ul);
          content.appendChild(insightsDiv);
        }
        
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        // Detail handled; next turn should start a new container
        detailPending = false;
        nextTurnShouldCreateNewContainer = true;
        // Hide loading indicator
        hideLoadingIndicator();
        hideStatus();
      } catch (error) {
        console.error("[CHART] Error parsing chart data:", error);
      }
      return;
    }
    
    // If it's a text, print it (including transcripts)
    if (message_from_server.mime_type == "text/plain") {
      // Determine message type
      let messageType = "agent"; // default
      let messageClass = "agent-message";
      let label = "🤖 Agent:";
      let messageId = currentMessageId;
      
      // If the previous turn completed and detail was handled, start a new container
      if (nextTurnShouldCreateNewContainer) {
        currentTurnDiv = null;
        nextTurnShouldCreateNewContainer = false;
      }

      // Ensure a turn container exists for transcripts
      if (!currentTurnDiv) {
        currentTurnDiv = createTurnContainer();
      }
      const transcriptsContainer = currentTurnDiv.querySelector(".transcripts");

      if (message_from_server.is_input_transcript) {
        messageType = "input_transcript";
        messageClass = "input-transcript-message";
        label = "🎙️ You said:";
        // Use stable ID for the current input transcript session
        if (!currentInputTranscriptId) {
          currentInputTranscriptId = "input_transcript_" + Math.random().toString(36).substring(7);
        }
        messageId = currentInputTranscriptId;
      } else if (message_from_server.is_output_transcript) {
        messageType = "output_transcript";
        messageClass = "output-transcript-message";
        label = "🎤 Agent said:";
        // Use stable ID for the current output transcript session
        if (!currentOutputTranscriptId) {
          currentOutputTranscriptId = "output_transcript_" + Math.random().toString(36).substring(7);
        }
        messageId = currentOutputTranscriptId;
      }
      
      // For transcripts, create or update the specific transcript message
      if (messageType !== "agent") {
        let message = document.getElementById(messageId);
        
        // Create new transcript message if it doesn't exist
        if (!message) {
          message = document.createElement("div");
          message.id = messageId;
          message.className = messageClass;
          
          // Add a label for message type
          const labelElement = document.createElement("span");
          labelElement.className = "message-label";
          labelElement.textContent = label;
          message.appendChild(labelElement);
          
          // Add the text content
          const textContent = document.createElement("span");
          textContent.className = "message-text";
          message.appendChild(textContent);
          
          // Append the message element to the transcripts panel
          transcriptsContainer.appendChild(message);
        }
        
        // Append text to transcript (transcripts can be streamed in chunks)
        const textContent = message.querySelector(".message-text");
        textContent.textContent += message_from_server.data;
        
      } else {
        // For regular agent messages
        if (currentMessageId == null) {
          currentMessageId = Math.random().toString(36).substring(7);
          const message = document.createElement("div");
          message.id = currentMessageId;
          message.className = messageClass;
          
          // Add a label for message type
          const labelElement = document.createElement("span");
          labelElement.className = "message-label";
          labelElement.textContent = label;
          message.appendChild(labelElement);
          
          // Add the text content
          const textContent = document.createElement("span");
          textContent.className = "message-text";
          message.appendChild(textContent);
          
          // Append the message element to the transcripts panel
          transcriptsContainer.appendChild(message);
        }
        
        // Add message text to the existing message element
        const message = document.getElementById(currentMessageId);
        const textContent = message.querySelector(".message-text");
        textContent.textContent += message_from_server.data;
      }

      // Scroll down to the bottom of the messagesDiv
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  };

  // Handle connection close
  websocket.onclose = function () {
    console.log("WebSocket connection closed.");
    if (reconnectImmediately) {
      reconnectImmediately = false;
      connectWebsocket();
      return;
    }
    setTimeout(function () {
      console.log("Reconnecting...");
      connectWebsocket();
    }, 5000);
  };

  websocket.onerror = function (e) {
    console.log("WebSocket error: ", e);
  };
}
// Do not auto-connect; wait for microphone start

// Add submit handler to the form
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value;
    if (message) {
      const p = document.createElement("div");
      p.className = "user-message";
      p.innerHTML = '<span class="message-label">👤 You:</span> <span class="message-text">' + message + '</span>';
      messagesDiv.appendChild(p);
      messageInput.value = "";
      sendMessage({
        mime_type: "text/plain",
        data: message,
      });
      console.log("[CLIENT TO AGENT] " + message);
    }
    return false;
  };
}

// Send a message to the server as a JSON string
function sendMessage(message) {
  if (websocket && websocket.readyState == WebSocket.OPEN) {
    const messageJson = JSON.stringify(message);
    websocket.send(messageJson);
  }
}

// Decode Base64 data to Array
function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

// Simple markdown renderer with mermaid support
function renderMarkdownWithMermaid(element, markdownText) {
  console.log('[MARKDOWN] Input text length:', markdownText.length);
  console.log('[MARKDOWN] First 500 chars:', markdownText.substring(0, 500));
  
  // Simple markdown rendering (basic support)
  let html = markdownText;
  
  // Extract mermaid code blocks before processing
  const mermaidBlocks = [];
  // Match ```mermaid with optional whitespace and newlines
  html = html.replace(/```mermaid\s*([\s\S]*?)```/g, (match, code) => {
    console.log('[MARKDOWN] Found mermaid block:', code);
    const placeholder = `__MERMAID_${mermaidBlocks.length}__`;
    mermaidBlocks.push(code.trim());
    return placeholder;
  });
  
  console.log('[MARKDOWN] Found', mermaidBlocks.length, 'mermaid blocks');
  
  // Basic markdown rendering
  // Headers
  html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');
  
  // Bold
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  
  // Bullet points
  html = html.replace(/^[•\-\*] (.*$)/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
  
  // Paragraphs
  html = html.split('\n\n').map(p => {
    if (!p.trim().startsWith('<') && p.trim()) {
      return '<p>' + p + '</p>';
    }
    return p;
  }).join('\n');
  
  // Restore mermaid blocks
  mermaidBlocks.forEach((code, index) => {
    const mermaidId = `mermaid-${Date.now()}-${index}`;
    const mermaidDiv = `<div class="mermaid" id="${mermaidId}">${code}</div>`;
    html = html.replace(`__MERMAID_${index}__`, mermaidDiv);
    console.log(`[MERMAID] Block ${index}:`, code); // Debug log
  });
  
  // Set the HTML
  element.innerHTML = html;
  
  // Render mermaid diagrams
  if (window.mermaid && mermaidBlocks.length > 0) {
    console.log(`[MERMAID] Rendering ${mermaidBlocks.length} diagrams`);
    setTimeout(() => {
      try {
        window.mermaid.run({
          querySelector: '.mermaid'
        });
        console.log('[MERMAID] Rendering completed');
      } catch (error) {
        console.error('[MERMAID] Rendering error:', error);
      }
    }, 100);
  }
}

/**
 * Audio handling
 */

let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;

// Audio buffering for 0.2s intervals
let audioBuffer = [];
let bufferTimer = null;

// Import the audio worklets
import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

// Start audio
function startAudio() {
  // Start audio output
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });
  // Start audio input
  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
    }
  );
}

// Start the audio only when the user clicked the button
// (due to the gesture requirement for the Web Audio API)
const startAudioButton = document.getElementById("startAudioButton");
const stopAudioButton = document.getElementById("stopAudioButton");

console.log("[INIT] startAudioButton:", startAudioButton);
console.log("[INIT] stopAudioButton:", stopAudioButton);

startAudioButton.addEventListener("click", () => {
  console.log("[BUTTON] Start Mic clicked!");
  console.log("[BUTTON] About to call showStatus...");
  
  try {
    showStatus("🎙️ Recording... Speak now", "recording");
    console.log("[BUTTON] showStatus called successfully");
  } catch (error) {
    console.error("[BUTTON] Error calling showStatus:", error);
  }
  
  startAudioButton.disabled = true;
  if (stopAudioButton) stopAudioButton.disabled = false;
  startAudio();
  is_audio = true;
  
  if (websocket && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)) {
    reconnectImmediately = true;
    try { websocket.close(); } catch (e) {}
  } else {
    connectWebsocket(); // connect with audio mode
  }
});

if (stopAudioButton) {
  stopAudioButton.addEventListener("click", () => {
    if (stopAudioButton) stopAudioButton.disabled = true;
    stopAudioRecording();
    if (micStream) {
      try { micStream.getTracks().forEach(t => t.stop()); } catch (e) {}
      micStream = null;
    }
    if (audioRecorderContext) {
      try { audioRecorderContext.close(); } catch (e) {}
      audioRecorderContext = null;
    }
    if (audioRecorderNode) {
      try { audioRecorderNode.port.postMessage({ command: "stop" }); } catch (e) {}
      audioRecorderNode = null;
    }
    // keep websocket alive; user can restart mic without page reload
    if (startAudioButton) startAudioButton.disabled = false;
    hideStatus();
  });
}

// Audio recorder handler
function audioRecorderHandler(pcmData) {
  // Add audio data to buffer
  audioBuffer.push(new Uint8Array(pcmData));
  
  // Start timer if not already running
  if (!bufferTimer) {
    bufferTimer = setInterval(sendBufferedAudio, 200); // 0.2 seconds
  }
}

// Send buffered audio data every 0.2 seconds
function sendBufferedAudio() {
  if (audioBuffer.length === 0) {
    return;
  }
  
  // Calculate total length
  let totalLength = 0;
  for (const chunk of audioBuffer) {
    totalLength += chunk.length;
  }
  
  // Combine all chunks into a single buffer
  const combinedBuffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of audioBuffer) {
    combinedBuffer.set(chunk, offset);
    offset += chunk.length;
  }
  
  // Send the combined audio data
  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(combinedBuffer.buffer),
  });
  console.log("[CLIENT TO AGENT] sent %s bytes", combinedBuffer.byteLength);
  
  // Clear the buffer
  audioBuffer = [];
}

// Stop audio recording and cleanup
function stopAudioRecording() {
  if (bufferTimer) {
    clearInterval(bufferTimer);
    bufferTimer = null;
  }
  
  // Send any remaining buffered audio
  if (audioBuffer.length > 0) {
    sendBufferedAudio();
  }
}

// Encode an array buffer with Base64
function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}
