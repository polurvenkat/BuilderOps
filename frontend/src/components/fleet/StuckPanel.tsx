import { Link } from "react-router-dom";
import type { RepoOut } from "../../api/types";
import { formatDwell } from "../../lib/format";

export function StuckPanel({ repos, expanded }: { repos: RepoOut[]; expanded: boolean }) {
  const stuckSorted = repos
    .filter((r) => r.is_stuck)
    .sort((a, b) => (b.dwell_days ?? 0) - (a.dwell_days ?? 0));

  return (
    <div
      data-testid="stuck-panel"
      hidden={!expanded}
      className="bg-bg-card border border-track3/35 rounded-xl p-4 mb-7"
    >
      <div className="font-mono text-[11px] uppercase tracking-wide text-track3 mb-3">Stuck now — worst first</div>
      {stuckSorted.map((repo, index) => (
        <Link
          key={repo.id}
          to={`/repos/${repo.id}`}
          className={`flex items-center gap-3 py-2.5 no-underline text-inherit ${index > 0 ? "border-t border-card-border" : ""}`}
        >
          <span data-testid="stuck-row-name" className="font-display font-bold text-[14px] flex-shrink-0 min-w-[170px]">
            {repo.name}
          </span>
          <span className="text-chalk-dim text-[13px] flex-1">{repo.stuck_reason}</span>
          <span className="font-mono font-bold text-track3 text-[13px] whitespace-nowrap tabular-nums">
            {formatDwell(repo.dwell_days)}
          </span>
        </Link>
      ))}
    </div>
  );
}
