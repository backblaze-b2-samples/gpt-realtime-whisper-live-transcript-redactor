"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, Square, ShieldAlert, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { startSession, realtimeSessionUrl } from "@/lib/api-client";
import { startCapture, type AudioCaptureHandle } from "@/lib/audio-capture";
import type {
  Detection,
  DetectionSeverity,
} from "@gpt-realtime-whisper-live-transcript-redactor/shared";

interface FinalSegment {
  index: number;
  redacted_text: string;
  detections: Detection[];
}

const SEV_COLOR: Record<DetectionSeverity, string> = {
  high: "bg-red-500/15 text-red-600 ring-1 ring-red-500/30",
  medium: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30",
  low: "bg-blue-500/15 text-blue-700 ring-1 ring-blue-500/30",
};

export function RecordControls() {
  const [recording, setRecording] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [delta, setDelta] = useState("");
  const [segments, setSegments] = useState<FinalSegment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [storeAudio, setStoreAudio] = useState(true);
  const [storeTranscript, setStoreTranscript] = useState(true);
  const [modes, setModes] = useState<string[]>(["pii", "secrets", "glossary"]);

  const wsRef = useRef<WebSocket | null>(null);
  const captureRef = useRef<AudioCaptureHandle | null>(null);

  const stop = useCallback(async () => {
    setRecording(false);
    try {
      wsRef.current?.send(JSON.stringify({ type: "stop" }));
    } catch {
      /* noop */
    }
    try {
      await captureRef.current?.stop();
    } finally {
      captureRef.current = null;
    }
    try {
      wsRef.current?.close();
    } catch {
      /* noop */
    }
    wsRef.current = null;
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setSegments([]);
    setDelta("");
    try {
      const session = await startSession({
        redaction_modes: modes,
        store_original_audio: storeAudio,
        store_original_transcript: storeTranscript,
      });
      setSessionId(session.session_id);

      const ws = new WebSocket(realtimeSessionUrl(session.session_id));
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      await new Promise<void>((resolve, reject) => {
        ws.onopen = () => resolve();
        ws.onerror = () =>
          reject(new Error("WebSocket connection failed"));
      });
      ws.onmessage = (evt) => {
        if (typeof evt.data !== "string") return;
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === "delta") setDelta((d) => d + msg.text);
          else if (msg.type === "segment") {
            setSegments((s) => [
              ...s,
              {
                index: msg.segment.index,
                redacted_text: msg.segment.redacted_text,
                detections: msg.detections ?? [],
              },
            ]);
            setDelta("");
          } else if (msg.type === "error") setError(msg.message);
          else if (msg.type === "finalized") {
            setRecording(false);
          }
        } catch {
          /* noop */
        }
      };

      const handle = await startCapture({
        onChunk: (chunk) => {
          if (ws.readyState === WebSocket.OPEN) ws.send(chunk);
        },
        onError: (e) => setError(e.message),
      });
      captureRef.current = handle;
      setRecording(true);
    } catch (e) {
      setError((e as Error).message);
      await stop();
    }
  }, [modes, storeAudio, storeTranscript, stop]);

  useEffect(() => {
    return () => {
      void stop();
    };
  }, [stop]);

  const toggleMode = (mode: string) => {
    setModes((cur) =>
      cur.includes(mode) ? cur.filter((m) => m !== mode) : [...cur, mode],
    );
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <Card>
        <CardHeader className="border-b border-border py-4 px-5 flex flex-row items-center justify-between gap-3">
          <CardTitle className="card-title">
            {recording ? "Live transcript" : "Ready to record"}
          </CardTitle>
          {sessionId ? (
            <span className="text-xs text-muted-foreground font-mono">
              {sessionId}
            </span>
          ) : null}
        </CardHeader>
        <CardContent className="p-5 space-y-4 min-h-[320px]">
          {error ? (
            <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600 flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" /> {error}
            </div>
          ) : null}
          {segments.length === 0 && !delta ? (
            <p className="text-sm text-muted-foreground">
              Hit <strong>Start recording</strong> and your microphone audio
              will stream to OpenAI Realtime. Finalized utterances run through
              the layered redaction pass and appear here with severity chips.
            </p>
          ) : null}
          <div className="space-y-3 max-h-[420px] overflow-auto">
            {segments.map((seg) => (
              <div key={seg.index} className="space-y-1">
                <p className="text-sm leading-relaxed">{seg.redacted_text}</p>
                {seg.detections.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {seg.detections.map((d, i) => (
                      <span
                        key={i}
                        className={`text-[10px] font-mono rounded px-1.5 py-0.5 ${SEV_COLOR[d.severity]}`}
                      >
                        {d.type}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            {delta ? (
              <p className="text-sm italic text-muted-foreground">{delta}</p>
            ) : null}
          </div>
          <div className="flex gap-3 pt-2">
            {recording ? (
              <Button onClick={stop} variant="destructive" size="sm">
                <Square className="h-3.5 w-3.5" />
                Stop
              </Button>
            ) : (
              <Button onClick={start} size="sm">
                <Mic className="h-3.5 w-3.5" />
                Start recording
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
      <Card className="self-start">
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5" /> Session options
          </CardTitle>
        </CardHeader>
        <CardContent className="p-5 space-y-5 text-sm">
          <div className="space-y-2">
            <div className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
              Redaction layers
            </div>
            {["pii", "secrets", "glossary"].map((m) => (
              <div key={m} className="flex items-center gap-2">
                <Checkbox
                  id={`mode-${m}`}
                  checked={modes.includes(m)}
                  onCheckedChange={() => toggleMode(m)}
                  disabled={recording}
                />
                <Label htmlFor={`mode-${m}`} className="font-normal">
                  {m === "pii" ? "PII (emails, phones, SSN, IPs)" : null}
                  {m === "secrets" ? "Secrets (AWS / GitHub / OpenAI / JWT)" : null}
                  {m === "glossary" ? "Custom glossary" : null}
                </Label>
              </div>
            ))}
          </div>
          <div className="space-y-2">
            <div className="text-xs uppercase tracking-wider text-muted-foreground font-semibold">
              Storage
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="store-audio"
                checked={storeAudio}
                onCheckedChange={(v) => setStoreAudio(Boolean(v))}
                disabled={recording}
              />
              <Label htmlFor="store-audio" className="font-normal">
                Store original audio
              </Label>
            </div>
            <div className="flex items-center gap-2">
              <Checkbox
                id="store-transcript"
                checked={storeTranscript}
                onCheckedChange={(v) => setStoreTranscript(Boolean(v))}
                disabled={recording}
              />
              <Label htmlFor="store-transcript" className="font-normal">
                Store unredacted transcript
              </Label>
            </div>
            <p className="text-xs text-muted-foreground pt-1">
              <Badge variant="secondary" className="text-[10px] mr-1">
                Default
              </Badge>
              Both are on for dev convenience. Flip them off for
              compliance-sensitive deployments — the redacted bundle and audit
              manifest are always preserved.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
