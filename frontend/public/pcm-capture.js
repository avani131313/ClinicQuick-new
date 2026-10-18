// AudioWorklet: microphone Float32 at the device rate → 16 kHz mono PCM16, posted in ~40 ms chunks.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000;
    this.buf = [];
    this.pos = 0;
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    // linear-interpolated downsample
    for (; this.pos < ch.length; this.pos += this.ratio) {
      const i = Math.floor(this.pos), f = this.pos - i;
      const a = ch[i], b = i + 1 < ch.length ? ch[i + 1] : a;
      this.buf.push(a + (b - a) * f);
    }
    this.pos -= ch.length;
    if (this.buf.length >= 640) {
      const out = new Int16Array(this.buf.length);
      let peak = 0;
      for (let i = 0; i < this.buf.length; i++) {
        const v = Math.max(-1, Math.min(1, this.buf[i]));
        out[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
        peak = Math.max(peak, Math.abs(v));
      }
      this.port.postMessage({ pcm: out.buffer, peak }, [out.buffer]);
      this.buf = [];
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
