"use client";

import { useRef, useState } from "react";

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
  Symptom: "border-red-500/40 bg-red-500/10 text-red-100",
  Medication: "border-sky-500/40 bg-sky-500/10 text-sky-100",
  Dosage: "border-amber-500/40 bg-amber-500/10 text-amber-100",
  "Medical History": "border-violet-500/40 bg-violet-500/10 text-violet-100",
  "Anatomical Site": "border-teal-500/40 bg-teal-500/10 text-teal-100",
  Duration: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
  Frequency: "border-pink-500/40 bg-pink-500/10 text-pink-100",
};

function LatencyBadge({ latency }: { latency?: number }) {
  if (latency === undefined || latency === null) {
    return <span className="text-sm text-zinc-500">Waiting</span>;
  }

  const isFast = latency < 1000;

  return (
    <span
      className={`text-2xl font-semibold tabular-nums ${
        isFast ? "text-emerald-300" : "text-rose-300"
      }`}
    >
      {latency}ms{isFast ? " ✓" : ""}
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
    <section
      className={`min-h-[360px] border p-5 ${
        isWinner
          ? "border-emerald-400/60 bg-emerald-400/[0.04]"
          : "border-zinc-800 bg-zinc-950"
      }`}
    >
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            {eyebrow}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-white">{title}</h2>
        </div>
        <LatencyBadge latency={result?.latency_ms} />
      </div>

      {populated.length ? (
        <div className="space-y-3">
          {populated.map(([label, values]) => (
            <div key={label} className="grid grid-cols-[112px_1fr] gap-3">
              <span className="pt-1 text-xs text-zinc-500">{label}</span>
              <div className="flex flex-wrap gap-2">
                {values.map((value) => (
                  <span
                    key={`${label}-${value}`}
                    className={`border px-2.5 py-1 text-xs font-medium ${
                      labelStyles[label] ??
                      "border-zinc-700 bg-zinc-900 text-zinc-200"
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
        <div className="flex h-52 items-center justify-center border border-dashed border-zinc-800 text-sm text-zinc-500">
          Run an analysis to populate extracted entities.
        </div>
      )}
    </section>
  );
}

function KnowledgeCards({ cards }: { cards: TavilyCard[] }) {
  if (!cards.length) {
    return (
      <div className="border border-dashed border-zinc-800 p-8 text-center text-sm text-zinc-500">
        Medication verification cards will appear here after analysis.
      </div>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {cards.map((card) => (
        <article
          key={card.drug}
          className={`border p-4 ${
            card.warning
              ? "border-amber-400/70 bg-amber-500/[0.08]"
              : "border-zinc-800 bg-zinc-950"
          }`}
        >
          <div className="mb-3 flex items-start justify-between gap-3">
            <h3 className="text-base font-semibold text-white">{card.drug}</h3>
            {card.warning ? (
              <span className="border border-amber-400/40 px-2 py-0.5 text-xs font-semibold text-amber-200">
                Warning
              </span>
            ) : null}
          </div>
          <p className="text-sm leading-6 text-zinc-300">{card.indication}</p>
          {card.contraindications ? (
            <p className="mt-2 text-sm leading-6 text-zinc-400">
              <span className="text-zinc-500">Caution:</span>{" "}
              {card.contraindications}
            </p>
          ) : null}
          {card.warning ? (
            <p className="mt-3 border border-amber-400/30 bg-amber-400/10 p-3 text-sm leading-6 text-amber-100">
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
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("Ready");
  const [error, setError] = useState("");
  const sttRef = useRef<GradiumSTT | null>(null);

  async function analyzeTranscript(inputText = transcript) {
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
        }
      },
    });

    sttRef.current = stt;
    try {
      await stt.start();
      setIsRecording(true);
    } catch (err) {
      setIsRecording(false);
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
    setVoiceStatus("Ready");
    setTranscript("");
    setResults(null);
    setError("");
  }

  const activeResults = results;

  return (
    <main className="min-h-screen bg-[#080b0f] text-zinc-100">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-zinc-800 pb-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.22em] text-emerald-300">
              Privacy-first medical triage
            </p>
            <h1 className="mt-2 text-3xl font-semibold text-white">
              Pioneer-Med
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <span className="border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm text-zinc-300">
              Status: {isAnalyzing ? "Analyzing" : voiceStatus}
            </span>
            <button
              type="button"
              onClick={handleRecord}
              disabled={isAnalyzing}
              className={`px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400 ${
                isRecording
                  ? "bg-rose-400 text-zinc-950 hover:bg-rose-300"
                  : "border border-zinc-700 text-zinc-200 hover:border-zinc-500 hover:bg-zinc-900"
              }`}
            >
              {isRecording ? "Stop" : "Record"}
            </button>
            <button
              type="button"
              onClick={() => analyzeTranscript()}
              disabled={isAnalyzing}
              className="bg-emerald-400 px-4 py-2 text-sm font-semibold text-zinc-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
            >
              {isAnalyzing ? "Analyzing..." : "Analyze"}
            </button>
            <button
              type="button"
              onClick={clearTranscript}
              className="border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-900"
            >
              Clear
            </button>
          </div>
        </header>

        {error ? (
          <div className="border border-amber-400/40 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
            {error}
          </div>
        ) : null}

        {isAnalyzing ? (
          <div className="flex items-center gap-2 text-sm text-sky-300">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-sky-300 border-t-transparent" />
            <span>Analyzing transcript...</span>
          </div>
        ) : null}

        <section className="grid gap-5 xl:grid-cols-[0.85fr_1.15fr]">
          <div className="border border-zinc-800 bg-zinc-950 p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
                  Live transcript
                </p>
                <h2 className="mt-1 text-lg font-semibold text-white">
                  Patient History
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setTranscript(demoTranscript)}
                className="border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 transition hover:border-zinc-500 hover:bg-zinc-900"
              >
                Demo Text
              </button>
            </div>

            <textarea
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              placeholder="Type or paste the patient transcript here."
              className="h-[360px] w-full resize-none border border-zinc-800 bg-[#0c1117] p-4 text-base leading-7 text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-emerald-400/70"
            />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <EntityPanel
              title="Pioneer GLiNER2"
              eyebrow="Specialized NER"
              result={activeResults?.pioneer}
              isWinner={activeResults?.winner === "pioneer"}
            />
            <EntityPanel
              title="GPT-4o-mini"
              eyebrow="Cloud baseline"
              result={activeResults?.openai}
              isWinner={activeResults?.winner === "openai"}
            />
          </div>
        </section>

        <section className="border-t border-zinc-800 pt-5">
          <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
                Tavily verification
              </p>
              <h2 className="mt-1 text-xl font-semibold text-white">
                Medication Knowledge Cards
              </h2>
            </div>
            <p className="text-sm text-zinc-500">
              Using Pioneer medication extractions as the safety-check input.
            </p>
          </div>
          <KnowledgeCards cards={activeResults?.tavily_cards ?? []} />
        </section>
      </div>
    </main>
  );
}
