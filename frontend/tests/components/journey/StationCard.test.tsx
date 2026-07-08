import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { StationCard } from "../../../src/components/journey/StationCard";

describe("StationCard", () => {
  it("renders the badge, title, and description", () => {
    render(
      <StationCard
        code="ST-01"
        title="Standardized"
        description="Repo hygiene, ownership, and access controls are in place."
        badge="Cleared"
        trackColor="#A79AE8"
      />
    );

    expect(screen.getByText("Cleared")).toBeInTheDocument();
    expect(screen.getByText("Standardized")).toBeInTheDocument();
  });

  it("shows the locked note instead of a details toggle when locked", () => {
    render(
      <StationCard
        code="PI-01"
        title="Piped"
        description="GitHub Actions are wired up for every environment."
        badge="Locked"
        trackColor="#3FBBA0"
        lockedNote="Not live yet — unlocks once the CI/CD connector ships."
      />
    );

    expect(screen.getByText(/Not live yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /details/i })).not.toBeInTheDocument();
  });

  it("toggles the details panel via a real accessible button", async () => {
    const user = userEvent.setup();
    render(
      <StationCard
        code="ON-01"
        title="Onboarded"
        description="Migrated from Azure DevOps."
        badge="Cleared"
        trackColor="#A79AE8"
        check={{ status: "pass", source: "auto", detail: null, updated_at: "2026-07-08T00:00:00Z" }}
      />
    );

    const button = screen.getByRole("button", { name: /details/i });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);

    expect(button).toHaveAttribute("aria-expanded", "true");
  });
});
