import { useState } from "react";
import type { RepoOut } from "../../api/types";
import { RepoCard } from "./RepoCard";

const CAP = 4;

interface RealColumnProps {
  code: string;
  title: string;
  color: string;
  repos: RepoOut[];
}

function sortByDwellDesc(repos: RepoOut[]): RepoOut[] {
  return [...repos].sort((a, b) => {
    const aStuck = a.is_stuck ? 1 : 0;
    const bStuck = b.is_stuck ? 1 : 0;
    if (aStuck !== bStuck) return bStuck - aStuck;
    return (b.dwell_days ?? 0) - (a.dwell_days ?? 0);
  });
}

function RealColumn({ code, title, color, repos }: RealColumnProps) {
  const [expanded, setExpanded] = useState(false);
  const sorted = sortByDwellDesc(repos);
  const isCapped = repos.length > 5;
  const visible = expanded || !isCapped ? sorted : sorted.slice(0, CAP);

  return (
    <div className="bg-bg-card-locked rounded-xl flex-1 min-w-[220px] flex flex-col">
      <div className="p-3.5 pb-2.5 rounded-t-xl" style={{ borderTop: `3px solid ${color}` }}>
        <div className="font-mono text-[10.5px] text-chalk-dimmer">{code}</div>
        <div className="font-display font-bold text-[17px] my-0.5">{title}</div>
        <div className="font-mono text-[11px] text-chalk-dim">{repos.length} repos</div>
      </div>
      <div className="px-3 pb-3.5 flex flex-col gap-2.5">
        {visible.map((repo) => (
          <RepoCard key={repo.id} repo={repo} />
        ))}
        {isCapped && !expanded ? (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="text-center border border-dashed border-card-border rounded-[9px] p-2.5 font-mono text-[11.5px] text-chalk-dim hover:text-chalk hover:border-chalk-dim focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
          >
            Show all {repos.length}
          </button>
        ) : null}
      </div>
    </div>
  );
}

function EmptyColumn({ code, title, color, message }: { code: string; title: string; color: string; message: string }) {
  return (
    <div className="bg-bg-card-locked rounded-xl flex-1 min-w-[220px] flex flex-col">
      <div className="p-3.5 pb-2.5 rounded-t-xl" style={{ borderTop: `3px solid ${color}` }}>
        <div className="font-mono text-[10.5px] text-chalk-dimmer">{code}</div>
        <div className="font-display font-bold text-[17px] my-0.5">{title}</div>
        <div className="font-mono text-[11px] text-chalk-dim">0 repos</div>
      </div>
      <div className="px-3 pb-3.5">
        <div className="border border-dashed border-card-border rounded-[9px] p-5 text-center">
          <p className="font-mono text-[11px] text-chalk-dimmer leading-relaxed">{message}</p>
        </div>
      </div>
    </div>
  );
}

export function StationBoard({ repos }: { repos: RepoOut[] }) {
  // Only onboarded/standardized are real columns today because the backend never produces any
  // other current_stage value; repos with any other stage are intentionally not shown on the
  // board in this phase — a future phase adding a new stage must also update this component.
  const onboarded = repos.filter((r) => r.current_stage === "onboarded");
  const standardized = repos.filter((r) => r.current_stage === "standardized");

  return (
    <div className="flex gap-4 overflow-x-auto pb-3 mb-5">
      <RealColumn code="ON" title="Onboarded" color="#A79AE8" repos={onboarded} />
      <RealColumn code="ST" title="Standardized" color="#A79AE8" repos={standardized} />
      <EmptyColumn
        code="PI"
        title="Piped"
        color="#3FBBA0"
        message="Not live yet — unlocks once the CI/CD connector ships."
      />
      <EmptyColumn
        code="TS"
        title="Tested"
        color="#E7975C"
        message="Not live yet — unlocks once the E2E/load connector ships."
      />
      <EmptyColumn
        code="PV"
        title="Paved road"
        color="#EFC24B"
        message="Not started. Unlocks once Piped and Tested both ship."
      />
    </div>
  );
}
