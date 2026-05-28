"use client";

import Link from "next/link";
import { MicOff, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useDeleteSession, useSessions } from "@/lib/queries";
import { formatDate } from "@/lib/utils";

function fmtDuration(ms: number): string {
  if (!ms) return "0s";
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes) return `${minutes}m ${seconds}s`;
  return `${seconds}s`;
}

export function SessionsList() {
  const { data: sessions = [], isLoading, error, refetch } = useSessions(200);
  const del = useDeleteSession();

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-4 space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }
  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }
  if (sessions.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={MicOff}
            title="No sessions yet"
            description="Sessions you record show up here with their redaction stats."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow className="bg-muted/40 hover:bg-muted/40">
              <TableHead className="w-[28%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Session
              </TableHead>
              <TableHead className="w-[12%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Duration
              </TableHead>
              <TableHead className="w-[12%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Detections
              </TableHead>
              <TableHead className="w-[20%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Storage
              </TableHead>
              <TableHead className="w-[20%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Created
              </TableHead>
              <TableHead className="w-[8%]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {sessions.map((s) => (
              <TableRow key={s.session_id} className="table-row-hover">
                <TableCell className="font-medium">
                  <Link
                    href={`/sessions/${s.session_id}`}
                    className="hover:underline truncate"
                  >
                    {s.session_id}
                  </Link>
                </TableCell>
                <TableCell className="font-mono text-xs text-muted-foreground tabular-nums whitespace-nowrap">
                  {fmtDuration(s.duration_ms)}
                </TableCell>
                <TableCell className="text-muted-foreground whitespace-nowrap">
                  {s.detection_count}
                </TableCell>
                <TableCell className="whitespace-nowrap">
                  <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        s.storage_mode === "originals_stored"
                          ? "bg-amber-500"
                          : "bg-[var(--success)]"
                      }`}
                    />
                    {s.storage_mode === "originals_stored"
                      ? "Originals stored"
                      : "Redacted only"}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground whitespace-nowrap">
                  {formatDate(s.created_at)}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => del.mutate(s.session_id)}
                    disabled={del.isPending}
                    title="Delete session"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
