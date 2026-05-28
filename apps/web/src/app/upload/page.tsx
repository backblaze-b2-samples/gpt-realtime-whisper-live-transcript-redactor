import { PipelineUploadForm } from "@/components/upload/pipeline-upload-form";

export default function UploadPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Session Capture (File Upload)</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Upload an existing audio file and stream it through the same
          realtime redaction pipeline that Live Recording uses — a session
          bundle (redacted transcript + manifest + audit trail) lands in B2
          when the run finishes. v1 accepts WAV only.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <PipelineUploadForm />
      </div>
    </div>
  );
}
