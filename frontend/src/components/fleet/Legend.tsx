const ENTRIES: { color: string; label: string }[] = [
  { color: "#A79AE8", label: "Repo standards" },
  { color: "#3FBBA0", label: "CI/CD & environments" },
  { color: "#E7975C", label: "E2E & load testing" },
  { color: "#EFC24B", label: "Paved — ready to ship" },
];

export function Legend() {
  return (
    <div className="flex flex-wrap gap-2.5 mb-6">
      {ENTRIES.map((entry) => (
        <div
          key={entry.label}
          className="flex items-center gap-1.5 bg-bg-card border border-card-border rounded-full py-1 pl-2 pr-3 font-mono text-[11px] text-chalk-dim"
        >
          <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
          {entry.label}
        </div>
      ))}
    </div>
  );
}
