import { SessionsList } from "@/components/sessions/sessions-list";

export default function SessionsPage() {
  return (
    <div className="space-y-6">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Sessions</h1>
        <p className="text-sm text-muted-foreground mt-1.5">
          Library of redaction sessions scoped to the <code>sessions/</code>
          prefix in B2.
        </p>
      </div>
      <SessionsList />
    </div>
  );
}
