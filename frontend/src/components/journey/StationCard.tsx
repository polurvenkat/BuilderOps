import type { StageCheckOut } from "../../api/types";
import { DetailsToggle } from "./DetailsToggle";

interface StationCardProps {
  code: string;
  title: string;
  description: string;
  badge: "Cleared" | "You are here" | "Locked";
  trackColor: string;
  check?: StageCheckOut;
  lockedNote?: string;
}

const BADGE_STYLES: Record<StationCardProps["badge"], string> = {
  Cleared: "bg-white/[0.08] text-chalk-dim",
  "You are here": "bg-gold/15 text-gold",
  Locked: "bg-chalk-dimmer/20 text-chalk-dimmer",
};

export function StationCard({ code, title, description, badge, trackColor, check, lockedNote }: StationCardProps) {
  const isLocked = badge === "Locked";

  return (
    <div
      className={`rounded-xl border border-card-border p-4 ${isLocked ? "bg-bg-card-locked" : "bg-bg-card"}`}
      style={{ borderTopWidth: 3, borderTopColor: trackColor }}
    >
      <div className="flex justify-between items-center mb-2">
        <span className="font-mono text-[11px] text-chalk-dimmer">{code}</span>
        <span className={`font-mono text-[10.5px] font-semibold px-2 py-0.5 rounded ${BADGE_STYLES[badge]}`}>
          {badge}
        </span>
      </div>
      <h3 className={`font-display text-[21px] font-bold mb-1.5 ${isLocked ? "text-chalk-dim" : ""}`}>{title}</h3>
      <p className={`text-[14.5px] mb-2.5 ${isLocked ? "opacity-60" : "opacity-90"}`}>{description}</p>

      {isLocked ? (
        <p className="text-[13px] text-chalk-dim pt-2">{lockedNote}</p>
      ) : (
        <DetailsToggle>
          {check ? (
            <div className="flex justify-between text-[13px] py-2 border-t border-card-border">
              <span className="opacity-85">Status: {check.status}</span>
              <span className="font-mono text-[11px] text-chalk-dimmer">
                {check.updated_at ? new Date(check.updated_at).toLocaleDateString() : "—"}
              </span>
            </div>
          ) : null}
        </DetailsToggle>
      )}
    </div>
  );
}
