import { useState } from "react";
import { useRepos } from "../hooks/useRepos";
import { StatStrip } from "../components/fleet/StatStrip";
import { Legend } from "../components/fleet/Legend";
import { StationBoard } from "../components/fleet/StationBoard";

export function FleetPage() {
  const { repos } = useRepos();
  const [stuckExpanded, setStuckExpanded] = useState(false);

  return (
    <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk max-w-[1180px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Fleet
      </div>
      <h1 className="font-display text-[clamp(32px,6vw,48px)] font-extrabold tracking-tight mb-2">Repo fleet</h1>
      <p className="text-chalk-dim text-[15px] mb-8 max-w-[60ch]">
        Where every repo sits right now, and what's stuck. Click any repo for its full journey.
      </p>

      <StatStrip repos={repos} onToggleStuck={() => setStuckExpanded((prev) => !prev)} stuckExpanded={stuckExpanded} />
      <Legend />
      <StationBoard repos={repos} />
    </div>
  );
}
