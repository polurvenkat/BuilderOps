import type { PipelineStageStatusOut } from "../../api/types";

interface PipelineStatusPanelProps {
  stages: PipelineStageStatusOut[] | null;
  loading: boolean;
  error: string | null;
}

export function PipelineStatusPanel({ stages, loading, error }: PipelineStatusPanelProps) {
  const pendingApprovals = stages?.filter((s) => s.pending_approval_description) ?? [];

  return (
    <div className="bg-bg-card border border-card-border rounded-xl p-4 mt-4">
      <div className="font-mono text-[10.5px] text-chalk-dim uppercase mb-2">Live pipeline status</div>
      {loading ? <p className="text-[13px] text-chalk-dim">Loading…</p> : null}
      {error ? <p className="text-[13px] text-track3">Couldn't reach Azure DevOps — try again</p> : null}
      {!loading && !error && stages ? (
        <div className="flex flex-col gap-2">
          {stages.map((stage) => (
            <div key={stage.name} className="flex justify-between text-[13px]">
              <span>{stage.name}</span>
              <span className="font-mono text-[12px] text-chalk-dim">{stage.status}</span>
            </div>
          ))}
          {pendingApprovals.map((stage) => (
            <div
              key={`${stage.name}-approval`}
              className="mt-2 rounded-lg border border-gold/40 bg-gold/10 text-gold p-2 text-[12.5px]"
            >
              {stage.name}: {stage.pending_approval_description}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
