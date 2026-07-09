import { useId, useState } from "react";
import { patchRepo } from "../../api/client";
import type { RepoOut, RepoPatchIn } from "../../api/types";

const WAVE_OPTIONS: { value: RepoOut["migration_wave"]; label: string }[] = [
  { value: "not_started", label: "Not started" },
  { value: "pilot", label: "Pilot" },
  { value: "rolling_out", label: "Rolling out" },
  { value: "migrated", label: "Migrated" },
];

const DOCKERIZE_OPTIONS: { value: "unset" | "true" | "false"; label: string }[] = [
  { value: "unset", label: "Not yet assessed" },
  { value: "true", label: "Eligible" },
  { value: "false", label: "Not eligible" },
];

function dockerizeEligibleToOption(value: boolean | null | undefined): "unset" | "true" | "false" {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unset";
}

export function RepoFieldsForm({ repo, onUpdated }: { repo: RepoOut; onUpdated: (repo: RepoOut) => void }) {
  const [domain, setDomain] = useState(repo.domain ?? "");
  const [team, setTeam] = useState(repo.team ?? "");
  const [wave, setWave] = useState(repo.migration_wave);
  const [dockerizeEligible, setDockerizeEligible] = useState(dockerizeEligibleToOption(repo.dockerize_eligible));
  const [e2eTestPlanId, setE2eTestPlanId] = useState(
    repo.e2e_test_plan_id != null ? String(repo.e2e_test_plan_id) : ""
  );
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const domainId = useId();
  const teamId = useId();
  const waveId = useId();
  const dockerizeId = useId();
  const e2eTestPlanIdId = useId();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const body: RepoPatchIn = {
        domain,
        team,
        migration_wave: wave as RepoPatchIn["migration_wave"],
      };
      if (dockerizeEligible !== "unset") {
        body.dockerize_eligible = dockerizeEligible === "true";
      }
      if (e2eTestPlanId.trim() !== "") {
        const parsed = Number(e2eTestPlanId);
        if (!Number.isNaN(parsed)) {
          body.e2e_test_plan_id = parsed;
        }
      }
      const updated = await patchRepo(repo.id, body);
      onUpdated(updated);
      setSaved(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="bg-bg-card border border-card-border rounded-xl p-4 flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <label htmlFor={domainId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Domain
        </label>
        <input
          id={domainId}
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={teamId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Team
        </label>
        <input
          id={teamId}
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={waveId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Rollout wave
        </label>
        <select
          id={waveId}
          value={wave}
          onChange={(e) => setWave(e.target.value as RepoOut["migration_wave"])}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        >
          {WAVE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={dockerizeId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          Dockerize eligible
        </label>
        <select
          id={dockerizeId}
          value={dockerizeEligible}
          onChange={(e) => setDockerizeEligible(e.target.value as "unset" | "true" | "false")}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        >
          {DOCKERIZE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={e2eTestPlanIdId} className="font-mono text-[10.5px] text-chalk-dim uppercase">
          E2E test plan ID
        </label>
        <input
          id={e2eTestPlanIdId}
          type="number"
          value={e2eTestPlanId}
          onChange={(e) => setE2eTestPlanId(e.target.value)}
          className="bg-bg border border-card-border rounded px-2 py-1.5 text-[13px] text-chalk"
        />
      </div>
      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={saving}
          className="bg-gold text-bg font-semibold text-[12px] rounded px-3 py-1.5 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {saved ? <span className="text-[12px] text-track2">Saved</span> : null}
        {error ? <span className="text-[12px] text-track3">{error}</span> : null}
      </div>
    </form>
  );
}
