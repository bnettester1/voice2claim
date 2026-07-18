/* AudioWorklet: downsample về 16kHz (linear interp) → Int16 → frame 1600 mẫu (100ms)
   postMessage(ArrayBuffer) → main thread gửi binary qua WebSocket. */
class PCM16Downsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;   // sampleRate = rate thật của AudioContext
    this.readPos = 0;
    this.carry = new Float32Array(0);
    this.out = new Int16Array(1600);
    this.outLen = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    const buf = new Float32Array(this.carry.length + ch.length);
    buf.set(this.carry); buf.set(ch, this.carry.length);
    let pos = this.readPos;
    while (pos + 1 < buf.length) {
      const i = pos | 0, f = pos - i;
      let s = buf[i] * (1 - f) + buf[i + 1] * f;
      s = Math.max(-1, Math.min(1, s));
      this.out[this.outLen++] = s < 0 ? s * 0x8000 : s * 0x7FFF;
      if (this.outLen === 1600) {
        const frame = this.out.slice(0);
        this.port.postMessage(frame.buffer, [frame.buffer]);
        this.outLen = 0;
      }
      pos += this.ratio;
    }
    const keep = pos | 0;
    this.carry = buf.slice(keep);
    this.readPos = pos - keep;
    return true;
  }
}
registerProcessor('pcm16-downsampler', PCM16Downsampler);
