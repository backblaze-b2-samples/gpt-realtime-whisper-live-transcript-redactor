import type {
  DailySessionCount,
  DailyUploadCount,
  ExportFormat,
  ExportInfo,
  FileMetadata,
  FileUploadResponse,
  Glossary,
  SessionManifest,
  SessionStartRequest,
  SessionStartResponse,
  SessionStats,
  SessionSummary,
  Transcript,
  UploadStats,
} from "@gpt-realtime-whisper-live-transcript-redactor/shared";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Typed API error with HTTP status code for caller-side branching. */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }

  /** True for 408, 429, 500, 502, 503, 504 — worth retrying. */
  get isRetryable(): boolean {
    return [408, 429, 500, 502, 503, 504].includes(this.status);
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  get isConflict(): boolean {
    return this.status === 409;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError("Network error — check your connection", 0);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(body.detail || `API error: ${res.status}`, res.status);
  }
  return res.json();
}

// --- Health / files (kept from starter) ----------------------------------

export async function getHealth() {
  return apiFetch<{
    status: string;
    b2_connected: boolean;
    openai_reachable: boolean;
  }>("/health");
}

export async function getFiles(prefix = "", limit = 100) {
  return apiFetch<FileMetadata[]>(
    `/files?prefix=${encodeURIComponent(prefix)}&limit=${limit}`,
  );
}

export async function getFileStats() {
  return apiFetch<UploadStats>("/files/stats");
}

export async function getUploadActivity(days = 7) {
  return apiFetch<DailyUploadCount[]>(`/files/stats/activity?days=${days}`);
}

export async function getFile(key: string) {
  return apiFetch<FileMetadata>(`/files/${key}`);
}

export async function getDownloadUrl(key: string) {
  return apiFetch<{ url: string }>(`/files/${key}/download`);
}

export async function getPreviewUrl(key: string) {
  return apiFetch<{ url: string }>(`/files/${key}/preview`);
}

export async function deleteFile(key: string) {
  return apiFetch<{ deleted: boolean; key: string }>(`/files/${key}`, {
    method: "DELETE",
  });
}

export function uploadFile(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<FileUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(new ApiError(body.detail || `Upload failed: ${xhr.status}`, xhr.status));
        } catch {
          reject(new ApiError(`Upload failed: ${xhr.status}`, xhr.status));
        }
      }
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error — check your connection", 0)),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError("Upload aborted", 0)),
    );

    xhr.open("POST", `${API_BASE}/upload`);
    xhr.send(formData);
  });
}

// --- Sessions / redaction / exports / glossary ---------------------------

export async function startSession(body: SessionStartRequest) {
  return apiFetch<SessionStartResponse>("/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function listSessions(limit = 100) {
  return apiFetch<SessionSummary[]>(`/sessions?limit=${limit}`);
}

export async function getSession(sessionId: string) {
  return apiFetch<SessionManifest>(`/sessions/${sessionId}`);
}

export async function getSessionTranscript(sessionId: string) {
  return apiFetch<Transcript>(`/sessions/${sessionId}/transcript`);
}

export async function deleteSession(sessionId: string) {
  return apiFetch<{
    deleted: boolean;
    session_id: string;
    objects_removed: number;
  }>(`/sessions/${sessionId}`, { method: "DELETE" });
}

export async function getSessionStats() {
  return apiFetch<SessionStats>("/sessions/stats");
}

export async function getSessionActivity(days = 7) {
  return apiFetch<DailySessionCount[]>(`/sessions/stats/activity?days=${days}`);
}

export async function generateExport(sessionId: string, format: ExportFormat) {
  return apiFetch<ExportInfo>(`/sessions/${sessionId}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
}

export async function getGlossary() {
  return apiFetch<Glossary>("/glossary");
}

export async function saveGlossary(glossary: Glossary) {
  return apiFetch<Glossary>("/glossary", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(glossary),
  });
}

export function realtimeSessionUrl(sessionId: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/ws/sessions/${sessionId}`;
}

/**
 * Pipeline-mode file upload — streams the uploaded audio through the
 * same realtime stack `/record` uses and resolves with the finalized
 * session id when the bundle is durable.
 *
 * v1 accepts WAV only (see `service/audio_decode.py`). Progress callback
 * reports XHR upload progress; the server-side realtime drain happens
 * after the bytes land, so the progress hits 100% before the response
 * arrives.
 */
export interface SessionUploadResponse {
  session_id: string;
  segment_count: number;
  detection_count: number;
  duration_ms_received: number;
}

export function uploadSessionAudio(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<SessionUploadResponse> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("file", file);

    xhr.upload.addEventListener("progress", (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new ApiError("Malformed server response", xhr.status));
        }
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(
            new ApiError(
              body.detail || `Upload failed: ${xhr.status}`,
              xhr.status,
            ),
          );
        } catch {
          reject(new ApiError(`Upload failed: ${xhr.status}`, xhr.status));
        }
      }
    });

    xhr.addEventListener("error", () =>
      reject(new ApiError("Network error — check your connection", 0)),
    );
    xhr.addEventListener("abort", () =>
      reject(new ApiError("Upload aborted", 0)),
    );

    xhr.open("POST", `${API_BASE}/sessions/upload`);
    xhr.send(formData);
  });
}
