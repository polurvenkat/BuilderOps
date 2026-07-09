import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useRepo } from "../hooks/useRepo";
import { usePipelineStatus } from "../hooks/usePipelineStatus";
import { ConvergenceDiagram } from "../components/journey/ConvergenceDiagram";
import { StationCard } from "../components/journey/StationCard";
import { RepoFieldsForm } from "../components/journey/RepoFieldsForm";
import { PipelineStatusPanel } from "../components/journey/PipelineStatusPanel";
import { OnboardingLog } from "../components/journey/OnboardingLog";
import type { PipelineStageStatusOut, RepoOut } from "../api/types";

const STANDARDIZED_KEYS = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];
const STANDARDIZED_CHECK_ORDER = ["codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"];

const PIPED_CHECK_ORDER = ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized", "deployed_aca"];
const PIPED_CHECK_LABELS: Record<string, string> = {
  pipeline_linked: "Pipeline linked",
  pipeline_is_yaml: "YAML pipeline",
  environment_gates_configured: "Environment gates",
  dockerized: "Dockerized",
  deployed_aca: "Deployed to ACA",
};
const PIPED_BLOCKING_KEYS = ["pipeline_linked", "pipeline_is_yaml", "environment_gates_configured", "dockerized"];
const DEPLOY_STAGE_NAMES = ["dev", "qa", "uat", "prod"];

const TESTED_CHECK_ORDER = ["e2e_covered", "unit_tested", "integration_tested", "load_tested"];
const TESTED_CHECK_LABELS: Record<string, string> = {
  e2e_covered: "E2E coverage",
  unit_tested: "Unit tests",
  integration_tested: "Integration tests",
  load_tested: "Load tests",
};

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

function pipelineLinked(repo: RepoOut): boolean {
  return repo.stages.pipeline_linked?.status === "pass";
}

function pipedBadge(repo: RepoOut): "Cleared" | "You are here" | "Locked" {
  if (!pipelineLinked(repo)) return "Locked";
  const allBlockingPass = PIPED_BLOCKING_KEYS.every((key) => repo.stages[key]?.status === "pass");
  return allBlockingPass ? "Cleared" : "You are here";
}

function pipedChecks(repo: RepoOut) {
  return PIPED_CHECK_ORDER.map((key) => ({ label: PIPED_CHECK_LABELS[key], check: repo.stages[key] }));
}

function pipelineProgressFraction(stages: PipelineStageStatusOut[] | null): number {
  if (!stages) return 0;
  const relevant = stages.filter((s) =>
    DEPLOY_STAGE_NAMES.some((name) => s.name.toLowerCase().includes(name))
  );
  if (relevant.length === 0) return 0;
  return relevant.filter((s) => s.status === "succeeded").length / relevant.length;
}

function testedBadge(repo: RepoOut): "Cleared" | "You are here" | "Locked" {
  const status = repo.stages.e2e_covered?.status;
  if (status === "pass") return "Cleared";
  if (!status || status === "pending_convention") return "Locked";
  return "You are here";
}

function testedChecks(repo: RepoOut) {
  return TESTED_CHECK_ORDER.map((key) => ({ label: TESTED_CHECK_LABELS[key], check: repo.stages[key] }));
}

export function JourneyPage() {
  const { id } = useParams<{ id: string }>();
  const { repo: fetchedRepo, loading, error } = useRepo(Number(id));
  const [repo, setRepo] = useState<RepoOut | null>(null);

  useEffect(() => {
    if (fetchedRepo) setRepo(fetchedRepo);
  }, [fetchedRepo]);

  const linked = repo ? pipelineLinked(repo) : false;
  const { stages: pipelineStages, loading: pipelineLoading, error: pipelineError } = usePipelineStatus(
    repo?.id ?? 0,
    linked
  );

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
  const pipelineProgress = pipelineProgressFraction(pipelineStages);
  const testingProgress = repo.stages.e2e_covered?.status === "pass" ? 1 : 0;

  return (
    <div data-testid="journey-page" className="min-h-screen bg-bg text-chalk max-w-[760px] mx-auto px-6 py-12">
      <Link
        to="/"
        className="font-mono text-[11px] text-chalk-dim uppercase tracking-wide mb-2 inline-block hover:text-chalk"
      >
        ← BuilderOps · Repo Status
      </Link>
      <h1 className="font-display text-[clamp(36px,7vw,56px)] font-extrabold tracking-tight mb-8">
        {repo.name}
      </h1>

      <ConvergenceDiagram standardsProgress={standardsProgress} pipelineProgress={pipelineProgress} testingProgress={testingProgress} />

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
          description="Azure Pipelines is wired up and the YAML pipeline deploys cleanly through every environment."
          badge={pipedBadge(repo)}
          trackColor="#3FBBA0"
          checks={pipedChecks(repo)}
          lockedNote={!linked ? "Not connected — link the pipeline ID below, or wait for the next sync." : undefined}
        />
        <StationCard
          code="TS-01"
          title="Tested"
          description="End-to-end tests are passing on the latest Azure Test Plans run."
          badge={testedBadge(repo)}
          trackColor="#E7975C"
          checks={testedChecks(repo)}
          lockedNote={testedBadge(repo) === "Locked" ? "Not live yet — unlocks once an E2E Test Plan is mapped." : undefined}
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
        {linked ? (
          <PipelineStatusPanel stages={pipelineStages} loading={pipelineLoading} error={pipelineError} />
        ) : null}
        <OnboardingLog repoId={repo.id} />
      </div>
    </div>
  );
}
