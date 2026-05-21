/**
 * Voice client — minimal WebSocket + Web Audio bridge to the Pipecat bot.
 *
 * Wire format mirrors backend/transports/serializer.py:
 *   - Outgoing binary  : Int16 PCM @ 16 kHz mono (mic capture)
 *   - Outgoing text    : JSON control (rarely used; bot is mostly self-driving)
 *   - Incoming binary  : Int16 PCM @ 24 kHz mono (TTS playback)
 *   - Incoming text    : JSON events { type: "transcript" | "bot_speaking" | ... }
 *
 * Mic capture uses an AudioWorklet to downsample to 16k and emit Int16 chunks.
 * Playback uses an AudioBufferSource queue with monotonic scheduling — no
 * jitter, no clicks between chunks, supports barge-in (flush on user start).
 */

export type VoiceEvent =
  | { type: "transcript"; role: "user" | "assistant"; text: string; interim?: boolean; language?: string }
  | { type: "bot_speaking"; speaking: boolean }
  | { type: "user_speaking"; speaking: boolean }
  | { type: "interrupt" }
  | { type: "interrupt_stop" }
  | { type: "end" }
  | { type: "mic_level"; rms: number; peak: number }
  | { type: "state"; mode: string; persona: string; lesson_id: string | null; lesson_step: string; quiz_index: number; quiz_total: number; quiz_score: number; engagement_score?: number; engagement_label?: string; pace_wpm?: number }
  | { type: "connection"; status: "connected" | "disconnected" | "error"; message?: string };

export type VoiceClientOptions = {
  url: string;
  onEvent?: (e: VoiceEvent) => void;
  sampleRateIn?: number;   // mic capture target
  sampleRateOut?: number;  // playback
};

export class VoiceClient {
  private ws: WebSocket | null = null;
  private audioCtx: AudioContext | null = null;
  private workletNode: AudioWorkletNode | null = null;
  private micStream: MediaStream | null = null;
  private playheadTime = 0;
  private playbackCtx: AudioContext | null = null;
  private playbackGain: GainNode | null = null;
  private outQueue: ArrayBuffer[] = [];
  private opts: Required<VoiceClientOptions>;
  private alive = false;

  constructor(opts: VoiceClientOptions) {
    this.opts = {
      sampleRateIn: 16000,
      sampleRateOut: 24000,
      onEvent: () => {},
      ...opts,
    };
  }

  async connect(): Promise<void> {
    await this.setupAudio();
    await this.setupSocket();
  }

  async disconnect(): Promise<void> {
    this.alive = false;
    try { this.ws?.close(); } catch {}
    this.ws = null;
    try { this.workletNode?.disconnect(); } catch {}
    this.workletNode = null;
    try { this.micStream?.getTracks().forEach((t) => t.stop()); } catch {}
    this.micStream = null;
    try { await this.audioCtx?.close(); } catch {}
    this.audioCtx = null;
    try { await this.playbackCtx?.close(); } catch {}
    this.playbackCtx = null;
    this.opts.onEvent({ type: "connection", status: "disconnected" });
  }

  // ---------------------------------------------------------------------
  // Audio
  // ---------------------------------------------------------------------
  private async setupAudio() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    this.micStream = stream;

    // Capture context — browser default sample rate (often 48kHz).
    this.audioCtx = new AudioContext();
    await this.audioCtx.audioWorklet.addModule(workletURL());
    const src = this.audioCtx.createMediaStreamSource(stream);
    this.workletNode = new AudioWorkletNode(this.audioCtx, "pcm-downsampler", {
      processorOptions: { targetSampleRate: this.opts.sampleRateIn },
    });
    let framesSent = 0;
    let lastLevelEmit = 0;
    this.workletNode.port.onmessage = (ev) => {
      const buf: ArrayBuffer = ev.data;
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(buf);
        framesSent++;
        // RMS + peak of this chunk — feed UI meter (throttled to 10Hz).
        const now = performance.now();
        if (now - lastLevelEmit > 100) {
          const i16 = new Int16Array(buf);
          let sumSq = 0;
          let peak = 0;
          for (let i = 0; i < i16.length; i++) {
            const v = i16[i];
            sumSq += v * v;
            if (Math.abs(v) > peak) peak = Math.abs(v);
          }
          const rms = i16.length ? Math.sqrt(sumSq / i16.length) : 0;
          this.opts.onEvent({ type: "mic_level", rms, peak });
          lastLevelEmit = now;
        }
        if (framesSent === 1 || framesSent % 250 === 0) {
          console.log(`[voiceClient] sent ${framesSent} audio frames`);
        }
      }
    };
    src.connect(this.workletNode);
    // No destination — capture-only.

    // Separate playback context at the server's output rate.
    this.playbackCtx = new AudioContext({ sampleRate: this.opts.sampleRateOut });
    this.playbackGain = this.playbackCtx.createGain();
    this.playbackGain.gain.value = 1.0;
    this.playbackGain.connect(this.playbackCtx.destination);
    this.playheadTime = this.playbackCtx.currentTime + 0.05;
  }

  private async setupSocket() {
    this.alive = true;
    const ws = new WebSocket(this.opts.url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    ws.onopen = () => {
      console.log("[voiceClient] WebSocket open →", this.opts.url);
      this.opts.onEvent({ type: "connection", status: "connected" });
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        try {
          const msg = JSON.parse(ev.data) as VoiceEvent;
          if (msg.type === "interrupt") this.flushPlayback();
          this.opts.onEvent(msg);
        } catch {
          /* ignore */
        }
      } else if (ev.data instanceof ArrayBuffer) {
        this.enqueueAudio(ev.data);
      }
    };

    ws.onerror = (e) => {
      console.error("[voiceClient] WebSocket error", e);
      this.opts.onEvent({ type: "connection", status: "error", message: "WebSocket error" });
    };

    ws.onclose = (e) => {
      console.log(`[voiceClient] WebSocket closed (code=${e.code} reason=${e.reason || "—"})`);
      this.alive = false;
      this.opts.onEvent({ type: "connection", status: "disconnected" });
    };
  }

  private enqueueAudio(buf: ArrayBuffer) {
    if (!this.playbackCtx || !this.playbackGain) return;
    // Decode Int16 → Float32.
    const i16 = new Int16Array(buf);
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 0x8000;

    const audioBuffer = this.playbackCtx.createBuffer(1, f32.length, this.opts.sampleRateOut);
    audioBuffer.copyToChannel(f32, 0);
    const node = this.playbackCtx.createBufferSource();
    node.buffer = audioBuffer;
    node.connect(this.playbackGain);
    const now = this.playbackCtx.currentTime;
    if (this.playheadTime < now) this.playheadTime = now + 0.02;
    node.start(this.playheadTime);
    this.playheadTime += audioBuffer.duration;
  }

  private flushPlayback() {
    if (!this.playbackCtx || !this.playbackGain) return;
    // Disconnect and rebuild the gain node — fastest way to drop pending
    // scheduled buffers without iterating sources.
    try { this.playbackGain.disconnect(); } catch {}
    this.playbackGain = this.playbackCtx.createGain();
    this.playbackGain.gain.value = 1.0;
    this.playbackGain.connect(this.playbackCtx.destination);
    this.playheadTime = this.playbackCtx.currentTime + 0.02;
  }
}

// Inline AudioWorklet — kept as a blob URL so we don't need a static path.
const WORKLET_SOURCE = `
class PCMDownsampler extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    this.targetRate = (opts.processorOptions && opts.processorOptions.targetSampleRate) || 16000;
    this.srcRate = sampleRate;
    this.ratio = this.srcRate / this.targetRate;
    this.buf = [];
    this.bufLen = 0;
    this.chunkFrames = Math.floor(this.targetRate * 0.04); // ~40ms chunks
  }
  process(inputs) {
    const ch0 = inputs[0][0];
    if (!ch0) return true;

    // Resample by linear interpolation.
    const outLen = Math.floor(ch0.length / this.ratio);
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const t = i * this.ratio;
      const i0 = Math.floor(t);
      const i1 = Math.min(ch0.length - 1, i0 + 1);
      const frac = t - i0;
      out[i] = ch0[i0] * (1 - frac) + ch0[i1] * frac;
    }
    this.buf.push(out);
    this.bufLen += out.length;

    while (this.bufLen >= this.chunkFrames) {
      const merged = new Float32Array(this.chunkFrames);
      let off = 0;
      while (off < this.chunkFrames) {
        const head = this.buf[0];
        const take = Math.min(head.length, this.chunkFrames - off);
        merged.set(head.subarray(0, take), off);
        off += take;
        if (take === head.length) this.buf.shift();
        else this.buf[0] = head.subarray(take);
      }
      this.bufLen -= this.chunkFrames;

      // Float32 → Int16 LE.
      const i16 = new Int16Array(merged.length);
      for (let i = 0; i < merged.length; i++) {
        const s = Math.max(-1, Math.min(1, merged[i]));
        i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(i16.buffer, [i16.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-downsampler", PCMDownsampler);
`;

let _workletURL: string | null = null;
function workletURL(): string {
  if (_workletURL) return _workletURL;
  const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
  _workletURL = URL.createObjectURL(blob);
  return _workletURL;
}
