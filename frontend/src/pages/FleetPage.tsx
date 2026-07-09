import { useEffect, useState } from "react";
import { useRepos } from "../hooks/useRepos";
import { StatStrip } from "../components/fleet/StatStrip";
import { Legend } from "../components/fleet/Legend";
import { StuckPanel } from "../components/fleet/StuckPanel";
import { StationBoard } from "../components/fleet/StationBoard";
import { InventoryTable } from "../components/fleet/InventoryTable";
import type { RepoOut } from "../api/types";

export function FleetPage() {
  const { repos: fetchedRepos, loading, error } = useRepos();
  const [repos, setRepos] = useState<RepoOut[]>([]);
  const [stuckExpanded, setStuckExpanded] = useState(false);
  const [view, setView] = useState<"board" | "inventory">("board");

  useEffect(() => {
    setRepos(fetchedRepos);
  }, [fetchedRepos]);

  function handleRepoUpdated(updated: RepoOut) {
    setRepos((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  if (loading) {
    return (
      <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk p-8">
        Loading…
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk p-8">
        {error}
      </div>
    );
  }

  return (
    <div data-testid="fleet-page" className="min-h-screen bg-bg text-chalk max-w-[1180px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Fleet
      </div>
      <h1 className="font-display text-[clamp(32px,6vw,48px)] font-extrabold tracking-tight mb-2">Repo fleet</h1>
      <p className="text-chalk-dim text-[15px] mb-8 max-w-[60ch]">
        Where every repo sits right now, and what's stuck. Click any repo for its full journey.
      </p>

      <div className="flex gap-1 border-b border-card-border mb-6" role="tablist">
        <button
          role="tab"
          aria-selected={view === "board"}
          onClick={() => setView("board")}
          className={`px-4 py-2 text-[12px] border-b-2 -mb-px ${
            view === "board" ? "border-gold text-gold" : "border-transparent text-chalk-dim"
          }`}
        >
          Board
        </button>
        <button
          role="tab"
          aria-selected={view === "inventory"}
          onClick={() => setView("inventory")}
          className={`px-4 py-2 text-[12px] border-b-2 -mb-px ${
            view === "inventory" ? "border-gold text-gold" : "border-transparent text-chalk-dim"
          }`}
        >
          Inventory
        </button>
      </div>

      {view === "board" ? (
        <>
          <StatStrip repos={repos} onToggleStuck={() => setStuckExpanded((prev) => !prev)} stuckExpanded={stuckExpanded} />
          <Legend />
          <StuckPanel repos={repos} expanded={stuckExpanded} />
          <StationBoard repos={repos} />
        </>
      ) : (
        <InventoryTable repos={repos} onUpdated={handleRepoUpdated} />
      )}
    </div>
  );
}
