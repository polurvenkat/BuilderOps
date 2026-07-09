import { useState } from "react";
import { patchRepo } from "../../api/client";
import { toKebabCase } from "../../lib/format";
import type { RepoOut } from "../../api/types";

const COMPLEXITY_COLOR: Record<string, string> = {
  low: "text-track2",
  medium: "text-gold",
  high: "text-track3",
};

function InventoryRow({ repo, onUpdated }: { repo: RepoOut; onUpdated: (repo: RepoOut) => void }) {
  const [newName, setNewName] = useState(toKebabCase(repo.name));
  const [appCount, setAppCount] = useState(repo.app_count != null ? String(repo.app_count) : "");
  const [renaming, setRenaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const trimmedNewName = newName.trim();
  const applyDisabled = renaming || trimmedNewName === "" || trimmedNewName === repo.name;

  async function handleRename() {
    if (applyDisabled) return;
    const confirmed = window.confirm(
      `Rename the real GitHub repository from "${repo.name}" to "${trimmedNewName}"? This is a live, hard-to-reverse action.`
    );
    if (!confirmed) return;

    setRenaming(true);
    setError(null);
    setNote(null);
    try {
      const updated = await patchRepo(repo.id, { new_name: trimmedNewName });
      onUpdated(updated);
      setNewName(toKebabCase(updated.name));
      setNote("Pipeline links re-check on the next sync.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setRenaming(false);
    }
  }

  async function commitAppCount() {
    setError(null);
    const trimmed = appCount.trim();
    if (trimmed === "") return;
    const parsed = Number(trimmed);
    if (Number.isNaN(parsed) || parsed === repo.app_count) return;
    try {
      const updated = await patchRepo(repo.id, { app_count: parsed });
      onUpdated(updated);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <tr className="border-b border-card-border">
      <td className="p-2.5 align-top">
        <div className="text-chalk mb-1.5">{repo.name}</div>
        <div className="flex items-center gap-1.5">
          <span className="text-chalk-dimmer text-[11px]">{repo.name} →</span>
          <input
            aria-label={`New name for ${repo.name}`}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="bg-bg border border-card-border rounded px-1.5 py-0.5 text-[11px] text-chalk w-[260px]"
          />
          <button
            onClick={handleRename}
            disabled={applyDisabled}
            className="bg-gold text-bg font-semibold text-[11px] rounded px-2.5 py-0.5 disabled:opacity-40"
          >
            {renaming ? "Renaming…" : "Apply"}
          </button>
        </div>
        {note ? <div className="text-[11px] text-track2 mt-1">{note}</div> : null}
        {error ? <div className="text-[11px] text-track3 mt-1">{error}</div> : null}
      </td>
      <td className="p-2.5 align-top">
        <input
          aria-label={`App count for ${repo.name}`}
          type="number"
          value={appCount}
          onChange={(e) => setAppCount(e.target.value)}
          onBlur={commitAppCount}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
          className="bg-bg border border-card-border rounded px-1.5 py-0.5 text-[13px] text-chalk w-[50px] text-center"
        />
      </td>
      <td className="p-2.5 align-top">
        <span className="bg-bg-card border border-card-border rounded px-2 py-0.5 text-[12px] text-chalk">
          {repo.primary_language ?? "—"}
        </span>
      </td>
      <td className="p-2.5 align-top">
        <span
          className={`bg-bg-card border border-card-border rounded px-2 py-0.5 text-[12px] capitalize ${
            repo.complexity ? COMPLEXITY_COLOR[repo.complexity] : "text-chalk-dimmer"
          }`}
        >
          {repo.complexity ?? "—"}
        </span>
      </td>
    </tr>
  );
}

export function InventoryTable({ repos, onUpdated }: { repos: RepoOut[]; onUpdated: (repo: RepoOut) => void }) {
  return (
    <table className="w-full border-collapse text-[12.5px]">
      <thead>
        <tr className="text-left text-chalk-dim uppercase text-[10px] tracking-wide">
          <th className="p-2.5 border-b border-card-border">Repo name</th>
          <th className="p-2.5 border-b border-card-border">Apps</th>
          <th className="p-2.5 border-b border-card-border">Technology</th>
          <th className="p-2.5 border-b border-card-border">Complexity</th>
        </tr>
      </thead>
      <tbody>
        {repos.map((repo) => (
          <InventoryRow key={repo.id} repo={repo} onUpdated={onUpdated} />
        ))}
      </tbody>
    </table>
  );
}
