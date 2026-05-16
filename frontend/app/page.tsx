"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  analyzeTriage,
  createPatient,
  createRecording,
  createSession,
  getSession,
  getWorkspace,
  updateFollowUpQuestion,
} from "../lib/api";
import { GradiumSTT } from "../lib/gradium";
import type {
  Analysis,
  Doctor,
  EntityMap,
  ExtractionResult,
  FollowUpQuestion,
  Patient,
  Recording,
  SessionDetail,
  SessionDetailResponse,
  TavilyCard,
  TriageResponse,
  WorkspaceResponse,
} from "../types";

const demoTranscript =
  "I've had severe migraine for the past week and started taking Doliprane, but I am not sure about the dose.";

const emptyEntities: EntityMap = {
  Symptom: [],
  Medication: [],
  Dosage: [],
  "Medical History": [],
  "Anatomical Site": [],
  Duration: [],
  Frequency: [],
};

const demoDoctor: Doctor = {
  id: "doctor_demo",
  name: "Dr. Youssef",
  avatar_url: "/doctor-avatar.jpg",
};

const demoWorkspace: WorkspaceResponse = {
  doctor: demoDoctor,
  patients: [
    {
      id: "patient_1",
      name: "Youssef Amrani",
      age: 34,
      sex: "male",
      summary: "Migraine assessment",
      sessions: [
        {
          id: "session_1",
          title: "Migraine intake",
          status: "active",
          updated_at: new Date().toISOString(),
        },
      ],
    },
    {
      id: "patient_2",
      name: "Amal Benali",
      age: 42,
      sex: "female",
      summary: "Chest pain follow-up",
      sessions: [
        {
          id: "session_2",
          title: "Chest pain intake",
          status: "active",
          updated_at: "2026-05-16T12:00:00Z",
        },
      ],
    },
    {
      id: "patient_3",
      name: "Nora Haddad",
      age: 57,
      sex: "female",
      summary: "Medication review",
      sessions: [],
    },
  ],
};

const demoSessionDetails: Record<string, SessionDetailResponse> = {
  session_1: {
    session: {
      id: "session_1",
      patient_id: "patient_1",
      title: "Migraine intake",
      status: "active",
      summary: "Patient reports severe migraine for the past week and started Doliprane.",
    },
    recordings: [
      {
        id: "recording_demo_1",
        session_id: "session_1",
        transcript: demoTranscript,
        duration_seconds: 18,
        created_at: new Date(Date.now() - 1000 * 60 * 12).toISOString(),
      },
    ],
    analyses: [],
    follow_up_questions: [
      {
        id: "question_demo_1",
        question: "What dose of Doliprane did you take, and how often?",
        reason: "Medication dosage and frequency are missing.",
        priority: "high",
        answered: false,
      },
      {
        id: "question_demo_2",
        question: "Do you have nausea, vision changes, weakness, or fever?",
        reason: "Associated symptoms help identify red flags.",
        priority: "high",
        answered: false,
      },
      {
        id: "question_demo_3",
        question: "How severe is the migraine from 1 to 10?",
        reason: "Severity is not captured yet.",
        priority: "medium",
        answered: false,
      },
    ],
  },
  session_2: {
    session: {
      id: "session_2",
      patient_id: "patient_2",
      title: "Chest pain intake",
      status: "active",
      summary:
        "Patient previously described chest pain for three days with Lisinopril use and bypass surgery history.",
    },
    recordings: [],
    analyses: [],
    follow_up_questions: [],
  },
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

const priorityStyles: Record<string, string> = {
  high: "border-rose-200 bg-rose-50 text-rose-700",
  medium: "border-amber-200 bg-amber-50 text-amber-800",
  low: "border-zinc-200 bg-zinc-50 text-zinc-600",
};

const idleWaveformLevels = [
  0.18, 0.24, 0.14, 0.32, 0.42, 0.2, 0.28, 0.5, 0.68, 0.34, 0.24, 0.56,
  0.72, 0.38, 0.22, 0.3, 0.46, 0.28, 0.18, 0.34, 0.52, 0.6, 0.42, 0.24,
  0.18,
];

function formatTimer(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function sortSessions(sessions: Patient["sessions"]) {
  return [...sessions].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );
}

function normalizeAnalysis(input: TriageResponse): Analysis {
  return {
    pioneer: input.pioneer,
    pioneer_finetuned: input.pioneer_finetuned ?? null,
    openai: input.openai,
    tavily_cards: input.tavily_cards,
    winner: input.winner,
  };
}

function createFallbackQuestions(analysis: Analysis): FollowUpQuestion[] {
  const fineTunedEntities = analysis.pioneer_finetuned?.entities ?? {};
  const pioneerEntities = analysis.pioneer.entities;
  const openAiEntities = analysis.openai.entities;
  const medications = [
    ...(fineTunedEntities.Medication ?? []),
    ...(pioneerEntities.Medication ?? []),
    ...(openAiEntities.Medication ?? []),
  ];
  const symptoms = [
    ...(fineTunedEntities.Symptom ?? []),
    ...(pioneerEntities.Symptom ?? []),
    ...(openAiEntities.Symptom ?? []),
  ];

  const medication = medications[0] ?? "the medication";
  const symptom = symptoms[0] ?? "the main symptom";

  return [
    {
      id: `question_${Date.now()}_dosage`,
      question: `What dose of ${medication} are you taking, and how often?`,
      reason: "Medication dosage and frequency should be explicit before clinical handoff.",
      priority: "high",
      answered: false,
    },
    {
      id: `question_${Date.now()}_severity`,
      question: `How severe is ${symptom} from 1 to 10?`,
      reason: "Severity is missing from the current session context.",
      priority: "medium",
      answered: false,
    },
    {
      id: `question_${Date.now()}_red_flags`,
      question: "Any fever, weakness, chest pain, fainting, allergy, or breathing trouble?",
      reason: "Red flags and contraindications need to be screened.",
      priority: "high",
      answered: false,
    },
  ];
}

function summaryFromTranscript(transcript: string) {
  const trimmed = transcript.trim();
  if (!trimmed) {
    return "No session summary yet.";
  }
  return trimmed.length > 180 ? `${trimmed.slice(0, 177)}...` : trimmed;
}

function escapeHtml(value: string | number | null | undefined) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function mergeMedicationCards(analyses: Analysis[]): TavilyCard[] {
  const cards: TavilyCard[] = [];
  const seen = new Set<string>();

  for (const analysis of analyses) {
    for (const card of analysis.tavily_cards ?? []) {
      const key = card.drug.trim().toLocaleLowerCase();
      if (key && !seen.has(key)) {
        cards.push(card);
        seen.add(key);
      }
    }
  }

  return cards;
}

function MicIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-8 w-8"
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
  const center = Math.floor(sourceLevels.length / 2);

  return (
    <div className="flex h-16 items-center justify-center gap-1">
      {sourceLevels.map((level, index) => {
        const distance = Math.abs(index - center) / center;
        const weighted = Math.max(0.08, Math.min(1, level * (1 - distance * 0.62)));
        return (
          <span
            key={`${index}-${level}`}
            className={`w-1 rounded-full transition-all duration-75 ${
              active ? "bg-[#6e8f88]" : "bg-zinc-300"
            }`}
            style={{
              height: `${Math.max(8, Math.round(10 + weighted * 50))}px`,
              opacity: active ? Math.max(0.45, weighted) : 0.55,
            }}
          />
        );
      })}
    </div>
  );
}

function LatencyBadge({ latency }: { latency?: number }) {
  if (latency === undefined || latency === null) {
    return <span className="text-sm font-medium text-zinc-400">Waiting</span>;
  }

  return (
    <span
      className={`text-2xl font-semibold tabular-nums ${
        latency < 1000 ? "text-[#2d7b6f]" : "text-[#d56f60]"
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
  result?: ExtractionResult | null;
  isWinner?: boolean;
}) {
  const entities = result?.entities ?? emptyEntities;
  const populated = Object.entries(entities).filter(([, values]) => values.length);

  return (
    <article
      className={`rounded-2xl border bg-white p-4 shadow-sm ${
        isWinner ? "border-[#6e8f88] ring-4 ring-[#dbe9e4]" : "border-zinc-200"
      }`}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-zinc-400">
            {eyebrow}
          </p>
          <h3 className="mt-1 text-base font-semibold text-zinc-950">{title}</h3>
          {result?.provider ? (
            <p className="mt-1 truncate text-xs text-zinc-400">{result.provider}</p>
          ) : null}
        </div>
        <LatencyBadge latency={result?.latency_ms} />
      </div>

      {populated.length ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {populated.map(([label, values]) => (
            <div key={label} className="rounded-xl bg-zinc-50 p-3">
              <span className="text-xs font-semibold text-zinc-400">{label}</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {values.map((value) => (
                  <span
                    key={`${label}-${value}`}
                    className={`max-w-full rounded-full border px-3 py-1 text-xs font-medium leading-5 ${
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
        <div className="flex min-h-24 items-center justify-center rounded-xl border border-dashed border-zinc-200 bg-zinc-50 px-4 text-center text-sm text-zinc-400">
          Results will appear after analysis.
        </div>
      )}
    </article>
  );
}

function mergeAnalysisEntities(analyses: Analysis[]): EntityMap {
  const merged: EntityMap = Object.fromEntries(
    Object.keys(emptyEntities).map((label) => [label, []]),
  ) as EntityMap;
  const seen: Record<string, Set<string>> = Object.fromEntries(
    Object.keys(emptyEntities).map((label) => [label, new Set<string>()]),
  );

  for (const analysis of analyses) {
    const results = [analysis.pioneer_finetuned, analysis.pioneer, analysis.openai].filter(
      Boolean,
    ) as ExtractionResult[];

    for (const result of results) {
      for (const label of Object.keys(emptyEntities)) {
        for (const value of result.entities[label] ?? []) {
          const cleaned = value.replace(/\s+/g, " ").trim();
          const key = cleaned.toLocaleLowerCase();
          if (cleaned && !seen[label].has(key)) {
            merged[label].push(cleaned);
            seen[label].add(key);
          }
        }
      }
    }
  }

  for (const label of Object.keys(merged)) {
    const values = merged[label];
    merged[label] = values.filter((value, index) => {
      const normalized = value.toLocaleLowerCase();
      return !values.some((candidate, candidateIndex) => {
        if (candidateIndex === index) {
          return false;
        }
        const candidateNormalized = candidate.toLocaleLowerCase();
        return (
          candidateNormalized.length > normalized.length &&
          candidateNormalized.includes(normalized)
        );
      });
    });
  }

  return merged;
}

function SessionContextPanel({
  entities,
  recordingCount,
}: {
  entities: EntityMap;
  recordingCount: number;
}) {
  const populated = Object.entries(entities).filter(([, values]) => values.length);

  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
            Accumulated context
          </p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">
            Session Case View
          </h2>
        </div>
        <span className="rounded-full border border-zinc-200 px-3 py-1 text-xs font-semibold text-zinc-500">
          {recordingCount} recording{recordingCount === 1 ? "" : "s"}
        </span>
      </div>

      {populated.length ? (
        <div className="grid gap-3">
          {populated.map(([label, values]) => (
            <div key={label} className="rounded-xl bg-zinc-50 p-3">
              <span className="text-xs font-semibold text-zinc-400">{label}</span>
              <div className="mt-2 flex flex-wrap gap-2">
                {values.map((value, index) => (
                  <span
                    key={`${label}-${value}-${index}`}
                    className={`max-w-full rounded-full border px-3 py-1 text-xs font-medium leading-5 ${
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
        <div className="rounded-2xl border border-dashed border-zinc-200 bg-white/70 p-6 text-center text-sm text-zinc-400">
          Record patient answers to build the accumulated session context.
        </div>
      )}
    </section>
  );
}

function KnowledgeCards({ cards }: { cards: TavilyCard[] }) {
  if (!cards.length) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white/70 p-6 text-center text-sm text-zinc-400">
        No medication cards yet.
      </div>
    );
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {cards.map((card) => (
        <article
          key={`${card.drug}-${card.source ?? ""}`}
          className={`rounded-2xl border bg-white p-4 shadow-sm ${
            card.warning ? "border-[#f2b3a7]" : "border-zinc-200"
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-zinc-950">{card.drug}</h3>
              <p className="mt-1 text-sm leading-6 text-zinc-600">{card.indication}</p>
            </div>
            {card.warning ? (
              <span className="rounded-full bg-[#fff0ed] px-3 py-1 text-xs font-semibold text-[#c65f51]">
                Warning
              </span>
            ) : null}
          </div>
          {card.contraindications ? (
            <p className="mt-2 text-sm leading-6 text-zinc-500">
              <span className="font-medium text-zinc-700">Caution:</span>{" "}
              {card.contraindications}
            </p>
          ) : null}
          {card.warning ? (
            <p className="mt-3 rounded-xl bg-[#fff6f3] p-3 text-sm leading-6 text-[#994a41]">
              {card.warning}
            </p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function FollowUpList({
  questions,
  onToggle,
}: {
  questions: FollowUpQuestion[];
  onToggle: (question: FollowUpQuestion) => void;
}) {
  if (!questions.length) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white/70 p-6 text-center text-sm text-zinc-400">
        Follow-up questions will appear after the latest recording.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {questions.slice(0, 5).map((question) => (
        <article key={question.id} className="rounded-2xl border border-zinc-200 bg-white p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <span
                className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${
                  priorityStyles[question.priority] ?? priorityStyles.low
                }`}
              >
                {question.priority}
              </span>
              <h3 className="mt-3 text-sm font-semibold leading-6 text-zinc-950">
                {question.question}
              </h3>
              <p className="mt-1 text-sm leading-6 text-zinc-500">{question.reason}</p>
            </div>
            <button
              type="button"
              onClick={() => onToggle(question)}
              className={`flex shrink-0 items-center gap-2 rounded-full border py-1 pl-2 pr-1 text-xs font-semibold transition ${
                question.answered
                  ? "border-[#6e8f88] bg-[#eef6f3] text-[#557a72]"
                  : "border-zinc-200 bg-zinc-50 text-zinc-500"
              }`}
              aria-pressed={question.answered}
              aria-label={
                question.answered ? "Mark follow-up unanswered" : "Mark follow-up answered"
              }
            >
              <span>{question.answered ? "Done" : "Open"}</span>
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] shadow-sm transition ${
                  question.answered ? "bg-[#6e8f88] text-white" : "bg-white text-zinc-400"
                }`}
              >
                {question.answered ? "✓" : ""}
              </span>
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}

function Timeline({ recordings }: { recordings: Recording[] }) {
  if (!recordings.length) {
    return (
      <div className="rounded-2xl border border-dashed border-zinc-200 bg-white/70 p-6 text-center text-sm text-zinc-400">
        This session has no recordings yet.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {recordings.map((recording, index) => (
        <article key={recording.id} className="rounded-2xl border border-zinc-200 bg-white p-4">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-zinc-950">Recording {index + 1}</h3>
            <span className="text-xs text-zinc-400">{formatDateTime(recording.created_at)}</span>
          </div>
          <p className="mt-2 text-sm leading-6 text-zinc-600">{recording.transcript}</p>
          <p className="mt-3 text-xs font-medium text-zinc-400">
            Duration {formatTimer(recording.duration_seconds)}
          </p>
        </article>
      ))}
    </div>
  );
}

export default function Home() {
  const [doctor, setDoctor] = useState<Doctor>(demoDoctor);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string>("");
  const [selectedSessionId, setSelectedSessionId] = useState<string>("");
  const [sessionDetail, setSessionDetail] = useState<SessionDetail | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [followUpQuestions, setFollowUpQuestions] = useState<FollowUpQuestion[]>([]);
  const [transcript, setTranscript] = useState(demoTranscript);
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevels, setAudioLevels] = useState<number[]>([]);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [isLoadingWorkspace, setIsLoadingWorkspace] = useState(true);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [isCreatingPatient, setIsCreatingPatient] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("Ready");
  const [error, setError] = useState("");
  const [newSessionTitle, setNewSessionTitle] = useState("Follow-up intake");
  const [newPatientName, setNewPatientName] = useState("");
  const [newPatientAge, setNewPatientAge] = useState("");
  const [newPatientSex, setNewPatientSex] = useState("");
  const [newPatientSummary, setNewPatientSummary] = useState("");
  const sttRef = useRef<GradiumSTT | null>(null);

  const selectedPatient = patients.find((patient) => patient.id === selectedPatientId) ?? null;
  const latestAnalysis = analyses.length ? analyses[analyses.length - 1] : null;
  const accumulatedEntities = useMemo(() => mergeAnalysisEntities(analyses), [analyses]);
  const accumulatedMedicationCards = useMemo(() => mergeMedicationCards(analyses), [analyses]);
  const hasOpenQuestions = followUpQuestions.some((question) => !question.answered);
  const canGeneratePdf = recordings.length > 0 && !hasOpenQuestions;

  useEffect(() => {
    let cancelled = false;

    async function loadWorkspace() {
      setIsLoadingWorkspace(true);
      try {
        const data = await getWorkspace();
        if (cancelled) {
          return;
        }
        setDoctor(data.doctor);
        setPatients(data.patients);
        setError("");
        const firstPatient = data.patients[0];
        setSelectedPatientId(firstPatient?.id ?? "");
        setSelectedSessionId(sortSessions(firstPatient?.sessions ?? [])[0]?.id ?? "");
      } catch (err) {
        if (cancelled) {
          return;
        }
        setDoctor(demoWorkspace.doctor);
        setPatients(demoWorkspace.patients);
        setSelectedPatientId(demoWorkspace.patients[0]?.id ?? "");
        setSelectedSessionId(sortSessions(demoWorkspace.patients[0]?.sessions ?? [])[0]?.id ?? "");
        setError(
          err instanceof Error
            ? `${err.message}. Using local demo workspace until v1 backend endpoints are ready.`
            : "Using local demo workspace until v1 backend endpoints are ready.",
        );
      } finally {
        if (!cancelled) {
          setIsLoadingWorkspace(false);
        }
      }
    }

    void loadWorkspace();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isRecording) {
      return;
    }

    const interval = window.setInterval(() => {
      setRecordingSeconds((seconds) => seconds + 1);
    }, 1000);

    return () => window.clearInterval(interval);
  }, [isRecording]);

  useEffect(() => {
    let cancelled = false;

    async function loadSession() {
      if (!selectedSessionId) {
        setSessionDetail(null);
        setRecordings([]);
        setAnalyses([]);
        setFollowUpQuestions([]);
        return;
      }

      setIsLoadingSession(true);
      try {
        const data = await getSession(selectedSessionId);
        if (cancelled) {
          return;
        }
        setSessionDetail(data.session);
        setRecordings(data.recordings);
        setAnalyses(data.analyses);
        setFollowUpQuestions(data.follow_up_questions);
        setError("");
      } catch (err) {
        if (cancelled) {
          return;
        }
        const fallback = demoSessionDetails[selectedSessionId];
        if (fallback) {
          setSessionDetail(fallback.session);
          setRecordings(fallback.recordings);
          setAnalyses(fallback.analyses);
          setFollowUpQuestions(fallback.follow_up_questions);
        } else {
          const selectedSession = selectedPatient?.sessions.find(
            (session) => session.id === selectedSessionId,
          );
          setSessionDetail(
            selectedSession
              ? {
                  id: selectedSession.id,
                  patient_id: selectedPatientId,
                  title: selectedSession.title,
                  status: selectedSession.status,
                  summary: null,
                }
              : null,
          );
          setRecordings([]);
          setAnalyses([]);
          setFollowUpQuestions([]);
        }
        setError(
          err instanceof Error
            ? `${err.message}. Showing demo session data until v1 backend endpoints are ready.`
            : "Showing demo session data until v1 backend endpoints are ready.",
        );
      } finally {
        if (!cancelled) {
          setIsLoadingSession(false);
        }
      }
    }

    void loadSession();
    return () => {
      cancelled = true;
    };
  }, [selectedPatient?.sessions, selectedPatientId, selectedSessionId]);

  const sessionOptions = useMemo(
    () => sortSessions(selectedPatient?.sessions ?? []),
    [selectedPatient?.sessions],
  );

  function selectPatient(patient: Patient) {
    setSelectedPatientId(patient.id);
    setSelectedSessionId(sortSessions(patient.sessions)[0]?.id ?? "");
    setNewSessionTitle("New appointment");
    setTranscript("");
    setRecordingSeconds(0);
  }

  async function handleCreatePatient() {
    const name = newPatientName.trim();
    if (!name) {
      setError("Add a patient name before creating a patient.");
      return;
    }

    setIsCreatingPatient(true);
    setError("");

    try {
      const patient = await createPatient({
        name,
        age: newPatientAge.trim() ? Number(newPatientAge) : undefined,
        sex: newPatientSex.trim() || undefined,
        summary: newPatientSummary.trim() || "New patient",
      });
      const normalizedPatient = { ...patient, sessions: patient.sessions ?? [] };
      setPatients((items) => [normalizedPatient, ...items]);
      setSelectedPatientId(normalizedPatient.id);
      setSelectedSessionId("");
      setSessionDetail(null);
      setRecordings([]);
      setAnalyses([]);
      setFollowUpQuestions([]);
      setNewPatientName("");
      setNewPatientAge("");
      setNewPatientSex("");
      setNewPatientSummary("");
      setNewSessionTitle("Initial appointment");
    } catch (err) {
      const localPatient: Patient = {
        id: `patient_${Date.now()}`,
        name,
        age: newPatientAge.trim() ? Number(newPatientAge) : null,
        sex: newPatientSex.trim() || null,
        summary: newPatientSummary.trim() || "New patient",
        sessions: [],
      };
      setPatients((items) => [localPatient, ...items]);
      setSelectedPatientId(localPatient.id);
      setSelectedSessionId("");
      setSessionDetail(null);
      setRecordings([]);
      setAnalyses([]);
      setFollowUpQuestions([]);
      setError(
        err instanceof Error
          ? `${err.message}. Created a local patient until the backend is ready.`
          : "Created a local patient until the backend is ready.",
      );
    } finally {
      setIsCreatingPatient(false);
    }
  }

  async function handleCreateSession() {
    if (!selectedPatient) {
      setError("Select a patient before creating a session.");
      return;
    }

    const title = newSessionTitle.trim() || "New intake session";
    setIsCreatingSession(true);
    setError("");

    try {
      const detail = await createSession(selectedPatient.id, {
        title,
        status: "active",
        summary: "Awaiting first recording.",
      });
      const createdSession = {
        id: detail.session.id,
        title: detail.session.title,
        status: detail.session.status,
        updated_at: new Date().toISOString(),
      };
      setPatients((items) =>
        items.map((patient) =>
          patient.id === selectedPatient.id
            ? { ...patient, sessions: [createdSession, ...patient.sessions] }
            : patient,
        ),
      );
      setSelectedSessionId(detail.session.id);
      setSessionDetail(detail.session);
      setRecordings(detail.recordings);
      setAnalyses(detail.analyses);
      setFollowUpQuestions(detail.follow_up_questions);
      setNewSessionTitle("New appointment");
    } catch (err) {
      const fallbackSession = {
        id: `session_${Date.now()}`,
        title,
        status: "active",
        updated_at: new Date().toISOString(),
      };
      setPatients((items) =>
        items.map((patient) =>
          patient.id === selectedPatient.id
            ? { ...patient, sessions: [fallbackSession, ...patient.sessions] }
            : patient,
        ),
      );
      setSelectedSessionId(fallbackSession.id);
      setSessionDetail({
        id: fallbackSession.id,
        patient_id: selectedPatient.id,
        title: fallbackSession.title,
        status: fallbackSession.status,
        summary: "Awaiting first recording.",
      });
      setRecordings([]);
      setAnalyses([]);
      setFollowUpQuestions([]);
      setError(
        err instanceof Error
          ? `${err.message}. Created a local session until the backend is ready.`
          : "Created a local session until the backend is ready.",
      );
    } finally {
      setIsCreatingSession(false);
    }
  }

  function stopRecording() {
    sttRef.current?.stop();
    setIsRecording(false);
    setAudioLevels([]);
    setVoiceStatus("Ready");
  }

  async function handleRecord() {
    if (isRecording) {
      stopRecording();
      return;
    }

    setTranscript("");
    setError("");
    setRecordingSeconds(0);
    setAudioLevels([]);
    setVoiceStatus("Connecting");

    const stt = new GradiumSTT({
      onChunk: (text) => setTranscript(text),
      onFinal: (text) => {
        setIsRecording(false);
        setAudioLevels([]);
        setVoiceStatus("Ready");
        if (text.trim()) {
          setTranscript(text);
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
          ? `${err.message}. You can still type and send a transcript.`
          : "Voice input failed. You can still type and send a transcript.",
      );
    }
  }

  async function sendRecording(inputText = transcript) {
    if (isRecording) {
      stopRecording();
    }

    const text = inputText.trim();
    if (!text) {
      setError("Add a transcript before sending.");
      return;
    }
    if (!selectedSessionId) {
      setError("Select a session before sending a recording.");
      return;
    }

    setIsAnalyzing(true);
    setError("");

    try {
      const response = await createRecording(selectedSessionId, {
        transcript: text,
        duration_seconds: Math.max(recordingSeconds, 1),
      });
      setRecordings((items) => [...items, response.recording]);
      setAnalyses((items) => [...items, response.analysis]);
      setSessionDetail((current) =>
        current ? { ...current, summary: response.session_summary } : current,
      );
      setFollowUpQuestions(response.follow_up_questions);
      setTranscript("");
      setRecordingSeconds(0);
    } catch (err) {
      try {
        const triage = await analyzeTriage(text);
        const analysis = normalizeAnalysis(triage);
        const recording: Recording = {
          id: `recording_${Date.now()}`,
          session_id: selectedSessionId,
          transcript: text,
          duration_seconds: Math.max(recordingSeconds, 1),
          created_at: new Date().toISOString(),
        };
        setRecordings((items) => [...items, recording]);
        setAnalyses((items) => [...items, analysis]);
        setSessionDetail((current) =>
          current ? { ...current, summary: summaryFromTranscript(text) } : current,
        );
        setFollowUpQuestions(createFallbackQuestions(analysis));
        setTranscript("");
        setRecordingSeconds(0);
        setError(
          "Workspace recording endpoint is not ready yet, so this recording was analyzed through /triage.",
        );
      } catch {
        setError(
          err instanceof Error
            ? `${err.message}. Could not analyze the recording.`
            : "Could not analyze the recording.",
        );
      }
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function toggleQuestion(question: FollowUpQuestion) {
    const nextAnswered = !question.answered;
    setFollowUpQuestions((items) =>
      items.map((item) =>
        item.id === question.id ? { ...item, answered: nextAnswered } : item,
      ),
    );

    try {
      await updateFollowUpQuestion(question.id, { answered: nextAnswered });
    } catch {
      setError("Follow-up answer saved locally until the backend endpoint is ready.");
    }
  }

  function generateSessionPdf() {
    if (!selectedPatient || !sessionDetail || !canGeneratePdf) {
      return;
    }

    const entityRows = Object.entries(accumulatedEntities)
      .filter(([, values]) => values.length)
      .map(
        ([label, values]) => `
          <tr>
            <th>${escapeHtml(label)}</th>
            <td>${values.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}</td>
          </tr>
        `,
      )
      .join("");

    const medicationRows = accumulatedMedicationCards.length
      ? accumulatedMedicationCards
          .map(
            (card) => `
              <div class="note">
                <strong>${escapeHtml(card.drug)}</strong>
                <p>${escapeHtml(card.indication)}</p>
                ${
                  card.contraindications
                    ? `<p><b>Caution:</b> ${escapeHtml(card.contraindications)}</p>`
                    : ""
                }
                ${card.warning ? `<p><b>Warning:</b> ${escapeHtml(card.warning)}</p>` : ""}
              </div>
            `,
          )
          .join("")
      : '<p class="muted">No medication verification cards were generated.</p>';

    const recordingRows = recordings
      .map(
        (recording, index) => `
          <div class="recording">
            <div class="row">
              <strong>Recording ${index + 1}</strong>
              <span>${escapeHtml(formatDateTime(recording.created_at))} - ${escapeHtml(
                formatTimer(recording.duration_seconds),
              )}</span>
            </div>
            <p>${escapeHtml(recording.transcript)}</p>
          </div>
        `,
      )
      .join("");

    const questionRows = followUpQuestions.length
      ? followUpQuestions
          .map(
            (question) => `
              <li>
                <strong>[${question.answered ? "answered" : "open"}] ${escapeHtml(
                  question.question,
                )}</strong>
                <span>${escapeHtml(question.reason)}</span>
              </li>
            `,
          )
          .join("")
      : '<li><strong>No unresolved follow-up questions.</strong><span>The case context is ready for export.</span></li>';

    const reportWindow = window.open("", "_blank", "width=900,height=1100");
    if (!reportWindow) {
      setError("Allow pop-ups to generate the PDF report.");
      return;
    }

    reportWindow.document.write(`
      <!doctype html>
      <html>
        <head>
          <title>MediCheck Session Report - ${escapeHtml(selectedPatient.name)}</title>
          <style>
            * { box-sizing: border-box; }
            body {
              margin: 0;
              background: #f7f7f3;
              color: #171717;
              font-family: Arial, Helvetica, sans-serif;
              line-height: 1.5;
            }
            main {
              width: 820px;
              margin: 32px auto;
              background: #ffffff;
              border: 1px solid #deded9;
              border-radius: 18px;
              padding: 40px;
            }
            .eyebrow {
              color: #6e8f88;
              font-size: 12px;
              font-weight: 700;
              letter-spacing: 0.24em;
              text-transform: uppercase;
            }
            h1 { margin: 8px 0 0; font-size: 32px; }
            h2 {
              margin: 28px 0 12px;
              font-size: 18px;
              border-bottom: 1px solid #e5e5e0;
              padding-bottom: 8px;
            }
            .meta {
              display: grid;
              grid-template-columns: repeat(2, minmax(0, 1fr));
              gap: 12px;
              margin-top: 24px;
            }
            .meta div, .note, .recording {
              border: 1px solid #e5e5e0;
              border-radius: 12px;
              padding: 12px;
              background: #fbfbf8;
            }
            .label {
              display: block;
              color: #71717a;
              font-size: 11px;
              font-weight: 700;
              letter-spacing: 0.14em;
              text-transform: uppercase;
            }
            table { width: 100%; border-collapse: collapse; }
            th, td {
              border-bottom: 1px solid #ecece7;
              padding: 12px 0;
              text-align: left;
              vertical-align: top;
            }
            th { width: 180px; color: #71717a; }
            td span {
              display: inline-block;
              margin: 0 6px 6px 0;
              border: 1px solid #cde3dc;
              border-radius: 999px;
              padding: 4px 10px;
              color: #315f56;
              background: #f0f7f4;
              font-size: 12px;
              font-weight: 700;
            }
            .note, .recording { margin-bottom: 10px; }
            .note p, .recording p { margin: 6px 0 0; color: #3f3f46; }
            .row {
              display: flex;
              justify-content: space-between;
              gap: 16px;
              color: #71717a;
              font-size: 12px;
            }
            ul { margin: 0; padding-left: 20px; }
            li { margin-bottom: 10px; }
            li span { display: block; color: #71717a; }
            .muted { color: #71717a; }
            .footer {
              margin-top: 32px;
              color: #71717a;
              font-size: 11px;
            }
            @media print {
              body { background: white; }
              main {
                width: auto;
                margin: 0;
                border: 0;
                border-radius: 0;
                padding: 0;
              }
            }
          </style>
        </head>
        <body>
          <main>
            <div class="eyebrow">MediCheck Clinical Session Note</div>
            <h1>${escapeHtml(sessionDetail.title)}</h1>

            <section class="meta">
              <div><span class="label">Patient</span>${escapeHtml(selectedPatient.name)}</div>
              <div><span class="label">Clinician</span>${escapeHtml(doctor.name)}</div>
              <div><span class="label">Patient profile</span>${escapeHtml(
                [selectedPatient.age, selectedPatient.sex].filter(Boolean).join(" - ") ||
                  "Not specified",
              )}</div>
              <div><span class="label">Generated</span>${escapeHtml(
                new Date().toLocaleString(),
              )}</div>
              <div><span class="label">Session status</span>${escapeHtml(
                sessionDetail.status,
              )}</div>
              <div><span class="label">Recordings</span>${recordings.length}</div>
            </section>

            <h2>Accumulated Clinical Context</h2>
            ${
              entityRows
                ? `<table><tbody>${entityRows}</tbody></table>`
                : '<p class="muted">No structured entities were extracted.</p>'
            }

            <h2>Medication Safety Notes</h2>
            ${medicationRows}

            <h2>Recording Timeline</h2>
            ${recordingRows}

            <h2>Follow-up Questions</h2>
            <ul>${questionRows}</ul>

            <p class="footer">
              Generated by MediCheck from recorded session transcripts and model-assisted extraction.
              This document is a clinical support artifact and should be reviewed by the clinician before being stored in the medical record.
            </p>
          </main>
          <script>
            window.addEventListener("load", () => {
              window.print();
            });
          </script>
        </body>
      </html>
    `);
    reportWindow.document.close();
  }

  return (
    <main className="min-h-screen bg-[#f7f7f3] text-zinc-950">
      <div className="grid min-h-screen lg:grid-cols-[320px_1fr]">
        <aside className="border-r border-zinc-200 bg-white/80 p-5">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#6e8f88]">
              MediCheck
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950">
              Patient Workspace
            </h1>
          </div>

          <section className="mb-5 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
            <div className="mb-3">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                New patient
              </p>
              <h2 className="mt-1 text-sm font-semibold text-zinc-950">
                Add a client
              </h2>
            </div>
            <div className="space-y-2">
              <input
                value={newPatientName}
                onChange={(event) => setNewPatientName(event.target.value)}
                className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                placeholder="Patient name"
              />
              <div className="grid grid-cols-2 gap-2">
                <input
                  value={newPatientAge}
                  onChange={(event) => setNewPatientAge(event.target.value)}
                  className="min-w-0 rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                  inputMode="numeric"
                  placeholder="Age"
                />
                <input
                  value={newPatientSex}
                  onChange={(event) => setNewPatientSex(event.target.value)}
                  className="min-w-0 rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                  placeholder="Sex"
                />
              </div>
              <input
                value={newPatientSummary}
                onChange={(event) => setNewPatientSummary(event.target.value)}
                className="w-full rounded-xl border border-zinc-200 px-3 py-2 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                placeholder="Short reason for visit"
              />
              <button
                type="button"
                onClick={handleCreatePatient}
                disabled={isCreatingPatient}
                className="w-full rounded-xl bg-zinc-950 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
              >
                {isCreatingPatient ? "Adding..." : "Add Patient"}
              </button>
            </div>
          </section>

          {isLoadingWorkspace ? (
            <div className="rounded-2xl border border-zinc-200 bg-white p-4 text-sm text-zinc-500">
              Loading workspace...
            </div>
          ) : null}

          {!isLoadingWorkspace && !patients.length ? (
            <div className="rounded-2xl border border-dashed border-zinc-200 bg-white p-5 text-sm text-zinc-500">
              No patients yet.
            </div>
          ) : null}

          <div className="space-y-3">
            {patients.map((patient) => {
              const isSelected = patient.id === selectedPatientId;
              return (
                <section
                  key={patient.id}
                  className={`rounded-2xl border p-3 transition ${
                    isSelected
                      ? "border-[#6e8f88] bg-[#eef6f3]"
                      : "border-zinc-200 bg-white hover:border-zinc-300"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => selectPatient(patient)}
                    className="w-full text-left"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h2 className="text-sm font-semibold text-zinc-950">{patient.name}</h2>
                        <p className="mt-1 text-xs text-zinc-500">
                          {[patient.age, patient.sex].filter(Boolean).join(" · ") ||
                            "Patient profile"}
                        </p>
                      </div>
                      <span className="rounded-full bg-white px-2.5 py-1 text-xs font-semibold text-[#6e8f88]">
                        {patient.sessions.length}
                      </span>
                    </div>
                    {patient.summary ? (
                      <p className="mt-2 line-clamp-2 text-xs leading-5 text-zinc-500">
                        {patient.summary}
                      </p>
                    ) : null}
                  </button>

                  {isSelected ? (
                    <div className="mt-3 space-y-2">
                      {sessionOptions.length ? (
                        sessionOptions.map((session) => (
                          <button
                            key={session.id}
                            type="button"
                            onClick={() => setSelectedSessionId(session.id)}
                            className={`w-full rounded-xl border px-3 py-2 text-left transition ${
                              session.id === selectedSessionId
                                ? "border-[#6e8f88] bg-white text-zinc-950"
                                : "border-transparent bg-white/60 text-zinc-500 hover:bg-white"
                            }`}
                          >
                            <span className="block text-xs font-semibold">{session.title}</span>
                            <span className="mt-1 block text-xs text-zinc-400">
                              {formatDateTime(session.updated_at)}
                            </span>
                          </button>
                        ))
                      ) : (
                        <div className="rounded-xl border border-dashed border-zinc-200 bg-white/70 p-3 text-xs text-zinc-500">
                          No sessions yet. Create one from the workspace panel.
                        </div>
                      )}
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
        </aside>

        <section className="min-w-0 p-5 lg:p-8">
          <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                {selectedPatient?.name ?? "No patient selected"}
              </p>
              <h2 className="mt-1 text-3xl font-semibold tracking-tight text-zinc-950">
                {sessionDetail?.title ?? "Select a session"}
              </h2>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              {selectedPatient ? (
                <div className="flex w-full gap-2 sm:w-auto">
                  <input
                    value={newSessionTitle}
                    onChange={(event) => setNewSessionTitle(event.target.value)}
                    className="min-w-0 flex-1 rounded-full border border-zinc-200 bg-white px-4 py-2.5 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88] sm:w-56"
                    placeholder="Appointment title"
                  />
                  <button
                    type="button"
                    onClick={handleCreateSession}
                    disabled={isCreatingSession}
                    className="rounded-full bg-zinc-950 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
                  >
                    {isCreatingSession ? "Creating..." : "New Session"}
                  </button>
                </div>
              ) : null}

              <div className="flex items-center gap-3 rounded-2xl border border-zinc-200 bg-white px-4 py-3 shadow-sm">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#e8f1ee] text-sm font-semibold text-[#426d63]">
                  {doctor.name
                    .split(" ")
                    .map((part) => part[0])
                    .join("")
                    .slice(0, 2)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-zinc-950">{doctor.name}</p>
                  <p className="text-xs text-zinc-400">Logged in</p>
                </div>
              </div>
            </div>
          </header>

          {error ? (
            <div className="mb-6 rounded-2xl border border-[#f1c0b6] bg-[#fff6f3] px-5 py-4 text-sm text-[#994a41]">
              {error}
            </div>
          ) : null}

          {!selectedPatient ? (
            <div className="rounded-2xl border border-dashed border-zinc-200 bg-white p-10 text-center text-sm text-zinc-400">
              No patient selected.
            </div>
          ) : !selectedSessionId ? (
            <div className="rounded-2xl border border-dashed border-zinc-200 bg-white p-8 text-center">
              <p className="text-sm font-semibold text-zinc-950">
                This patient has no session yet.
              </p>
              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-zinc-500">
                Create an intake session to start recording, analyzing, and tracking
                follow-up questions for {selectedPatient.name}.
              </p>
              <div className="mx-auto mt-5 flex max-w-md flex-col gap-3 sm:flex-row">
                <input
                  value={newSessionTitle}
                  onChange={(event) => setNewSessionTitle(event.target.value)}
                  className="min-w-0 flex-1 rounded-full border border-zinc-200 px-4 py-2.5 text-sm text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                  placeholder="Session title"
                />
                <button
                  type="button"
                  onClick={handleCreateSession}
                  disabled={isCreatingSession}
                  className="rounded-full bg-zinc-950 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-300"
                >
                  {isCreatingSession ? "Creating..." : "Create Session"}
                </button>
              </div>
            </div>
          ) : (
            <div className="grid gap-6 xl:grid-cols-[430px_1fr]">
              <div className="space-y-6">
                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
                  <div className="rounded-2xl bg-[#f9faf8] p-5">
                    <div className="flex flex-col items-center">
                      <button
                        type="button"
                        onClick={handleRecord}
                        disabled={isAnalyzing}
                        aria-label={isRecording ? "Stop recording" : "Start recording"}
                        className={`relative flex h-24 w-24 items-center justify-center rounded-full transition disabled:cursor-not-allowed ${
                          isRecording
                            ? "bg-[#e8f1ee] text-[#426d63]"
                            : "bg-[#eef2ef] text-[#6e8f88] hover:bg-[#e7eee9]"
                        }`}
                      >
                        {isRecording ? (
                          <span className="absolute h-full w-full animate-ping rounded-full bg-[#dbe9e4]" />
                        ) : null}
                        <span className="relative flex h-16 w-16 items-center justify-center rounded-full bg-white shadow-sm">
                          <MicIcon />
                        </span>
                      </button>

                      <p className="mt-4 text-2xl font-semibold tabular-nums text-[#5d7973]">
                        {formatTimer(recordingSeconds)}
                      </p>
                      <Waveform active={isRecording} levels={audioLevels} />

                      <div className="mt-3 flex w-full items-center justify-between gap-3">
                        <span className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-500">
                          {isAnalyzing ? "Analyzing" : voiceStatus}
                        </span>
                        <button
                          type="button"
                          onClick={() => sendRecording()}
                          disabled={isAnalyzing}
                          className="flex h-12 w-12 items-center justify-center rounded-full bg-[#ee8b7b] text-white shadow-sm transition hover:bg-[#e17c6d] disabled:cursor-not-allowed disabled:bg-zinc-300"
                          aria-label="Send recording"
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
                          Transcript editor
                        </p>
                        <h2 className="mt-1 text-lg font-semibold text-zinc-950">
                          Current Recording
                        </h2>
                      </div>
                      <button
                        type="button"
                        onClick={() => setTranscript(demoTranscript)}
                        className="rounded-full border border-zinc-200 px-3 py-1.5 text-xs font-semibold text-zinc-600 transition hover:border-zinc-300"
                      >
                        Demo
                      </button>
                    </div>
                    <textarea
                      value={transcript}
                      onChange={(event) => setTranscript(event.target.value)}
                      placeholder="Type, paste, or record the patient's answer."
                      className="min-h-44 w-full resize-y rounded-2xl border border-zinc-200 bg-white p-4 text-base leading-7 text-zinc-800 outline-none transition placeholder:text-zinc-400 focus:border-[#6e8f88]"
                    />
                  </div>
                </section>

                <SessionContextPanel
                  entities={accumulatedEntities}
                  recordingCount={recordings.length}
                />

                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
                  <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                        Follow-up questions
                      </p>
                      <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">
                        Missing Context
                      </h2>
                      {!canGeneratePdf ? (
                        <p className="mt-1 text-xs text-zinc-400">
                          Answer all open questions to enable the session PDF.
                        </p>
                      ) : null}
                    </div>
                    <button
                      type="button"
                      onClick={generateSessionPdf}
                      disabled={!canGeneratePdf}
                      className="rounded-full bg-[#6e8f88] px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-[#5d7f77] disabled:cursor-not-allowed disabled:bg-zinc-300"
                    >
                      Generate PDF
                    </button>
                  </div>
                  <FollowUpList questions={followUpQuestions} onToggle={toggleQuestion} />
                </section>
              </div>

              <div className="space-y-6">
                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                        Session timeline
                      </p>
                      <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">
                        Recordings
                      </h2>
                    </div>
                    {isLoadingSession ? (
                      <span className="text-sm text-[#6e8f88]">Loading...</span>
                    ) : null}
                  </div>
                  <Timeline recordings={recordings} />
                </section>

                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
                  <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                        Model extraction
                      </p>
                      <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">
                        Latest Recording Analysis
                      </h2>
                    </div>
                    {isAnalyzing ? (
                      <div className="flex items-center gap-2 text-sm text-[#6e8f88]">
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-[#6e8f88] border-t-transparent" />
                        <span>Analyzing...</span>
                      </div>
                    ) : null}
                  </div>

                  <div className="grid gap-4">
                    <EntityPanel
                      title="Pioneer Zero-shot"
                      eyebrow="GLiNER2"
                      result={latestAnalysis?.pioneer}
                      isWinner={latestAnalysis?.winner === "pioneer"}
                    />
                    <EntityPanel
                      title="Pioneer Fine-tuned"
                      eyebrow="Medical GLiNER2"
                      result={latestAnalysis?.pioneer_finetuned}
                      isWinner={latestAnalysis?.winner === "pioneer_finetuned"}
                    />
                    <EntityPanel
                      title="GPT-4o-mini"
                      eyebrow="Cloud baseline"
                      result={latestAnalysis?.openai}
                      isWinner={latestAnalysis?.winner === "openai"}
                    />
                  </div>
                </section>

                <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-zinc-200">
                  <div className="mb-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-zinc-400">
                      Tavily verification
                    </p>
                    <h2 className="mt-1 text-xl font-semibold tracking-tight text-zinc-950">
                      Medication Cards
                    </h2>
                  </div>
                  <KnowledgeCards cards={latestAnalysis?.tavily_cards ?? []} />
                </section>
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
