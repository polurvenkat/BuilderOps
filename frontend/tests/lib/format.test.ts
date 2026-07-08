import { describe, expect, it } from "vitest";
import { formatDwell, STAGE_LABELS } from "../../src/lib/format";

describe("formatDwell", () => {
  it("returns empty string for null", () => {
    expect(formatDwell(null)).toBe("");
  });

  it("returns '<1d here' for 0 days", () => {
    expect(formatDwell(0)).toBe("<1d here");
  });

  it("returns 'Nd here' for N days", () => {
    expect(formatDwell(28)).toBe("28d here");
  });
});

describe("STAGE_LABELS", () => {
  it("labels the two real Phase 0 stages", () => {
    expect(STAGE_LABELS.onboarded).toBe("Onboarded");
    expect(STAGE_LABELS.standardized).toBe("Standardized");
  });
});
