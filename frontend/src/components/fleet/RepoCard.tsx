import { Link } from "react-router-dom";
import type { RepoOut } from "../../api/types";
import { formatDwell } from "../../lib/format";

export function RepoCard({ repo }: { repo: RepoOut }) {
  return (
    <Link
      to={`/repos/${repo.id}`}
      className="block bg-bg-card border border-card-border rounded-[9px] p-3 no-underline text-inherit hover:-translate-y-0.5 transition-transform focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
    >
      <div className="font-display font-bold text-[14.5px] mb-1.5">{repo.name}</div>
      <div className="flex justify-between font-mono text-[10.5px] text-chalk-dim">
        <span>{repo.team ?? "Unassigned"}</span>
        <span>{formatDwell(repo.dwell_days)}</span>
      </div>
      {repo.is_stuck && repo.stuck_reason ? (
        <div className="mt-2 pt-2 border-t border-dashed border-card-border flex gap-1.5 text-[12px] text-chalk-dim">
          <span className="w-1.5 h-1.5 rounded-full bg-track3 mt-1 flex-shrink-0" />
          {repo.stuck_reason}
        </div>
      ) : null}
    </Link>
  );
}
