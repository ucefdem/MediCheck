export interface Entity {
  text: string;
  label: string;
  score: number;
  start: number;
  end: number;
}

export type EntityMap = Record<string, string[]>;

export interface ExtractionResult {
  entities: EntityMap;
  latency_ms: number;
  provider?: string | null;
}

export interface TavilyCard {
  drug: string;
  indication: string;
  contraindications: string;
  warning?: string | null;
  source?: string;
}

export interface TriageResponse {
  pioneer: ExtractionResult;
  pioneer_finetuned?: ExtractionResult | null;
  openai: ExtractionResult;
  tavily_cards: TavilyCard[];
  transcript: string;
  winner?: string;
}

export interface Doctor {
  id: string;
  name: string;
  avatar_url?: string | null;
}

export interface PatientSession {
  id: string;
  title: string;
  status: "active" | "closed" | string;
  updated_at: string;
}

export interface Patient {
  id: string;
  name: string;
  age?: number | null;
  sex?: string | null;
  summary?: string | null;
  sessions: PatientSession[];
}

export interface Recording {
  id: string;
  session_id: string;
  transcript: string;
  duration_seconds: number;
  created_at: string;
}

export interface Analysis {
  pioneer: ExtractionResult;
  pioneer_finetuned?: ExtractionResult | null;
  openai: ExtractionResult;
  tavily_cards: TavilyCard[];
  winner?: string;
}

export interface FollowUpQuestion {
  id: string;
  question: string;
  reason: string;
  priority: "high" | "medium" | "low" | string;
  answered: boolean;
}

export interface WorkspaceResponse {
  doctor: Doctor;
  patients: Patient[];
}

export interface SessionDetail {
  id: string;
  patient_id: string;
  title: string;
  status: "active" | "closed" | string;
  summary?: string | null;
}

export interface SessionDetailResponse {
  session: SessionDetail;
  recordings: Recording[];
  analyses: Analysis[];
  follow_up_questions: FollowUpQuestion[];
}

export interface CreateRecordingResponse {
  recording: Recording;
  analysis: Analysis;
  session_summary: string;
  follow_up_questions: FollowUpQuestion[];
}

export interface CreatePatientPayload {
  name: string;
  age?: number;
  sex?: string;
  summary?: string;
}

export interface CreateSessionPayload {
  title: string;
  status?: string;
  summary?: string;
}

export interface CreateRecordingPayload {
  transcript: string;
  duration_seconds: number;
}

export interface UpdateFollowUpQuestionPayload {
  answered: boolean;
}
