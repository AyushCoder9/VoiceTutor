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
  private reconnectAttempts = 0;
  private readonly maxReconnects = 4;
  private reconnecting = false;

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
    this.reconnecting = false;
    this.reconnectAttempts = 0;
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
    // CRITICAL: Create AudioContexts synchronously *before* awaiting the mic prompt,
    // otherwise the browser's "user gesture" token expires and playback gets suspended.
    this.audioCtx = new AudioContext();
    this.playbackCtx = new AudioContext({ sampleRate: this.opts.sampleRateOut });
    this.playbackGain = this.playbackCtx.createGain();
    this.playbackGain.gain.value = 1.0;
    this.playbackGain.connect(this.playbackCtx.destination);
    this.playheadTime = this.playbackCtx.currentTime + 0.05;

    // Force-resume both contexts immediately (browsers may still create them suspended).
    if (this.audioCtx.state === "suspended") await this.audioCtx.resume();
    if (this.playbackCtx.state === "suspended") await this.playbackCtx.resume();
    console.log(`[voiceClient] 🔊 captureCtx.state=${this.audioCtx.state} playbackCtx.state=${this.playbackCtx.state} sampleRate=${this.playbackCtx.sampleRate}`);

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    this.micStream = stream;

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

    // (Moved to the top of setupAudio to ensure it runs synchronously with user gesture)
  }

  private async setupSocket() {
    this.alive = true;
    const ws = new WebSocket(this.opts.url);
    ws.binaryType = "arraybuffer";
    this.ws = ws;

    let binaryMsgCount = 0;
    let textMsgCount = 0;

    ws.onopen = async () => {
      console.log("[voiceClient] WebSocket open →", this.opts.url);
      this.reconnectAttempts = 0;
      this.reconnecting = false;
      if (this.playbackCtx && this.playbackCtx.state === "suspended") {
        console.warn("[voiceClient] ⚠️ playbackCtx was suspended at WS open — resuming");
        await this.playbackCtx.resume();
      }
      console.log(`[voiceClient] playbackCtx.state=${this.playbackCtx?.state}`);
      this.opts.onEvent({ type: "connection", status: "connected" });
    };

    ws.onmessage = async (ev) => {
      if (typeof ev.data === "string") {
        textMsgCount++;
        try {
          const msg = JSON.parse(ev.data) as VoiceEvent;
          console.log(`[voiceClient] 📨 text #${textMsgCount}: type=${msg.type}`, msg);
          if ((msg as any).type === "ping") return; // server keepalive
          if (msg.type === "interrupt") this.flushPlayback();
          this.opts.onEvent(msg);
        } catch (err) {
          console.warn("[voiceClient] ⚠️ failed to parse text message:", ev.data, err);
        }
      } else if (ev.data instanceof ArrayBuffer) {
        // Pipecat 1.x sends ALL frames (including JSON events) as binary.
        // Try to parse as UTF-8 JSON first; only treat as audio if that fails.
        const maybeJson = tryParseJsonBinary(ev.data);
        if (maybeJson !== null) {
          textMsgCount++;
          console.log(`[voiceClient] 📨 binary-JSON #${textMsgCount}: type=${maybeJson.type}`, maybeJson);
          if ((maybeJson as any).type === "ping") return;
          if (maybeJson.type === "interrupt") this.flushPlayback();
          this.opts.onEvent(maybeJson);
          return;
        }
        binaryMsgCount++;
        if (binaryMsgCount <= 3 || binaryMsgCount % 50 === 0) {
          console.log(`[voiceClient] 🔈 audio chunk #${binaryMsgCount}: ${ev.data.byteLength} bytes, playbackCtx.state=${this.playbackCtx?.state}`);
        }
        this.enqueueAudio(ev.data);
      } else if (ev.data instanceof Blob) {
        // Some WebSocket proxies (Render/Cloudflare) may deliver binary as Blob
        const arrayBuf = await ev.data.arrayBuffer();
        const maybeJson = tryParseJsonBinary(arrayBuf);
        if (maybeJson !== null) {
          textMsgCount++;
          console.log(`[voiceClient] 📨 blob-JSON #${textMsgCount}: type=${maybeJson.type}`, maybeJson);
          if ((maybeJson as any).type === "ping") return;
          if (maybeJson.type === "interrupt") this.flushPlayback();
          this.opts.onEvent(maybeJson);
          return;
        }
        binaryMsgCount++;
        if (binaryMsgCount <= 3 || binaryMsgCount % 50 === 0) {
          console.log(`[voiceClient] 🔈 audio chunk #${binaryMsgCount} (Blob→ArrayBuffer): ${arrayBuf.byteLength} bytes, playbackCtx.state=${this.playbackCtx?.state}`);
        }
        this.enqueueAudio(arrayBuf);
      } else {
        console.warn("[voiceClient] ❓ unknown message type:", typeof ev.data, ev.data);
      }
    };

    ws.onerror = (e) => {
      console.error("[voiceClient] WebSocket error", e);
      this.opts.onEvent({ type: "connection", status: "error", message: "WebSocket error" });
    };

    ws.onclose = async (e) => {
      console.log(`[voiceClient] WebSocket closed (code=${e.code} reason=${e.reason || "—"}) — received ${binaryMsgCount} audio chunks, ${textMsgCount} text msgs`);
      this.alive = false;
      // Auto-reconnect on unexpected close (not on user-initiated disconnect).
      if (!this.reconnecting && this.reconnectAttempts < this.maxReconnects && this.opts.url) {
        this.reconnecting = true;
        this.reconnectAttempts++;
        const delay = Math.min(1000 * 2 ** (this.reconnectAttempts - 1), 8000);
        console.log(`[voiceClient] reconnect attempt ${this.reconnectAttempts}/${this.maxReconnects} in ${delay}ms`);
        this.opts.onEvent({ type: "connection", status: "error", message: `Reconnecting… (${this.reconnectAttempts}/${this.maxReconnects})` });
        await new Promise(r => setTimeout(r, delay));
        this.reconnecting = false;
        if (this.opts.url) {
          this.alive = true;
          await this.setupSocket();
          return;
        }
      }
      this.opts.onEvent({ type: "connection", status: "disconnected" });
    };
  }

  private audioChunksQueued = 0;

  private enqueueAudio(buf: ArrayBuffer) {
    if (!this.playbackCtx || !this.playbackGain) {
      console.warn("[voiceClient] ❌ enqueueAudio called but playbackCtx or playbackGain is null");
      return;
    }

    // Safety-net: if context got suspended mid-session, resume it.
    if (this.playbackCtx.state === "suspended") {
      console.warn("[voiceClient] ⚠️ playbackCtx suspended in enqueueAudio — resuming");
      this.playbackCtx.resume();
    }

    // Decode Int16 → Float32.
    const i16 = new Int16Array(buf);
    if (i16.length === 0) {
      console.warn("[voiceClient] ⚠️ received empty audio chunk");
      return;
    }
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 0x8000;

    const audioBuffer = this.playbackCtx.createBuffer(1, f32.length, this.opts.sampleRateOut);
    audioBuffer.copyToChannel(f32, 0);
    const node = this.playbackCtx.createBufferSource();
    node.buffer = audioBuffer;
    node.connect(this.playbackGain!);
    const now = this.playbackCtx.currentTime;
    if (this.playheadTime < now) this.playheadTime = now + 0.02;
    node.start(this.playheadTime);
    this.playheadTime += audioBuffer.duration;
    this.audioChunksQueued++;

    if (this.audioChunksQueued <= 5 || this.audioChunksQueued % 100 === 0) {
      console.log(
        `[voiceClient] 🎵 queued chunk #${this.audioChunksQueued}: ` +
        `${f32.length} samples, ${audioBuffer.duration.toFixed(3)}s, ` +
        `playhead=${this.playheadTime.toFixed(3)}, ctxTime=${now.toFixed(3)}, ` +
        `state=${this.playbackCtx.state}, gain=${this.playbackGain!.gain.value}`
      );
    }
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

function tryParseJsonBinary(buf: ArrayBuffer): VoiceEvent | null {
  // Pipecat 1.x sends JSON control frames as binary WebSocket frames.
  // JSON always starts with '{' (0x7B). Audio PCM16 starts with raw sample bytes
  // that virtually never start with 0x7B 0x22 ({"...). Check the first byte fast.
  const view = new Uint8Array(buf);
  if (view.length === 0 || view[0] !== 0x7b) return null; // not '{'
  try {
    const text = new TextDecoder().decode(buf);
    return JSON.parse(text) as VoiceEvent;
  } catch {
    return null;
  }
}

let _workletURL: string | null = null;
function workletURL(): string {
  if (_workletURL) return _workletURL;
  const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
  _workletURL = URL.createObjectURL(blob);
  return _workletURL;
}
