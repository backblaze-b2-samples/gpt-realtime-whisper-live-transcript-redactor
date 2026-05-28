"use client";

import { useState } from "react";
import { Download, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { useGenerateExport, useSession } from "@/lib/queries";
import { formatDate } from "@/lib/utils";
import type {
  ExportFormat,
} from "@gpt-realtime-whisper-live-transcript-redactor/shared";

function fmtDuration(ms: number): string {
  if (!ms) return "0s";
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

const FORMATS: ExportFormat[] = ["txt", "srt", "vtt"];

export function SessionDetail({ sessionId }: { sessionId: string }) {
  const { data, isLoading, error, refetch } = useSession(sessionId);
  const exporter = useGenerateExport();
  const [lastExportUrl, setLastExportUrl] = useState<string | null>(null);

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }
  if (error || !data) {
    return <ErrorState error={error ?? new Error("Not found")} onRetry={() => refetch()} />;
  }

  const handleExport = (format: ExportFormat) => {
    exporter.mutate(
      { sessionId, format },
      {
        onSuccess: (info) => setLastExportUrl(info.url ?? null),
      },
    );
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title">Session summary</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 p-5 text-sm">
          <div>
            <div className="text-xs text-muted-foreground">Created</div>
            <div className="font-medium">{formatDate(data.created_at)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Duration</div>
            <div className="font-medium">{fmtDuration(data.duration_ms)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Detections</div>
            <div className="font-medium">{data.detection_count}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Storage mode</div>
            <div className="font-medium">
              {data.storage_mode === "originals_stored"
                ? "Originals stored"
                : "Redacted only"}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title flex items-center gap-2">
            <ShieldAlert className="h-3.5 w-3.5" /> Audit trail
          </CardTitle>
        </CardHeader>
        <CardContent className="p-5">
          <ul className="space-y-1.5 text-xs font-mono">
            {data.events.map((ev, i) => (
              <li key={i} className="text-muted-foreground">
                <span className="text-foreground">{ev.type}</span>{" "}
                <span>{formatDate(ev.at)}</span>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="border-b border-border py-4 px-5">
          <CardTitle className="card-title flex items-center gap-2">
            <Download className="h-3.5 w-3.5" /> Exports
          </CardTitle>
        </CardHeader>
        <CardContent className="p-5 flex flex-wrap gap-3">
          {FORMATS.map((fmt) => (
            <Button
              key={fmt}
              variant="outline"
              size="sm"
              onClick={() => handleExport(fmt)}
              disabled={exporter.isPending}
            >
              Generate .{fmt}
            </Button>
          ))}
          {lastExportUrl ? (
            <a
              href={lastExportUrl}
              className="text-sm underline self-center"
              target="_blank"
              rel="noopener noreferrer"
            >
              Download latest
            </a>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
