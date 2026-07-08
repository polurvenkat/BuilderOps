import { useEffect, useId, useState } from "react";
import { getOnboardingLog, postOnboardingLog } from "../../api/client";
import type { OnboardingSummaryOut } from "../../api/types";

export function OnboardingLog({ repoId }: { repoId: number }) {
  const [summary, setSummary] = useState<OnboardingSummaryOut | null>(null);
  const [engineerName, setEngineerName] = useState("");
  const [hours, setHours] = useState("");
  const engineerId = useId();
  const hoursId = useId();

  function refetch() {
    getOnboardingLog(repoId).then(setSummary);
  }

  useEffect(() => {
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await postOnboardingLog(repoId, { engineer_name: engineerName, hours: Number(hours) });
    setEngineerName("");
    setHours("");
    refetch();
  }

  if (!summary) return null;

  return (
    <div className="bg-bg-card border border-card-border rounded-xl p-4 mt-4">
      <div className="font-mono text-[10.5px] text-chalk-dim uppercase mb-2">Onboarding time</div>
      {summary.median_hours === null ? (
        <p className="text-[13px] text-chalk-dim mb-3">No entries logged yet.</p>
      ) : (
        <p className="text-[13px] text-chalk mb-3">
          Median: <span className="font-mono">{summary.median_hours}</span> hrs ({summary.entries.length} entries)
        </p>
      )}
      <div className="flex flex-col gap-1 mb-3">
        {summary.entries.map((entry) => (
          <div key={entry.id} className="flex justify-between text-[12.5px] text-chalk-dim">
            <span>{entry.engineer_name}</span>
            <span className="font-mono">{entry.hours} hrs</span>
          </div>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="flex items-end gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={engineerId} className="font-mono text-[10px] text-chalk-dim">
            Engineer
          </label>
          <input
            id={engineerId}
            value={engineerName}
            onChange={(e) => setEngineerName(e.target.value)}
            className="bg-bg border border-card-border rounded px-2 py-1 text-[12px] text-chalk w-28"
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor={hoursId} className="font-mono text-[10px] text-chalk-dim">
            Hours
          </label>
          <input
            id={hoursId}
            type="number"
            step="0.5"
            value={hours}
            onChange={(e) => setHours(e.target.value)}
            className="bg-bg border border-card-border rounded px-2 py-1 text-[12px] text-chalk w-16"
          />
        </div>
        <button type="submit" className="bg-gold text-bg font-semibold text-[12px] rounded px-3 py-1.5">
          Log
        </button>
      </form>
    </div>
  );
}
