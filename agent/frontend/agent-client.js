/**
 * WebSocket client for communicating with the FastAPI backend.
 * Routes incoming binary data: IMG:-prefixed → screenshot, else → audio.
 */

const IMG_PREFIX = [0x49, 0x4d, 0x47, 0x3a]; // "IMG:"

class AgentClient {
  constructor({ onAudio, onScreenshot, onEvent, onOpen, onClose, onError }) {
    this.websocket = null;
    this.onAudio = onAudio;
    this.onScreenshot = onScreenshot;
    this.onEvent = onEvent;
    this.onOpen = onOpen;
    this.onClose = onClose;
    this.onError = onError;
  }

  connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.websocket = new WebSocket(
      `${protocol}//${window.location.host}/ws`
    );
    this.websocket.binaryType = "arraybuffer";

    this.websocket.onopen = () => {
      if (this.onOpen) this.onOpen();
    };

    this.websocket.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const bytes = new Uint8Array(event.data);
        // Check for "IMG:" prefix
        if (
          bytes.length > 4 &&
          bytes[0] === IMG_PREFIX[0] &&
          bytes[1] === IMG_PREFIX[1] &&
          bytes[2] === IMG_PREFIX[2] &&
          bytes[3] === IMG_PREFIX[3]
        ) {
          if (this.onScreenshot) this.onScreenshot(bytes.slice(4));
        } else {
          if (this.onAudio) this.onAudio(event.data);
        }
      } else {
        try {
          const msg = JSON.parse(event.data);
          if (this.onEvent) this.onEvent(msg);
        } catch (e) {
          console.error("Failed to parse event:", e);
        }
      }
    };

    this.websocket.onclose = () => {
      if (this.onClose) this.onClose();
    };

    this.websocket.onerror = (err) => {
      if (this.onError) this.onError(err);
    };
  }

  disconnect() {
    if (this.websocket) {
      this.websocket.close();
      this.websocket = null;
    }
  }

  isConnected() {
    return this.websocket && this.websocket.readyState === WebSocket.OPEN;
  }

  sendAudio(pcmArrayBuffer) {
    if (this.isConnected()) {
      this.websocket.send(pcmArrayBuffer);
    }
  }

  sendText(text) {
    if (this.isConnected()) {
      this.websocket.send(JSON.stringify({ type: "text", text }));
    }
  }

  sendNavigate(url) {
    if (this.isConnected()) {
      this.websocket.send(JSON.stringify({ type: "navigate", url }));
    }
  }
}
