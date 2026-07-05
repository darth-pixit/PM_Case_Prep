// Captures raw mic audio and posts Float32 frames to the main thread.
// The main thread resamples to 16 kHz Int16 PCM and streams it to the server.
class PCMWorklet extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0] && input[0].length) {
      // Copy — the underlying buffer is reused by the audio engine.
      this.port.postMessage(input[0].slice(0));
    }
    return true; // keep processor alive
  }
}
registerProcessor("pcm-worklet", PCMWorklet);
