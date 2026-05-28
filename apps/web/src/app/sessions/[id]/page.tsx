import { SessionDetail } from "@/components/sessions/session-detail";

export default async function SessionDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="space-y-6">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Session detail</h1>
        <p className="text-sm text-muted-foreground mt-1.5 font-mono">{id}</p>
      </div>
      <SessionDetail sessionId={id} />
    </div>
  );
}
