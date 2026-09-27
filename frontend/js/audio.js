class FechatSoundEffects {
  constructor() {
    this.ctx = null;
    this.isMuted = localStorage.getItem("fechat_sound_muted") === "true";
    this._incomingRingtoneInterval = null;
    this._outgoingRingbackInterval = null;
    this.setupAutoUnlock();
  }
  setupAutoUnlock() {
    const unlock = (e) => {
      if (e && e.isTrusted) {
        this.unlockAudio();
        document.removeEventListener("click", unlock);
        document.removeEventListener("keydown", unlock);
        document.removeEventListener("touchend", unlock);
      }
    };
    document.addEventListener("click", unlock, { passive: true });
    document.addEventListener("keydown", unlock, { passive: true });
    document.addEventListener("touchend", unlock, { passive: true });
  }
  unlockAudio() {
    try {
      if (!this.ctx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          this.ctx = new AudioCtx({ latencyHint: "interactive" });
        }
      }
      if (this.ctx && this.ctx.state === "suspended") {
        this.ctx.resume().catch(() => {});
      }
    } catch (_) {}
  }
  getAudioContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        try {
          this.ctx = new AudioCtx({ latencyHint: "interactive" });
        } catch (_) {}
      }
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }
  toggleMute() {
    this.isMuted = !this.isMuted;
    localStorage.setItem("fechat_sound_muted", String(this.isMuted));
    return this.isMuted;
  }
  playTick() {
    if (this.isMuted) return;
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(1400, ctx.currentTime);
      gain.gain.setValueAtTime(0.06, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.03);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.035);
    } catch (_) {}
  }
  playSent() {
    if (this.isMuted) return;
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(
        1174.66,
        ctx.currentTime + 0.09,
      );
      gain.gain.setValueAtTime(0.35, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.11);
    } catch (_) {}
  }
  playReceived() {
    if (navigator.vibrate) {
      try {
        navigator.vibrate([80, 50, 80]);
      } catch (_) {}
    }
    if (this.isMuted) return;
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(659.25, ctx.currentTime);
      gain1.gain.setValueAtTime(0.4, ctx.currentTime);
      gain1.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(ctx.currentTime);
      osc1.stop(ctx.currentTime + 0.2);
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "triangle";
      osc2.frequency.setValueAtTime(987.77, ctx.currentTime + 0.08);
      gain2.gain.setValueAtTime(0.45, ctx.currentTime + 0.08);
      gain2.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(ctx.currentTime + 0.08);
      osc2.stop(ctx.currentTime + 0.38);
    } catch (_) {}
  }
  playRecordStart() {
    if (this.isMuted) return;
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.3, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.12);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.14);
    } catch (_) {}
  }
  playRecordStop() {
    if (this.isMuted) return;
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(700, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(350, ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.25, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.1);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(ctx.currentTime);
      osc.stop(ctx.currentTime + 0.12);
    } catch (_) {}
  }
  startIncomingRingtone() {
    this.stopIncomingRingtone();
    this.unlockAudio();
    const playMelodyCycle = () => {
      if (this.isMuted) return;
      try {
        const ctx = this.getAudioContext();
        if (!ctx) return;
        const melody = [
          { f: 523.25, t: 0, d: 0.16, v: 0.45 },
          { f: 659.25, t: 0.14, d: 0.16, v: 0.45 },
          { f: 783.99, t: 0.28, d: 0.16, v: 0.5 },
          { f: 880, t: 0.42, d: 0.18, v: 0.55 },
          { f: 1046.5, t: 0.58, d: 0.22, v: 0.6 },
          { f: 783.99, t: 0.82, d: 0.18, v: 0.5 },
          { f: 1318.51, t: 1.02, d: 0.38, v: 0.65 },
        ];
        melody.forEach((n) => {
          const osc1 = ctx.createOscillator();
          const gain1 = ctx.createGain();
          osc1.type = "sine";
          osc1.frequency.setValueAtTime(n.f, ctx.currentTime + n.t);
          gain1.gain.setValueAtTime(n.v, ctx.currentTime + n.t);
          gain1.gain.exponentialRampToValueAtTime(
            0.001,
            ctx.currentTime + n.t + n.d,
          );
          osc1.connect(gain1);
          gain1.connect(ctx.destination);
          osc1.start(ctx.currentTime + n.t);
          osc1.stop(ctx.currentTime + n.t + n.d + 0.05);
          const osc2 = ctx.createOscillator();
          const gain2 = ctx.createGain();
          osc2.type = "triangle";
          osc2.frequency.setValueAtTime(n.f * 2, ctx.currentTime + n.t);
          gain2.gain.setValueAtTime(n.v * 0.3, ctx.currentTime + n.t);
          gain2.gain.exponentialRampToValueAtTime(
            0.001,
            ctx.currentTime + n.t + n.d * 0.7,
          );
          osc2.connect(gain2);
          gain2.connect(ctx.destination);
          osc2.start(ctx.currentTime + n.t);
          osc2.stop(ctx.currentTime + n.t + n.d + 0.05);
        });
        if (navigator.vibrate) {
          try {
            navigator.vibrate([250, 100, 250, 100, 400]);
          } catch (_) {}
        }
      } catch (err) {
        console.warn("Erro ao tocar ringtone:", err);
      }
    };
    playMelodyCycle();
    this._incomingRingtoneInterval = setInterval(playMelodyCycle, 2200);
  }
  stopIncomingRingtone() {
    if (this._incomingRingtoneInterval) {
      clearInterval(this._incomingRingtoneInterval);
      this._incomingRingtoneInterval = null;
    }
  }
  startOutgoingRingback() {
    this.stopOutgoingRingback();
    this.unlockAudio();
    const playDialTone = () => {
      if (this.isMuted) return;
      try {
        const ctx = this.getAudioContext();
        if (!ctx) return;
        [440, 480].forEach((freq) => {
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();
          osc.type = "sine";
          osc.frequency.setValueAtTime(freq, ctx.currentTime);
          gain.gain.setValueAtTime(0.001, ctx.currentTime);
          gain.gain.linearRampToValueAtTime(0.28, ctx.currentTime + 0.05);
          gain.gain.setValueAtTime(0.28, ctx.currentTime + 1.2);
          gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.28);
          osc.connect(gain);
          gain.connect(ctx.destination);
          osc.start(ctx.currentTime);
          osc.stop(ctx.currentTime + 1.3);
        });
      } catch (err) {
        console.warn("Erro ao tocar ringback:", err);
      }
    };
    playDialTone();
    this._outgoingRingbackInterval = setInterval(playDialTone, 3200);
  }
  stopOutgoingRingback() {
    if (this._outgoingRingbackInterval) {
      clearInterval(this._outgoingRingbackInterval);
      this._outgoingRingbackInterval = null;
    }
  }
  playCallConnected() {
    if (this.isMuted) return;
    this.unlockAudio();
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const chords = [
        { f: 523.25, t: 0, d: 0.18, v: 0.4 },
        { f: 659.25, t: 0.12, d: 0.18, v: 0.45 },
        { f: 1046.5, t: 0.24, d: 0.35, v: 0.55 },
      ];
      chords.forEach((c) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(c.f, ctx.currentTime + c.t);
        gain.gain.setValueAtTime(c.v, ctx.currentTime + c.t);
        gain.gain.exponentialRampToValueAtTime(
          0.001,
          ctx.currentTime + c.t + c.d,
        );
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + c.t);
        osc.stop(ctx.currentTime + c.t + c.d + 0.05);
      });
    } catch (_) {}
  }
  playCallEnded() {
    if (this.isMuted) return;
    this.unlockAudio();
    try {
      const ctx = this.getAudioContext();
      if (!ctx || ctx.state === "suspended") return;
      const beeps = [
        { f: 480, t: 0 },
        { f: 480, t: 0.16 },
        { f: 480, t: 0.32 },
      ];
      beeps.forEach((b) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(b.f, ctx.currentTime + b.t);
        gain.gain.setValueAtTime(0.35, ctx.currentTime + b.t);
        gain.gain.exponentialRampToValueAtTime(
          0.001,
          ctx.currentTime + b.t + 0.12,
        );
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + b.t);
        osc.stop(ctx.currentTime + b.t + 0.14);
      });
    } catch (_) {}
  }
}
const FechatAudio = new FechatSoundEffects();
window.FechatAudio = FechatAudio;
