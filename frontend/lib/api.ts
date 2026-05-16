import type {
  CreatePatientPayload,
  CreateRecordingPayload,
  CreateRecordingResponse,
  CreateSessionPayload,
  Patient,
  SessionDetailResponse,
  TriageResponse,
  UpdateFollowUpQuestionPayload,
  WorkspaceResponse,
} from "../types";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${backendUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`Backend error: ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

export async function analyzeTriage(transcript: string): Promise<TriageResponse> {
  return requestJson<TriageResponse>("/triage", {
    method: "POST",
    body: JSON.stringify({ text: transcript }),
  });
}

export async function getWorkspace(): Promise<WorkspaceResponse> {
  return requestJson<WorkspaceResponse>("/workspace");
}

export async function getSession(sessionId: string): Promise<SessionDetailResponse> {
  return requestJson<SessionDetailResponse>(`/sessions/${sessionId}`);
}

export async function createPatient(payload: CreatePatientPayload): Promise<Patient> {
  return requestJson<Patient>("/patients", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createSession(
  patientId: string,
  payload: CreateSessionPayload,
): Promise<SessionDetailResponse> {
  return requestJson<SessionDetailResponse>(`/patients/${patientId}/sessions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function createRecording(
  sessionId: string,
  payload: CreateRecordingPayload,
): Promise<CreateRecordingResponse> {
  return requestJson<CreateRecordingResponse>(`/sessions/${sessionId}/recordings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateFollowUpQuestion(
  questionId: string,
  payload: UpdateFollowUpQuestionPayload,
): Promise<void> {
  await requestJson(`/follow-up-questions/${questionId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
