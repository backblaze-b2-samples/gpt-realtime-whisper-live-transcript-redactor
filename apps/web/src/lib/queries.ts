"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ApiError,
  deleteFile,
  deleteSession,
  generateExport,
  getFiles,
  getFileStats,
  getGlossary,
  getPreviewUrl,
  getSession,
  getSessionActivity,
  getSessionStats,
  getSessionTranscript,
  getUploadActivity,
  listSessions,
  saveGlossary,
} from "@/lib/api-client";
import type {
  ExportFormat,
  FileMetadata,
  Glossary,
} from "@gpt-realtime-whisper-live-transcript-redactor/shared";

export const qk = {
  all: ["b2"] as const,
  files: (prefix?: string, limit?: number) =>
    [...qk.all, "files", prefix ?? "", limit ?? 100] as const,
  fileStats: () => [...qk.all, "fileStats"] as const,
  uploadActivity: (days: number) =>
    [...qk.all, "fileStats", "activity", days] as const,
  preview: (key: string) => [...qk.all, "preview", key] as const,
  sessions: (limit?: number) => [...qk.all, "sessions", limit ?? 100] as const,
  session: (id: string) => [...qk.all, "session", id] as const,
  transcript: (id: string) => [...qk.all, "transcript", id] as const,
  sessionStats: () => [...qk.all, "sessionStats"] as const,
  sessionActivity: (days: number) =>
    [...qk.all, "sessionStats", "activity", days] as const,
  glossary: () => [...qk.all, "glossary"] as const,
};

export function useFiles(prefix = "", limit = 100) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
  });
}

export function useFileStats() {
  return useQuery({ queryKey: qk.fileStats(), queryFn: getFileStats });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.all }),
  });
}

// --- Sessions / redaction --------------------------------------------------

export function useSessions(limit = 100) {
  return useQuery({
    queryKey: qk.sessions(limit),
    queryFn: () => listSessions(limit),
  });
}

export function useSession(id: string | undefined) {
  return useQuery({
    queryKey: qk.session(id ?? ""),
    queryFn: () => getSession(id as string),
    enabled: !!id,
  });
}

export function useSessionTranscript(id: string | undefined) {
  return useQuery({
    queryKey: qk.transcript(id ?? ""),
    queryFn: () => getSessionTranscript(id as string),
    enabled: !!id,
  });
}

export function useSessionStats() {
  return useQuery({ queryKey: qk.sessionStats(), queryFn: getSessionStats });
}

export function useSessionActivity(days = 7) {
  return useQuery({
    queryKey: qk.sessionActivity(days),
    queryFn: () => getSessionActivity(days),
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => deleteSession(sessionId),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.all }),
  });
}

export function useGenerateExport() {
  return useMutation({
    mutationFn: ({
      sessionId,
      format,
    }: {
      sessionId: string;
      format: ExportFormat;
    }) => generateExport(sessionId, format),
  });
}

export function useGlossary() {
  return useQuery({ queryKey: qk.glossary(), queryFn: getGlossary });
}

export function useSaveGlossary() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (glossary: Glossary) => saveGlossary(glossary),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.glossary() }),
  });
}
