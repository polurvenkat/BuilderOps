import type { RepoOut } from "../../api/types";
import { STAGE_LABELS } from "../../lib/format";

interface StatStripProps {
  repos: RepoOut[];
  onToggleStuck: () => void;
  stuckExpanded: boolean;
}

// Note: the caller renders STAGE_LABELS[crowded] ?? crowded, so if STAGE_LABELS doesn't have an
// entry for a given stage, this will surface the raw (unmapped) stage string — acceptable today,
// but a signal that STAGE_LABELS (here) and the backend's stage ordering need updating together
// if the set of possible stages changes.
function mostCrowdedStage(repos: RepoOut[]): string | null {
  const counts = new Map<string, number>();
  for (const repo of repos) {
    counts.set(repo.current_stage, (counts.get(repo.current_stage) ?? 0) + 1);
  }
  let top: string | null = null;
  let topCount = 0;
  for (const [stage, count] of counts) {
    if (count > topCount) {
      top = stage;
      topCount = count;
    }
  }
  return top;
}

export function StatStrip({ repos, onToggleStuck, stuckExpanded }: StatStripProps) {
  const paved = repos.filter((r) => r.current_stage === "paved_road").length;
  const stuckOver14 = repos.filter((r) => r.is_stuck && (r.dwell_days ?? 0) > 14).length;
  const crowded = mostCrowdedStage(repos);

  return (
    <div className="grid gap-px bg-card-border border border-card-border rounded-xl overflow-hidden mb-6">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-px bg-card-border">
        <div className="bg-bg-card p-4 flex flex-col gap-1">
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Repos tracked</span>
          <span className="font-display text-[26px] font-extrabold text-gold tabular-nums">{repos.length}</span>
        </div>
        <div className="bg-bg-card p-4 flex flex-col gap-1">
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Paved</span>
          <span className="font-display text-[26px] font-extrabold text-gold tabular-nums">{paved}</span>
        </div>
        <button
          type="button"
          aria-expanded={stuckExpanded}
          onClick={onToggleStuck}
          className="bg-bg-card p-4 flex flex-col gap-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
        >
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Stuck &gt;14 days</span>
          <span className="font-display text-[26px] font-extrabold text-track3 tabular-nums">{stuckOver14}</span>
        </button>
        <div className="bg-bg-card p-4 flex flex-col gap-1">
          <span className="font-mono text-[10.5px] text-chalk-dim uppercase">Most crowded</span>
          <span className="font-display text-[20px] font-extrabold text-gold">
            {crowded ? (STAGE_LABELS[crowded] ?? crowded) : "—"}
          </span>
        </div>
      </div>
    </div>
  );
}
