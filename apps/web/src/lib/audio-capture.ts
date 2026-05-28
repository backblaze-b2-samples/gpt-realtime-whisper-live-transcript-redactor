/**
 * Browser-side mic capture + PCM16 24kHz mono encoding.
 *
 * Uses getUserMedia + AudioContext + an AudioWorkletNode that loads the
 * encoder at `/audio-worklet.js`. The worklet emits ArrayBuffer chunks
 * the caller can pipe straight into a WebSocket binary frame.
 *
 * The AudioWorklet file must be served at the top-level URL — Next.js
 * does that for any file in `public/`. NEVER move it under `src/`; the
 * bundler will mangle the path and `addModule` will fail at runtime.
 */

export interface AudioCaptureHandle {
  stop: () => Promise<void>;
  stream: MediaStream;
}

export interface StartCaptureOptions {
  onChunk: (pcm16: ArrayBuffer) => void;
  onError?: (error: Error) => void;
  targetRate?: number;
}

export async function startCapture({
  onChunk,
  onError,
  targetRate = 24000,
}: StartCaptureOptions): Promise<AudioCaptureHandle> {
  if (typeof window === "undefined") {
    throw new Error("startCapture must run in the browser");
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("getUserMedia is not supported in this browser");
  }
  if (typeof AudioWorkletNode === "undefined") {
    throw new Error("AudioWorklet is not supported in this browser");
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  const ctx = new AudioContext();
  try {
    await ctx.audioWorklet.addModule("/audio-worklet.js");
  } catch (e) {
    stream.getTracks().forEach((t) => t.stop());
    await ctx.close();
    throw new Error(
      `Failed to load audio-worklet.js — make sure it is served at the URL root: ${(e as Error).message}`,
    );
  }

  const source = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "pcm16-encoder", {
    processorOptions: { targetRate },
  });

  node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
    try {
      onChunk(event.data);
    } catch (err) {
      onError?.(err as Error);
    }
  };

  source.connect(node);
  // Connect to destination via a zero-gain node so the worklet keeps
  // pulling — otherwise Chrome will throttle the AudioContext if it
  // thinks nothing is consuming the graph.
  const sink = ctx.createGain();
  sink.gain.value = 0;
  node.connect(sink);
  sink.connect(ctx.destination);

  let stopped = false;
  const stop = async () => {
    if (stopped) return;
    stopped = true;
    try {
      source.disconnect();
      node.disconnect();
      sink.disconnect();
    } catch {
      /* noop */
    }
    stream.getTracks().forEach((t) => t.stop());
    await ctx.close();
  };

  return { stop, stream };
}
