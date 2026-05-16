type GradiumMessage = {
  type?: string;
  text?: string;
  vad?: Array<{ horizon_s: number; inactivity_prob: number }>;
  message?: string;
};

type GradiumStatus = "connecting" | "ready" | "recording" | "stopped" | "error";

const TARGET_SAMPLE_RATE = 16000;

function floatTo16BitPCM(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

function downsampleBuffer(
  input: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number,
): Float32Array {
  if (inputSampleRate === outputSampleRate) {
    return input;
  }

  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.round(input.length / ratio);
  const output = new Float32Array(outputLength);

  for (let i = 0; i < outputLength; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j += 1) {
      sum += input[j];
    }
    output[i] = sum / Math.max(end - start, 1);
  }

  return output;
}

function int16ToBase64(input: Int16Array): string {
  const bytes = new Uint8Array(input.buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export class GradiumSTT {
  private onChunk: (text: string) => void;
  private onFinal: (text: string) => void;
  private onStatus: (status: GradiumStatus, message?: string) => void;
  private mediaStream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private ws: WebSocket | null = null;
  private transcriptSegments: string[] = [];

  constructor({
    onChunk,
    onFinal,
    onStatus,
  }: {
    onChunk: (text: string) => void;
    onFinal: (text: string) => void;
    onStatus: (status: GradiumStatus, message?: string) => void;
  }) {
    this.onChunk = onChunk;
    this.onFinal = onFinal;
    this.onStatus = onStatus;
  }

  async start() {
    this.onStatus("connecting");
    this.transcriptSegments = [];

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
    const wsUrl = backendUrl.replace(/^http/, "ws") + "/gradium/stt";

    this.ws = new WebSocket(wsUrl);
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data) as GradiumMessage;
      if (data.type === "ready") {
        this.onStatus("ready");
      }
      if (data.type === "text" && data.text) {
        this.transcriptSegments.push(data.text);
        this.onChunk(this.transcriptSegments.join(" "));
      }
      if (data.type === "end_of_stream") {
        this.onStatus("stopped");
        this.onFinal(this.transcriptSegments.join(" "));
      }
      if (data.type === "error") {
        this.onStatus("error", data.message);
      }
    };

    await new Promise<void>((resolve, reject) => {
      if (!this.ws) {
        reject(new Error("WebSocket did not initialize"));
        return;
      }
      this.ws.onopen = () => resolve();
      this.ws.onerror = () => reject(new Error("Could not connect to Gradium proxy"));
    });

    this.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.audioContext = new AudioContext();
    this.source = this.audioContext.createMediaStreamSource(this.mediaStream);
    this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
    this.processor.onaudioprocess = (event) => {
      if (this.ws?.readyState !== WebSocket.OPEN || !this.audioContext) {
        return;
      }
      const input = event.inputBuffer.getChannelData(0);
      const downsampled = downsampleBuffer(
        input,
        this.audioContext.sampleRate,
        TARGET_SAMPLE_RATE,
      );
      const pcm = floatTo16BitPCM(downsampled);
      this.ws.send(
        JSON.stringify({
          type: "audio",
          audio: int16ToBase64(pcm),
        }),
      );
    };

    this.source.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
    this.onStatus("recording");
  }

  stop() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "end_of_stream" }));
    }
    this.processor?.disconnect();
    this.source?.disconnect();
    void this.audioContext?.close();
    this.mediaStream?.getTracks().forEach((track) => track.stop());
    this.processor = null;
    this.source = null;
    this.audioContext = null;
    this.mediaStream = null;
  }
}
