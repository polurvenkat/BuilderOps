import { useId, useState } from "react";

export function DetailsToggle({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  return (
    <div>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((prev) => !prev)}
        className="text-chalk-dim text-[12.5px] font-semibold flex items-center gap-1.5 py-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-gold"
      >
        <span className={`text-[10px] transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
        Details
      </button>
      <div
        id={panelId}
        className="grid transition-[grid-template-rows] duration-200"
        style={{ gridTemplateRows: open ? "1fr" : "0fr" }}
      >
        <div className="overflow-hidden">{children}</div>
      </div>
    </div>
  );
}
