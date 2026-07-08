import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useRepo } from "../hooks/useRepo";
import { ConvergenceDiagram } from "../components/journey/ConvergenceDiagram";
import { StationCard } from "../components/journey/StationCard";
import { RepoFieldsForm } from "../components/journey/RepoFieldsForm";
import { OnboardingLog } from "../components/journey/OnboardingLog";
import type { RepoOut } from "../api/types";

const STANDARDIZED_KEYS = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];
const STANDARDIZED_CHECK_ORDER = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];

function fractionPassing(stages: Record<string, { status: string }>, keys: string[]): number {
  if (keys.length === 0) return 0;
  const passing = keys.filter((k) => stages[k]?.status === "pass").length;
  return passing / keys.length;
}

// Picks the most relevant Standardized sub-check to show in the card's Details panel: when the
// repo is stuck at the Standardized stage, surface whichever sub-check is actually failing
// (in a fixed priority order) instead of always defaulting to codeowners_assigned, so the
// Details panel matches the badge's "You are here" state.
function primaryStandardizedCheck(repo: RepoOut) {
  if (repo.is_stuck && repo.current_stage === "standardized") {
    const failingKey = STANDARDIZED_CHECK_ORDER.find((key) => repo.stages[key]?.status === "fail");
    if (failingKey) return repo.stages[failingKey];
  }
  return repo.stages.codeowners_assigned;
}

export function JourneyPage() {
  const { id } = useParams<{ id: string }>();
  const { repo: fetchedRepo, loading, error } = useRepo(Number(id));
  const [repo, setRepo] = useState<RepoOut | null>(null);

  useEffect(() => {
    if (fetchedRepo) setRepo(fetchedRepo);
  }, [fetchedRepo]);

  if (loading) {
    return (
      <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk p-8">
        Loading…
      </div>
    );
  }

  if (error || !repo) {
    return (
      <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk p-8">
        {error ?? "Repo not found"}
      </div>
    );
  }

  const standardsProgress = fractionPassing(repo.stages, ["migrated_from_ado", ...STANDARDIZED_KEYS]);

  return (
    <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk max-w-[760px] mx-auto px-6 py-12">
      <div className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2">
        BuilderOps · Repo Status
      </div>
      <h1 className="font-display text-[clamp(36px,7vw,56px)] font-extrabold tracking-tight mb-8">
        {repo.name}
      </h1>

      <ConvergenceDiagram standardsProgress={standardsProgress} pipelineProgress={0} testingProgress={0} />

      <div className="mt-8 flex flex-col gap-4">
        <StationCard
          code="ON-01"
          title="Onboarded"
          description="The repo now lives on GitHub and no longer exists in Azure DevOps."
          badge={
            repo.current_stage === "onboarded"
              ? "You are here"
              : repo.stages.migrated_from_ado?.status === "pass"
                ? "Cleared"
                : "You are here"
          }
          trackColor="#A79AE8"
          check={repo.stages.migrated_from_ado}
        />
        <StationCard
          code="ST-01"
          title="Standardized"
          description="Repo hygiene, ownership, and access controls are in place."
          badge={
            repo.current_stage === "standardized" && repo.is_stuck
              ? "You are here"
              : repo.current_stage === "onboarded"
                ? "Locked"
                : "Cleared"
          }
          trackColor="#A79AE8"
          check={primaryStandardizedCheck(repo)}
          lockedNote={repo.current_stage === "onboarded" ? "Not started. Unlocks once Onboarded clears." : undefined}
        />
        <StationCard
          code="PI-01"
          title="Piped"
          description="GitHub Actions are wired up for every environment and verified working."
          badge="Locked"
          trackColor="#3FBBA0"
          lockedNote="Not live yet — unlocks once the CI/CD connector ships."
        />
        <StationCard
          code="TS-01"
          title="Tested"
          description="Load testing, end-to-end testing, and code coverage all clear."
          badge="Locked"
          trackColor="#E7975C"
          lockedNote="Not live yet — unlocks once the E2E/load connector ships."
        />
        <StationCard
          code="PV-01"
          title="Paved Road"
          description="Every station cleared — this repo ships to prod with no manual gates."
          badge="Locked"
          trackColor="#EFC24B"
          lockedNote="Not started. Unlocks once Piped and Tested both ship."
        />
      </div>

      {repo.is_stuck && repo.stuck_reason ? (
        <div className="mt-6 rounded-lg border border-track3/40 bg-track3/10 text-track3 p-3 text-[13px]">
          {repo.stuck_reason}
        </div>
      ) : null}

      <div className="mt-8">
        <RepoFieldsForm repo={repo} onUpdated={setRepo} />
        <OnboardingLog repoId={repo.id} />
      </div>
    </div>
  );
}
