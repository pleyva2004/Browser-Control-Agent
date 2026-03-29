/**
 * Main application logic.
 * Wires AgentClient, AudioStreamer, and AudioPlayer together with the UI.
 */

// --- State ---
let audioStreamer = null;
let audioPlayer = null;
let connected = false;

// Accumulate streaming transcriptions
let currentUserMsg = null;
let currentGeminiMsg = null;

// --- DOM refs ---
const statusEl = document.getElementById("status");
const connectBtn = document.getElementById("connectBtn");
const micBtn = document.getElementById("micBtn");
const volumeSlider = document.getElementById("volumeSlider");
const browserPreview = document.getElementById("browserPreview");
const previewPlaceholder = document.getElementById("previewPlaceholder");
const chatLog = document.getElementById("chatLog");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const urlInput = document.getElementById("urlInput");
const urlGoBtn = document.getElementById("urlGoBtn");

// --- Screenshot display ---
let prevBlobUrl = null;

function displayScreenshot(jpegBytes) {
  const blob = new Blob([jpegBytes], { type: "image/jpeg" });
  const url = URL.createObjectURL(blob);
  browserPreview.src = url;
  browserPreview.classList.add("visible");
  previewPlaceholder.style.display = "none";
  if (prevBlobUrl) URL.revokeObjectURL(prevBlobUrl);
  prevBlobUrl = url;
}

// --- Chat messages ---
function addMessage(type, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${type}`;
  div.textContent = text;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
  return div;
}

function addToolMessage(name, args) {
  const div = document.createElement("div");
  div.className = "chat-msg tool";

  const nameSpan = document.createElement("span");
  nameSpan.className = "tool-name";
  nameSpan.textContent = name;
  div.appendChild(nameSpan);

  if (args && Object.keys(args).length > 0) {
    const argsDiv = document.createElement("div");
    argsDiv.className = "tool-args";
    argsDiv.textContent = JSON.stringify(args);
    div.appendChild(argsDiv);
  }

  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

// --- Event handling ---
function handleEvent(msg) {
  switch (msg.type) {
    case "user":
      // Streaming user transcription — accumulate into one message
      if (!currentUserMsg) {
        currentUserMsg = addMessage("user", msg.text);
      } else {
        currentUserMsg.textContent = msg.text;
      }
      break;

    case "gemini":
      // Streaming gemini transcription
      if (!currentGeminiMsg) {
        currentGeminiMsg = addMessage("gemini", msg.text);
      } else {
        currentGeminiMsg.textContent = msg.text;
      }
      break;

    case "tool_call":
      addToolMessage(msg.name, msg.args);
      break;

    case "turn_complete":
      // Reset accumulators for next turn
      currentUserMsg = null;
      currentGeminiMsg = null;
      break;

    case "interrupted":
      if (audioPlayer) audioPlayer.interrupt();
      currentGeminiMsg = null;
      break;

    case "nav_result":
      if (msg.status === "ok" && msg.url) {
        urlInput.value = msg.url;
      } else if (msg.status === "error") {
        addMessage("system", "Navigation failed: " + msg.message);
      }
      break;

    case "error":
      addMessage("system", "Error: " + msg.error);
      break;
  }
}

// --- Client setup ---
const client = new AgentClient({
  onAudio: (arrayBuffer) => {
    if (audioPlayer) audioPlayer.play(arrayBuffer);
  },
  onScreenshot: (jpegBytes) => {
    displayScreenshot(jpegBytes);
  },
  onEvent: (msg) => {
    handleEvent(msg);
  },
  onOpen: () => {
    connected = true;
    setUIState("connected");
    addMessage("info", "Connected to agent");
  },
  onClose: () => {
    connected = false;
    setUIState("disconnected");
    addMessage("info", "Disconnected");
    if (audioStreamer && audioStreamer.isStreaming) {
      audioStreamer.stop();
    }
    if (audioPlayer) {
      audioPlayer.destroy();
      audioPlayer = null;
    }
  },
  onError: () => {
    addMessage("system", "WebSocket error");
  },
});

// --- UI state management ---
function setUIState(state) {
  statusEl.className = `status ${state}`;
  statusEl.textContent =
    state === "connected"
      ? "Connected"
      : state === "connecting"
        ? "Connecting..."
        : "Disconnected";

  const isConnected = state === "connected";
  connectBtn.textContent = isConnected ? "Disconnect" : "Connect";
  connectBtn.disabled = state === "connecting";
  micBtn.disabled = !isConnected;
  textInput.disabled = !isConnected;
  sendBtn.disabled = !isConnected;
  urlInput.disabled = !isConnected;
  urlGoBtn.disabled = !isConnected;

  if (!isConnected) {
    micBtn.textContent = "Mic Off";
    micBtn.classList.remove("active");
    currentUserMsg = null;
    currentGeminiMsg = null;
  }
}

// --- Event listeners ---
connectBtn.addEventListener("click", async () => {
  if (connected) {
    client.disconnect();
    if (audioStreamer && audioStreamer.isStreaming) audioStreamer.stop();
    if (audioPlayer) {
      audioPlayer.destroy();
      audioPlayer = null;
    }
    return;
  }

  setUIState("connecting");
  audioPlayer = new AudioPlayer();
  await audioPlayer.init();
  volumeSlider.dispatchEvent(new Event("input"));
  client.connect();
});

micBtn.addEventListener("click", async () => {
  if (audioStreamer && audioStreamer.isStreaming) {
    audioStreamer.stop();
    micBtn.textContent = "Mic Off";
    micBtn.classList.remove("active");
  } else {
    audioStreamer = new AudioStreamer((pcmBuffer) => {
      client.sendAudio(pcmBuffer);
    });
    const ok = await audioStreamer.start();
    if (ok) {
      micBtn.textContent = "Mic On";
      micBtn.classList.add("active");
    } else {
      addMessage("system", "Could not access microphone");
    }
  }
});

volumeSlider.addEventListener("input", () => {
  if (audioPlayer) {
    audioPlayer.setVolume(volumeSlider.value / 100);
  }
});

function sendTextMessage() {
  const text = textInput.value.trim();
  if (!text) return;
  client.sendText(text);
  addMessage("user", text);
  textInput.value = "";
}

sendBtn.addEventListener("click", sendTextMessage);
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendTextMessage();
});

// --- URL bar ---
function navigateToUrl() {
  let url = urlInput.value.trim();
  if (!url) return;
  if (!/^https?:\/\//i.test(url)) url = "https://" + url;
  urlInput.value = url;
  client.sendNavigate(url);
}

urlGoBtn.addEventListener("click", navigateToUrl);
urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") navigateToUrl();
});

// --- Init ---
setUIState("disconnected");
