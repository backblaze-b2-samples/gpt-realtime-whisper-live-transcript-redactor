import { UploadForm } from "@/components/upload/upload-form";

export default function UploadPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Session Capture</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Upload an existing audio file (MP3, WAV, M4A, WebM, OGG, FLAC) — it
          is stored under <code>uploads/</code> in B2 and visible from{" "}
          <code>/files</code>. Use Live Recording for the full streaming
          pipeline with realtime redaction.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <UploadForm />
      </div>
    </div>
  );
}
