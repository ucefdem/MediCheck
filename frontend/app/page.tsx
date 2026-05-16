"use client";

import { useEffect, useRef, useState } from "react";

import { analyzeTriage } from "../lib/api";
import { GradiumSTT } from "../lib/gradium";
import type { EntityMap, ExtractionResult, TavilyCard, TriageResponse } from "../types";

const demoTranscript =
  "Um, hi doctor, I've been having chest pain for three days, kind of on the left side. I take 50 milligrams of Lisinopril every morning, sometimes ibuprofen too. I had a bypass surgery in 2019.";

const emptyEntities: EntityMap = {
  Symptom: [],
  Medication: [],
  Dosage: [],
  "Medical History": [],
  "Anatomical Site": [],
  Duration: [],
  Frequency: [],
};

const sampleResults: TriageResponse = {
  transcript: demoTranscript,
  winner: "pioneer",
  pioneer: {
    latency_ms: 342,
    provider: "pioneer_gliner2",
    entities: {
      ...emptyEntities,
      Symptom: ["chest pain"],
      Medication: ["Lisinopril", "ibuprofen"],
      Dosage: ["50 milligrams"],
      "Medical History": ["bypass surgery"],
      "Anatomical Site": ["left side"],
      Duration: ["three days"],
      Frequency: ["every morning"],
    },
  },
  pioneer_finetuned: {
    latency_ms: 416,
    provider: "pioneer_gliner2_finetuned",
    entities: {
      ...emptyEntities,
      Symptom: ["chest pain"],
      Medication: ["Lisinopril", "ibuprofen"],
      Dosage: ["50 milligrams"],
      "Medical History": ["bypass surgery"],
      "Anatomical Site": ["left side"],
      Duration: ["three days"],
      Frequency: ["every morning"],
    },
  },
  openai: {
    latency_ms: 2841,
    provider: "gpt-4o-mini",
    entities: {
      ...emptyEntities,
      Symptom: ["chest pain"],
      Medication: ["Lisinopril", "ibuprofen"],
      "Medical History": ["bypass surgery in 2019"],
      "Anatomical Site": ["left side"],
      Duration: ["three days"],
    },
  },
  tavily_cards: [
    {
      drug: "Lisinopril",
      indication:
        "ACE inhibitor commonly used for high blood pressure and heart failure.",
      contraindications: "Monitor potassium, kidney function, and low blood pressure.",
    },
    {
      drug: "Ibuprofen",
      indication: "NSAID used for pain, fever, and inflammation.",
      contraindications: "May reduce antihypertensive effect and increase renal risk.",
      warning:
        "Ibuprofen can be risky in some cardiac histories. Verify use with the patient.",
    },
  ],
};

const labelStyles: Record<string, string> = {
  Symptom: "border-rose-200 bg-rose-50 text-rose-700",
  Medication: "border-sky-200 bg-sky-50 text-sky-700",
  Dosage: "border-amber-200 bg-amber-50 text-amber-800",
  "Medical History": "border-violet-200 bg-violet-50 text-violet-700",
  "Anatomical Site": "border-teal-200 bg-teal-50 text-teal-700",
  Duration: "border-emerald-200 bg-emerald-50 text-emerald-700",
  Frequency: "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-700",
};

const idleWaveformLevels = [
  0.18, 0.24, 0.14, 0.32, 0.42, 0.2, 0.28, 0.5, 0.68, 0.34, 0.24, 0.56,
  0.72, 0.38, 0.22, 0.3, 0.46, 0.28, 0.18, 0.34, 0.52, 0.6, 0.42, 0.24,
  0.18,
];
const waveformCenter = Math.floor(idleWaveformLevels.length / 2);

function formatTimer(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

function MicIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-9 w-9"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.8"
    >
      <path d="M12 14.5a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 0 0-7 0v5a3.5 3.5 0 0 0 3.5 3.5Z" />
      <path d="M5.5 10.5a6.5 6.5 0 0 0 13 0M12 17v4M8.5 21h7" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-5 w-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth="1.9"
    >
      <path d="m4 12 16-7-7 16-2-7-7-2Z" />
      <path d="m11 14 4-4" />
    </svg>
  );
}

function Waveform({ active, levels }: { active: boolean; levels: number[] }) {
  const sourceLevels = levels.length ? levels : idleWaveformLevels;
  const displayLevels = sourceLevels.map((level, index) => {
    const distanceFromCenter = Math.abs(index - waveformCenter) / waveformCenter;
    const centerWeight = 1 - distanceFromCenter * 0.68;
    return Math.max(0.08, Math.min(1, level * centerWeight));
  });

  return (
    <div className="flex h-20 items-center justify-center gap-1.5">
      {displayLevels.map((level, index) => (
        <span
          key={`${index}-${level}`}
          className={`w-1.5 rounded-full transition-all duration-75 ${
            active ? "bg-[#6e8f88]" : "bg-zinc-300"
          }`}
          style={{
            height: `${Math.max(10, Math.round(14 + level * 66))}px`,
            opacity: active ? Math.max(0.45, level) : 0.55,
          }}
        />
      ))}
    </div>
  );
}

function LatencyBadge({ latency }: { latency?: number }) {
  if (latency === undefined || latency === null) {
    return <span className="text-sm font-medium text-zinc-400">Waiting</span>;
  }

  const isFast = latency < 1000;

  return (
    <span
      className={`text-3xl font-semibold tabular-nums ${
        isFast ? "text-[#2d7b6f]" : "text-[#d56f60]"
      }`}
    >
      {latency}ms
    </span>
  );
}

function EntityPanel({
  title,
  eyebrow,
  result,
  isWinner,
}: {
  title: string;
  eyebrow: string;
  result?: ExtractionResult;
  isWinner?: boolean;
}) {
  const entities = result?.entities ?? emptyEntities;
  const populated = Object.entries(entities).filter(([, values]) => values.length);

  return (
    <article
      className={`rounded-3xl border bg-white p-5 shadow-sm ${
        isWinner ? "border-[#6e8f88] ring-4 ring-[#dbe9e4]" : "border-zinc-200"
      }`}
    >
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
            {eyebrow}
          </p>
          <h3 className="mt-1 text-xl font-semibold text-zinc-950">{title}</h3>
          {result?.provider ? (
            <p className="mt-1 truncate text-xs text-zinc-400">{result.provider}</p>
          ) : null}
        </div>
        <LatencyBadge latency={result?.latency_ms} />
      </div>

      {populated.length ? (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {populated.map(([label, values]) => (
            <div key={label} className="rounded-2xl bg-zinc-50 p-3">
              <span className="text-xs font-semibold text-zinc-400">{label}</span>
              <div className="flex flex-wrap gap-2">
                {values.map((value) => (
                  <span
                    key={`${label}-${value}`}
                    className={`mt-2 max-w-full rounded-full border px-3 py-1 text-xs font-medium leading-5 ${
                      labelStyles[label] ??
                      "border-zinc-200 bg-zinc-50 text-zinc-600"
                    }`}
                  >
                    {value}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex min-h-32 items-center justify-center rounded-2xl border border-dashed border-zinc-200 bg-zinc-50 px-4 text-center text-sm text-zinc-400">
          Results will appear after analysis.
        </div>
      )}
    </article>
  );
}

function KnowledgeCards({ cards }: { cards: TavilyCard[] }) {
  if (!cards.length) {
    return (
      <div className="rounded-3xl border border-dashed border-zinc-200 bg-white/70 p-10 text-center text-sm text-zinc-400">
        Medication verification cards will appear here after analysis.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {cards.map((card) => (
        <article
          key={card.drug}
          className={`rounded-3xl border bg-white p-4 shadow-sm ${
            card.warning ? "border-[#f2b3a7]" : "border-zinc-200"
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0 flex-1">
              <h3 className="text-base font-semibold text-zinc-950">{card.drug}</h3>
              <p className="mt-1 text-sm leading-6 text-zinc-600">{card.indication}</p>
              {card.contraindications ? (
                <p className="mt-1 text-sm leading-6 text-zinc-500">
                  <span className="font-medium text-zinc-700">Caution:</span>{" "}
                  {card.contraindications}
                </p>
              ) : null}
            </div>
            {card.warning ? (
              <span className="shrink-0 rounded-full bg-[#fff0ed] px-3 py-1 text-xs font-semibold text-[#c65f51]">
                Warning
              </span>
            ) : null}
          </div>
          {card.warning ? (
            <p className="mt-3 rounded-2xl bg-[#fff6f3] p-3 text-sm leading-6 text-[#994a41]">
              {card.warning}
            </p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

export default function Home() {
  const [transcript, setTranscript] = useState(demoTranscript);
  const [results, setResults] = useState<TriageResponse | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevels, setAudioLevels] = useState<number[]>([]);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("Ready");
  const [error, setError] = useState("");
  const sttRef = useRef<GradiumSTT | null>(null);

  useEffect(() => {
    if (!isRecording) {
      return;
    }

    const interval = window.setInterval(() => {
      setRecordingSeconds((seconds) => seconds + 1);
    }, 1000);

    return () => window.clearInterval(interval);
  }, [isRecording]);

  async function analyzeTranscript(inputText = transcript) {
    if (isRecording) {
      sttRef.current?.stop();
      setIsRecording(false);
      setAudioLevels([]);
      setVoiceStatus("Finalizing");
    }

    const text = inputText.trim();
    if (!text) {
      setError("Add a transcript before analyzing.");
      return;
    }

    setIsAnalyzing(true);
    setError("");

    try {
      const data = await analyzeTriage(text);
      setResults(data);
    } catch (err) {
      setResults(sampleResults);
      setError(
        err instanceof Error
          ? `${err.message}. Showing demo data until the backend is ready.`
          : "Backend unavailable. Showing demo data until the backend is ready.",
      );
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleRecord() {
    if (isRecording) {
      sttRef.current?.stop();
      setIsRecording(false);
      setVoiceStatus("Finalizing");
      return;
    }

    setTranscript("");
    setResults(null);
    setError("");
    setRecordingSeconds(0);
    setAudioLevels([]);
    setVoiceStatus("Connecting");

    const stt = new GradiumSTT({
      onChunk: (text) => setTranscript(text),
      onFinal: (text) => {
        setIsRecording(false);
        setVoiceStatus("Ready");
        if (text.trim()) {
          setTranscript(text);
          void analyzeTranscript(text);
        }
      },
      onStatus: (status, message) => {
        if (status === "recording") {
          setVoiceStatus("Recording");
        } else if (status === "ready") {
          setVoiceStatus("Listening");
        } else if (status === "connecting") {
          setVoiceStatus("Connecting");
        } else if (status === "stopped") {
          setVoiceStatus("Ready");
        } else if (status === "error") {
          setVoiceStatus("Voice unavailable");
          setError(message ?? "Gradium transcription failed.");
          setIsRecording(false);
          setAudioLevels([]);
        }
      },
      onAudioLevels: setAudioLevels,
    });

    sttRef.current = stt;
    try {
      await stt.start();
      setIsRecording(true);
    } catch (err) {
      setIsRecording(false);
      setAudioLevels([]);
      setVoiceStatus("Voice unavailable");
      setError(
        err instanceof Error
          ? `${err.message}. You can still paste text and click Analyze.`
          : "Voice input failed. You can still paste text and click Analyze.",
      );
    }
  }

  function clearTranscript() {
    sttRef.current?.stop();
    setIsRecording(false);
    setAudioLevels([]);
    setRecordingSeconds(0);
    setVoiceStatus("Ready");
    setTranscript("");
    setResults(null);
    setError("");
  }

  const activeResults = results;

  return (
    <main className="min-h-screen bg-[#f7f7f3] text-zinc-950">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-6 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#6e8f88]">
              Privacy-first medical triage
            </p>
            <h1 className="mt-2 text-4xl font-semibold tracking-tight text-zinc-950">
              MediCheck
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-500 shadow-sm">
              {isAnalyzing ? "Analyzing" : voiceStatus}
            </span>
            <button
              type="button"
              onClick={() => analyzeTranscript()}
              disabled={isAnalyzing}
              className="rounded-full bg-zinc-950 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
            >
              {isAnalyzing ? "Analyzing..." : "Analyze"}
            </button>
            <button
              type="button"
              onClick={clearTranscript}
              className="rounded-full border border-zinc-200 bg-white px-5 py-2.5 text-sm font-semibold text-zinc-700 shadow-sm transition hover:border-zinc-300 hover:bg-zinc-50"
            >
              Clear
            </button>
          </div>
        </header>

        {error ? (
          <div className="rounded-3xl border border-[#f1c0b6] bg-[#fff6f3] px-5 py-4 text-sm text-[#994a41]">
            {error}
          </div>
        ) : null}

        <section className="grid gap-6 lg:grid-cols-[420px_1fr]">
          <div className="space-y-6">
            <div className="rounded-[2.25rem] bg-white p-5 shadow-sm ring-1 ring-zinc-200">
              <div className="rounded-[2rem] bg-[#f9faf8] p-6">
                <div className="mx-auto mb-5 h-1.5 w-12 rounded-full bg-zinc-200" />

                <div className="flex flex-col items-center">
                  <button
                    type="button"
                    onClick={handleRecord}
                    disabled={isAnalyzing}
                    aria-label={isRecording ? "Stop recording" : "Start recording"}
                    className={`relative flex h-28 w-28 items-center justify-center rounded-full transition disabled:cursor-not-allowed ${
                      isRecording
                        ? "bg-[#e8f1ee] text-[#426d63]"
                        : "bg-[#eef2ef] text-[#6e8f88] hover:bg-[#e7eee9]"
                    }`}
                  >
                    {isRecording ? (
                      <span className="absolute h-full w-full animate-ping rounded-full bg-[#dbe9e4]" />
                    ) : null}
                    <span className="relative flex h-20 w-20 items-center justify-center rounded-full bg-white shadow-sm">
                      <MicIcon />
                    </span>
                  </button>

                  <p className="mt-5 text-2xl font-semibold tabular-nums text-[#5d7973]">
                    {formatTimer(recordingSeconds)}
                  </p>
                  <Waveform active={isRecording} levels={audioLevels} />

                  <div className="mt-4 flex w-full items-center justify-between">
                    <button
                      type="button"
                      onClick={() => setTranscript(demoTranscript)}
                      className="flex h-12 w-12 items-center justify-center rounded-full border border-zinc-200 bg-white text-xl text-[#6e8f88] shadow-sm transition hover:border-zinc-300"
                      aria-label="Reset demo transcript"
                    >
                      ↻
                    </button>
                    <button
                      type="button"
                      onClick={() => analyzeTranscript()}
                      disabled={isAnalyzing}
                      className="flex h-14 w-14 items-center justify-center rounded-full bg-[#ee8b7b] text-white shadow-sm transition hover:bg-[#e17c6d] disabled:cursor-not-allowed disabled:bg-zinc-300"
                      aria-label="Analyze transcript"
                    >
                      <SendIcon />
                    </button>
                  </div>
                </div>
              </div>

              <div className="mt-5">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                      Transcript
                    </p>
                    <h2 className="mt-1 text-lg font-semibold text-zinc-950">
                      Patient History
                    </h2>
                  </div>
                </div>
                <textarea
                  value={transcript}
                  onChange={(event) => setTranscript(event.target.value)}
                  placeholder="Type or paste the patient transcript here."
                  className="min-h-[190px] w-full resize-y rounded-3xl border border-zinc-200 bg-white p-4 text-base leading-7 text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                />
              </div>
            </div>

            <section className="rounded-[2rem] bg-white p-6 shadow-sm ring-1 ring-zinc-200">
              <div className="mb-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                  Tavily verification
                </p>
                <h2 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950">
                  Medication Cards
                </h2>
                <p className="mt-2 text-sm text-zinc-500">
                  Safety checks from extracted medications.
                </p>
              </div>
              <KnowledgeCards cards={activeResults?.tavily_cards ?? []} />
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-[2rem] bg-white p-6 shadow-sm ring-1 ring-zinc-200">
              <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                    Model benchmark
                  </p>
                  <h2 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-950">
                    Extraction Results
                  </h2>
                </div>
                <p className="text-sm text-zinc-500">
                  Zero-shot, fine-tuned, and GPT baseline compared live.
                </p>
              </div>

              {isAnalyzing ? (
                <div className="mb-4 flex items-center gap-2 text-sm text-[#6e8f88]">
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#6e8f88] border-t-transparent" />
                  <span>Analyzing transcript...</span>
                </div>
              ) : null}

              <div className="grid gap-4">
                <EntityPanel
                  title="Pioneer Zero-shot"
                  eyebrow="GLiNER2"
                  result={activeResults?.pioneer}
                  isWinner={activeResults?.winner === "pioneer"}
                />
                <EntityPanel
                  title="Pioneer Fine-tuned"
                  eyebrow="Medical GLiNER2"
                  result={activeResults?.pioneer_finetuned ?? undefined}
                  isWinner={activeResults?.winner === "pioneer_finetuned"}
                />
                <EntityPanel
                  title="GPT-4o-mini"
                  eyebrow="Cloud baseline"
                  result={activeResults?.openai}
                  isWinner={activeResults?.winner === "openai"}
                />
              </div>
            </section>

          </div>
        </section>
      </div>
    </main>
  );
}
