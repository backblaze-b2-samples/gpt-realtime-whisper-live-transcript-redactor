"use client";

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { useGlossary, useSaveGlossary } from "@/lib/queries";
import type {
  DetectionSeverity,
  Glossary,
} from "@gpt-realtime-whisper-live-transcript-redactor/shared";

export function GlossaryEditor() {
  const { data: glossary, isLoading, error, refetch } = useGlossary();

  if (isLoading) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (error) {
    return <ErrorState error={error} onRetry={() => refetch()} />;
  }
  // Remount the form whenever the persisted glossary changes — avoids the
  // useEffect-into-setState anti-pattern. Local edits live entirely inside
  // GlossaryEditorForm.
  return (
    <GlossaryEditorForm
      key={JSON.stringify(glossary?.terms ?? [])}
      glossary={glossary ?? { version: 1, terms: [] }}
    />
  );
}

function GlossaryEditorForm({ glossary }: { glossary: Glossary }) {
  const save = useSaveGlossary();
  const [terms, setTerms] = useState(glossary.terms ?? []);
  const [draft, setDraft] = useState("");

  const add = () => {
    const term = draft.trim();
    if (!term) return;
    setTerms((t) => [...t, { term, severity: "low", label: null }]);
    setDraft("");
  };

  const remove = (index: number) =>
    setTerms((t) => t.filter((_, i) => i !== index));

  const updateSeverity = (index: number, severity: DetectionSeverity) => {
    setTerms((t) =>
      t.map((row, i) => (i === index ? { ...row, severity } : row)),
    );
  };

  const persist = () => {
    save.mutate(
      { version: glossary.version ?? 1, terms },
      {
        onSuccess: () =>
          toast.success("Glossary saved", {
            description: `${terms.length} term${terms.length === 1 ? "" : "s"}`,
          }),
        onError: (e) =>
          toast.error("Failed to save glossary", {
            description: (e as Error).message,
          }),
      },
    );
  };

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Custom glossary</CardTitle>
      </CardHeader>
      <CardContent className="p-5 space-y-4">
        <p className="text-xs text-muted-foreground">
          Case-insensitive whole-word terms redacted alongside PII and secrets.
          Stored at <code>config/glossary.json</code> in B2.
        </p>
        <div className="flex gap-2">
          <Input
            placeholder="Add a term (e.g. project codename)"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <Button type="button" onClick={add} size="sm" variant="secondary">
            <Plus className="h-3.5 w-3.5" /> Add
          </Button>
        </div>
        {terms.length === 0 ? (
          <p className="text-xs italic text-muted-foreground">
            No terms yet — emails, SSNs, AWS keys etc. are still redacted by
            the built-in detectors.
          </p>
        ) : (
          <ul className="space-y-2">
            {terms.map((t, i) => (
              <li
                key={`${t.term}-${i}`}
                className="flex items-center gap-2 rounded border border-border p-2"
              >
                <code className="flex-1 text-sm">{t.term}</code>
                <Select
                  value={t.severity}
                  onValueChange={(v) =>
                    updateSeverity(i, v as DetectionSeverity)
                  }
                >
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => remove(i)}
                  title="Remove"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end pt-2">
          <Button onClick={persist} disabled={save.isPending}>
            {save.isPending ? "Saving..." : "Save glossary"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
