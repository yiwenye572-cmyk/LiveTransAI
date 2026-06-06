(function () {
  const STORAGE_KEY = "livetransai-tts-enabled";
  const MAX_QUEUE = 10;

  function decodeBase64(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }

  class AstAudioPlayer {
    constructor() {
      this.supported = typeof Audio !== "undefined";
      this.enabled = localStorage.getItem(STORAGE_KEY) !== "0";
      this.available = false;
      this.mimeType = "audio/ogg";
      this.buffers = new Map();
      this.playQueue = [];
      this.playing = false;
      this.currentAudio = null;
      this.currentObjectUrl = null;
    }

    setConfig(payload) {
      this.available = true;
      const format = payload.format || "ogg_opus";
      this.mimeType = format === "ogg_opus" ? "audio/ogg" : "audio/ogg";
    }

    setEnabled(on) {
      this.enabled = Boolean(on);
      localStorage.setItem(STORAGE_KEY, this.enabled ? "1" : "0");
      if (!this.enabled) {
        this.stop();
      }
      return this.enabled;
    }

    toggle() {
      return this.setEnabled(!this.enabled);
    }

    isEnabled() {
      return this.enabled;
    }

    isAvailable() {
      return this.available;
    }

    onStart(payload) {
      this.buffers.set(payload.sequence, []);
    }

    onAudio(payload) {
      if (!payload.data) {
        return;
      }
      if (!this.buffers.has(payload.sequence)) {
        this.buffers.set(payload.sequence, []);
      }
      this.buffers.get(payload.sequence).push(decodeBase64(payload.data));
    }

    onEnd(payload) {
      const chunks = this.buffers.get(payload.sequence) || [];
      this.buffers.delete(payload.sequence);
      if (!this.enabled || !this.available || chunks.length === 0) {
        return;
      }

      const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
      const merged = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.length;
      }

      this.playQueue.push(merged);
      while (this.playQueue.length > MAX_QUEUE) {
        this.playQueue.shift();
      }
      this.pump();
    }

    stop() {
      if (this.currentAudio) {
        this.currentAudio.pause();
        this.currentAudio = null;
      }
      if (this.currentObjectUrl) {
        URL.revokeObjectURL(this.currentObjectUrl);
        this.currentObjectUrl = null;
      }
      this.playQueue = [];
      this.buffers.clear();
      this.playing = false;
    }

    pump() {
      if (!this.supported || this.playing || this.playQueue.length === 0) {
        return;
      }

      const data = this.playQueue.shift();
      this.playing = true;

      const blob = new Blob([data], { type: this.mimeType });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      this.currentAudio = audio;
      this.currentObjectUrl = url;

      const finish = () => {
        if (this.currentObjectUrl === url) {
          URL.revokeObjectURL(url);
          this.currentObjectUrl = null;
        }
        this.currentAudio = null;
        this.playing = false;
        this.pump();
      };

      audio.onended = finish;
      audio.onerror = finish;
      audio.play().catch(finish);
    }
  }

  window.translationTts = new AstAudioPlayer();
})();
