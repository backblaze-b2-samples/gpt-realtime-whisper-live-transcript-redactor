// PCM16 24kHz mono encoder for the realtime transcription bridge.
//
// OpenAI Realtime expects 24kHz mono PCM16 input. The browser delivers
// Float32 audio at the AudioContext's native sample rate (typically
// 44.1k or 48k); we resample down with a simple linear-interpolation
// step and clamp the resulting Float32 samples to Int16.
//
// This file MUST live at apps/web/public/audio-worklet.js — Next.js
// serves /public at the URL root, and AudioWorklet.addModule() requires
// a top-level URL that does not run through the bundler.

class PCM16Encoder extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = (options && options.processorOptions && options.processorOptions.targetRate) || 24000;
    this.inputBuffer = [];
    this.inputRate = sampleRate; // global from AudioWorkletGlobalScope
    this.ratio = this.inputRate / this.targetRate;
    this.chunkSamples = Math.round(this.targetRate * 0.04); // ~40ms chunks
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const channel = input[0];

    // Append the float frames; downsample lazily once enough is buffered.
    for (let i = 0; i < channel.length; i++) {
      this.inputBuffer.push(channel[i]);
    }

    const needed = Math.ceil(this.chunkSamples * this.ratio);
    while (this.inputBuffer.length >= needed) {
      const slice = this.inputBuffer.splice(0, needed);
      const out = new Int16Array(this.chunkSamples);
      for (let j = 0; j < this.chunkSamples; j++) {
        const srcIdx = j * this.ratio;
        const lo = Math.floor(srcIdx);
        const hi = Math.min(lo + 1, slice.length - 1);
        const frac = srcIdx - lo;
        const sample = slice[lo] * (1 - frac) + slice[hi] * frac;
        const clamped = Math.max(-1, Math.min(1, sample));
        out[j] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
      }
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}

registerProcessor("pcm16-encoder", PCM16Encoder);
