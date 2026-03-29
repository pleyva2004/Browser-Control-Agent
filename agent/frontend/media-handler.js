/**
 * Audio capture (16kHz) and playback (24kHz) using AudioWorklets.
 * Adapted from the ephemeral-tokens reference example.
 */

// --- Audio Streamer (Microphone Capture) ---

class AudioStreamer {
  constructor(onAudioData) {
    this.onAudioData = onAudioData; // callback: (ArrayBuffer) => void
    this.audioContext = null;
    this.workletNode = null;
    this.sourceNode = null;
    this.stream = null;
    this.isStreaming = false;
  }

  async start() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      this.audioContext = new AudioContext({ sampleRate: 16000 });
      await this.audioContext.audioWorklet.addModule(
        "/static/audio-processors/capture.worklet.js"
      );

      this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);
      this.workletNode = new AudioWorkletNode(
        this.audioContext,
        "audio-capture-processor"
      );

      this.workletNode.port.onmessage = (event) => {
        if (event.data.type === "audio") {
          // Convert Float32 to PCM16 LE bytes
          const float32 = event.data.data;
          const pcm16 = new Int16Array(float32.length);
          for (let i = 0; i < float32.length; i++) {
            const s = Math.max(-1, Math.min(1, float32[i]));
            pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          this.onAudioData(pcm16.buffer);
        }
      };

      this.sourceNode.connect(this.workletNode);
      this.workletNode.connect(this.audioContext.destination);
      this.isStreaming = true;
      return true;
    } catch (err) {
      console.error("AudioStreamer start error:", err);
      return false;
    }
  }

  stop() {
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.sourceNode) {
      this.sourceNode.disconnect();
      this.sourceNode = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    this.isStreaming = false;
  }
}

// --- Audio Player (Gemini Response Playback) ---

class AudioPlayer {
  constructor() {
    this.audioContext = null;
    this.workletNode = null;
    this.gainNode = null;
    this.initialized = false;
  }

  async init() {
    this.audioContext = new AudioContext({ sampleRate: 24000 });
    await this.audioContext.audioWorklet.addModule(
      "/static/audio-processors/playback.worklet.js"
    );

    this.workletNode = new AudioWorkletNode(this.audioContext, "pcm-processor");
    this.gainNode = this.audioContext.createGain();
    this.gainNode.gain.value = 1.0;
    this.workletNode.connect(this.gainNode);
    this.gainNode.connect(this.audioContext.destination);
    this.initialized = true;
  }

  async play(arrayBuffer) {
    if (!this.initialized) return;

    // Resume context if suspended (browser autoplay policy)
    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }

    // Convert raw PCM16 LE bytes to Float32
    const int16 = new Int16Array(arrayBuffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) {
      float32[i] = int16[i] / 32768.0;
    }

    this.workletNode.port.postMessage(float32);
  }

  interrupt() {
    if (this.workletNode) {
      this.workletNode.port.postMessage("interrupt");
    }
  }

  setVolume(value) {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, value));
    }
  }

  destroy() {
    if (this.workletNode) this.workletNode.disconnect();
    if (this.gainNode) this.gainNode.disconnect();
    if (this.audioContext) this.audioContext.close();
    this.initialized = false;
  }
}
