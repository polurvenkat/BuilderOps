export function formatDwell(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "<1d here";
  return `${days}d here`;
}

export const STAGE_LABELS: Record<string, string> = {
  onboarded: "Onboarded",
  standardized: "Standardized",
  piped: "Piped",
};
