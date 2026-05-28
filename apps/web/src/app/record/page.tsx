import { RecordControls } from "@/components/record/record-controls";

export default function RecordPage() {
  return (
    <div className="space-y-6">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Live Recording</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Stream your microphone to OpenAI Realtime, redact PII, secrets, and
          glossary terms in flight, and persist a privacy-default bundle to
          Backblaze B2.
        </p>
      </div>
      <RecordControls />
    </div>
  );
}
