"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import type { FileRejection } from "react-dropzone";
import { useDropzone } from "react-dropzone";
import { Loader2, ShieldAlert, Upload as UploadIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  uploadSessionAudio,
  type SessionUploadResponse,
} from "@/lib/api-client";
import { humanizeBytes } from "@/lib/utils";
import { useRefresh } from "@/lib/refresh-context";

const MAX_SIZE = 100 * 1024 * 1024;

// v1 pipeline-mode upload accepts WAV only — see
// services/api/app/service/audio_decode.py for the rationale and v2
// expansion plan. The legacy /upload (now removed from this surface)
// allowed MP3/M4A/WebM via the bucket-explorer ingest; pipeline mode
// is stricter on purpose.
const ACCEPTED_WAV = {
  "audio/wav": [".wav"],
  "audio/x-wav": [".wav"],
  "audio/wave": [".wav"],
};

type Phase = "idle" | "uploading" | "processing" | "done" | "error";

export function PipelineUploadForm() {
  const router = useRouter();
  const { triggerRefresh } = useRefresh();
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SessionUploadResponse | null>(null);

  const handleRejected = useCallback((rejections: FileRejection[]) => {
    for (const r of rejections) {
      const reasons = r.errors.map((e) =>
        e.code === "file-too-large"
          ? `exceeds 100MB (${humanizeBytes(r.file.size)})`
          : e.code === "file-invalid-type"
            ? "pipeline mode accepts WAV only in v1"
            : e.message,
      );
      toast.error(`${r.file.name}: ${reasons.join(", ")}`);
    }
  }, []);

  const handleDrop = useCallback(
    async (accepted: File[]) => {
      if (accepted.length === 0) return;
      const [picked] = accepted;
      setFile(picked);
      setProgress(0);
      setError(null);
      setResult(null);
      setPhase("uploading");
      try {
        const res = await uploadSessionAudio(picked, (percent) => {
          setProgress(percent);
          if (percent >= 100) setPhase("processing");
        });
        setResult(res);
        setPhase("done");
        triggerRefresh();
        toast.success(
          `Streamed through realtime pipeline — ${res.segment_count} segment(s), ${res.detection_count} detection(s).`,
        );
        // Hand off to the detail page so the user sees the redacted bundle.
        router.push(`/sessions/${res.session_id}`);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Upload failed";
        setError(message);
        setPhase("error");
        toast.error(message);
      }
    },
    [router, triggerRefresh],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: handleDrop,
    onDropRejected: handleRejected,
    maxSize: MAX_SIZE,
    accept: ACCEPTED_WAV,
    multiple: false,
    disabled: phase === "uploading" || phase === "processing",
  });

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Stream audio file through the realtime pipeline</CardTitle>
      </CardHeader>
      <CardContent className="p-5 space-y-4">
        <div
          {...getRootProps()}
          className={`flex flex-col items-center justify-center rounded-md border-2 border-dashed p-10 text-center transition-colors cursor-pointer ${
            isDragActive
              ? "border-primary bg-[var(--accent-subtle)] dropzone-active"
              : "border-border hover:border-primary/60 hover:bg-muted/60"
          } ${phase === "uploading" || phase === "processing" ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <input {...getInputProps()} />
          <div className="flex flex-col items-center gap-3">
            <div className="flex items-center justify-center w-12 h-12 rounded-md bg-muted border border-border">
              <UploadIcon className="h-5 w-5 text-muted-foreground" />
            </div>
            <div>
              <p className="text-base font-semibold">
                {isDragActive
                  ? "Drop your WAV file here"
                  : "Drag & drop a WAV file, or click to browse"}
              </p>
              <p className="text-xs text-muted-foreground mt-1 font-mono">
                WAV (PCM 16-bit / 8-bit, mono or stereo) · max 100 MB · ≤ 30 min
              </p>
            </div>
          </div>
        </div>

        {file && (phase === "uploading" || phase === "processing") && (
          <div className="flex items-center gap-3 rounded-md border border-border bg-card p-3">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{file.name}</p>
              <p className="text-xs text-muted-foreground">
                {phase === "uploading"
                  ? `Uploading… ${progress}%`
                  : "Streaming through realtime API…"}
              </p>
            </div>
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {humanizeBytes(file.size)}
            </span>
          </div>
        )}

        {phase === "done" && result && (
          <div className="rounded-md border border-[var(--success)]/30 bg-[var(--success)]/10 p-3 text-sm">
            Pipeline ingest complete — {result.segment_count} segment(s),{" "}
            {result.detection_count} detection(s). Redirecting to{" "}
            <code className="font-mono text-xs">
              /sessions/{result.session_id}
            </code>
            …
          </div>
        )}

        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive flex items-center gap-2">
            <ShieldAlert className="h-4 w-4" /> {error}
          </div>
        )}

        <p className="text-xs text-muted-foreground">
          v1 pipeline ingest accepts WAV only. MP3, M4A, WebM and OGG are
          documented as a v2 expansion — see{" "}
          <code className="font-mono">docs/features/session-capture.md</code>{" "}
          for the v2 plan. Use <strong>Live Recording</strong> for direct mic
          capture.
        </p>
      </CardContent>
    </Card>
  );
}
