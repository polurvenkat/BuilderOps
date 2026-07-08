import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useRepos } from "../hooks/useRepos";
import { STAGE_LABELS, formatDwell } from "../lib/format";
import type { RepoOut } from "../api/types";

const CHECK_COLUMNS = [
  "migrated_from_ado",
  "codeowners_assigned",
  "domain_assigned",
  "branch_protection",
  "readme_present",
  "naming_standardized",
];

function checkIcon(status: string | undefined): string {
  if (status === "pass") return "✓";
  if (status === "fail") return "✗";
  return "?";
}

function sortByDwellDesc(repos: RepoOut[]): RepoOut[] {
  return [...repos].sort((a, b) => {
    const aStuck = a.is_stuck ? 1 : 0;
    const bStuck = b.is_stuck ? 1 : 0;
    if (aStuck !== bStuck) return bStuck - aStuck;
    return (b.dwell_days ?? 0) - (a.dwell_days ?? 0);
  });
}

function toCsv(repos: RepoOut[]): string {
  const header = ["Name", "Domain", "Team", "Wave", "Stage", "Dwell Days", ...CHECK_COLUMNS];
  const rows = repos.map((r) => [
    r.name,
    r.domain ?? "",
    r.team ?? "",
    r.migration_wave,
    r.current_stage,
    String(r.dwell_days ?? ""),
    ...CHECK_COLUMNS.map((key) => r.stages[key]?.status ?? ""),
  ]);
  return [header, ...rows].map((row) => row.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(",")).join("\n");
}

function downloadCsv(repos: RepoOut[]) {
  const csv = toCsv(repos);
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "repos.csv";
  a.click();
  URL.revokeObjectURL(url);
}

export function RepoTablePage() {
  const { repos } = useRepos();
  const [searchParams] = useSearchParams();
  const [stageFilter, setStageFilter] = useState(searchParams.get("stage") ?? "");
  const [domainFilter, setDomainFilter] = useState("");
  const [waveFilter, setWaveFilter] = useState("");
  const [search, setSearch] = useState("");

  const domains = useMemo(() => Array.from(new Set(repos.map((r) => r.domain).filter(Boolean))) as string[], [repos]);

  const filtered = sortByDwellDesc(repos.filter((r) => {
    if (stageFilter && r.current_stage !== stageFilter) return false;
    if (domainFilter && r.domain !== domainFilter) return false;
    if (waveFilter && r.migration_wave !== waveFilter) return false;
    if (search && !r.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  }));

  return (
    <div className="min-h-screen bg-bg text-chalk max-w-[1180px] mx-auto px-6 py-12">
      <h1 className="font-display text-[28px] font-extrabold mb-6">Repos</h1>

      <div className="flex gap-3 mb-4 items-end">
        <div>
          <label htmlFor="domain-filter" className="block font-mono text-[10.5px] text-chalk-dim uppercase mb-1">
            Domain
          </label>
          <select
            id="domain-filter"
            value={domainFilter}
            onChange={(e) => setDomainFilter(e.target.value)}
            className="bg-bg-card border border-card-border rounded px-2 py-1 text-[12px]"
          >
            <option value="">All domains</option>
            {domains.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="wave-filter" className="block font-mono text-[10.5px] text-chalk-dim uppercase mb-1">
            Wave
          </label>
          <select
            id="wave-filter"
            value={waveFilter}
            onChange={(e) => setWaveFilter(e.target.value)}
            className="bg-bg-card border border-card-border rounded px-2 py-1 text-[12px]"
          >
            <option value="">All waves</option>
            <option value="not_started">Not started</option>
            <option value="pilot">Pilot</option>
            <option value="rolling_out">Rolling out</option>
            <option value="migrated">Migrated</option>
          </select>
        </div>
        <div>
          <label htmlFor="name-search" className="block font-mono text-[10.5px] text-chalk-dim uppercase mb-1">
            Search
          </label>
          <input
            id="name-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by name…"
            className="bg-bg-card border border-card-border rounded px-2 py-1 text-[12px]"
          />
        </div>
        <button
          type="button"
          onClick={() => downloadCsv(filtered)}
          className="self-end bg-bg-card border border-card-border rounded px-3 py-1.5 text-[12px] text-chalk-dim hover:text-chalk"
        >
          Export CSV
        </button>
      </div>

      {stageFilter ? (
        <button
          type="button"
          onClick={() => setStageFilter("")}
          className="mb-4 font-mono text-[11px] text-chalk-dim underline"
        >
          Clear stage filter: {STAGE_LABELS[stageFilter] ?? stageFilter} ×
        </button>
      ) : null}

      <div className="overflow-x-auto">
        <table className="w-full text-[12px] border-collapse">
          <thead>
            <tr className="text-left text-chalk-dim font-mono text-[10.5px] uppercase border-b border-card-border">
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 pr-3">Domain</th>
              <th className="py-2 pr-3">Team</th>
              <th className="py-2 pr-3">Wave</th>
              <th className="py-2 pr-3">Stage</th>
              <th className="py-2 pr-3">Dwell</th>
              {CHECK_COLUMNS.map((key) => (
                <th key={key} className="py-2 pr-3" title={key}>
                  {key.slice(0, 4)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((repo) => (
              <tr key={repo.id} className="border-b border-card-border">
                <td className="py-2 pr-3">
                  <Link to={`/repos/${repo.id}`} className="text-gold hover:underline">
                    {repo.name}
                  </Link>
                </td>
                <td className="py-2 pr-3">{repo.domain ?? "—"}</td>
                <td className="py-2 pr-3">{repo.team ?? "—"}</td>
                <td className="py-2 pr-3">{repo.migration_wave}</td>
                <td className="py-2 pr-3">{STAGE_LABELS[repo.current_stage] ?? repo.current_stage}</td>
                <td className="py-2 pr-3 font-mono">{formatDwell(repo.dwell_days)}</td>
                {CHECK_COLUMNS.map((key) => (
                  <td key={key} className="py-2 pr-3 text-center">
                    {checkIcon(repo.stages[key]?.status)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
