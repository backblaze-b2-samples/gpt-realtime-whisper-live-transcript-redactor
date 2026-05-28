export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  image_width: number | null;
  image_height: number | null;
  exif: Record<string, string> | null;
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// --- Session / redaction domain ------------------------------------------

export type SessionStatus = "recording" | "finalized" | "errored";
export type StorageMode = "redacted_only" | "originals_stored";
export type DetectorSource = "pii" | "secrets" | "glossary";
export type DetectionSeverity = "low" | "medium" | "high";
export type ExportFormat = "txt" | "srt" | "vtt";

export interface AuditEvent {
  type: string;
  at: string;
  detail: Record<string, unknown>;
}

export interface Detection {
  segment_index: number;
  start: number;
  end: number;
  detector: DetectorSource;
  type: string;
  severity: DetectionSeverity;
  original_length: number;
}

export interface RedactionManifest {
  session_id: string;
  modes: string[];
  detections: Detection[];
  counts_by_type: Record<string, number>;
  counts_by_severity: Record<string, number>;
}

export interface TranscriptSegment {
  index: number;
  started_at_ms: number;
  ended_at_ms: number;
  text: string;
}

export interface Transcript {
  session_id: string;
  variant: "redacted" | "original";
  segments: TranscriptSegment[];
}

export interface SessionManifest {
  session_id: string;
  created_at: string;
  finalized_at: string | null;
  status: SessionStatus;
  storage_mode: StorageMode;
  store_original_audio: boolean;
  store_original_transcript: boolean;
  redaction_modes: string[];
  model: string;
  duration_ms: number;
  audio_bytes_received: number;
  segment_count: number;
  detection_count: number;
  detection_counts_by_severity: Record<string, number>;
  original_text_sha256: string | null;
  redacted_text_sha256: string | null;
  audio_extension: string | null;
  events: AuditEvent[];
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  finalized_at: string | null;
  status: SessionStatus;
  storage_mode: StorageMode;
  duration_ms: number;
  detection_count: number;
  detection_counts_by_severity: Record<string, number>;
  segment_count: number;
  has_audio: boolean;
  has_original_transcript: boolean;
}

export interface SessionStartRequest {
  redaction_modes?: string[] | null;
  store_original_audio?: boolean | null;
  store_original_transcript?: boolean | null;
}

export interface SessionStartResponse {
  session_id: string;
  created_at: string;
  storage_mode: StorageMode;
  redaction_modes: string[];
  model: string;
}

export interface SessionStats {
  total_sessions: number;
  total_duration_ms: number;
  total_detections: number;
  detections_by_severity: Record<string, number>;
  sessions_today: number;
  storage_mode_counts: Record<string, number>;
}

export interface DailySessionCount {
  date: string;
  sessions: number;
  detections: number;
}

export interface ExportInfo {
  session_id: string;
  format: ExportFormat;
  key: string;
  size_bytes: number;
  url: string | null;
}

export interface GlossaryTerm {
  term: string;
  severity: DetectionSeverity;
  label: string | null;
}

export interface Glossary {
  version: number;
  terms: GlossaryTerm[];
}
