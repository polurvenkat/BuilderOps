import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PipelineStatusPanel } from "../../../src/components/journey/PipelineStatusPanel";

describe("PipelineStatusPanel", () => {
  it("shows a loading state", () => {
    render(<PipelineStatusPanel stages={null} loading={true} error={null} />);

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it("shows an error banner on failure, with no stage data", () => {
    render(<PipelineStatusPanel stages={null} loading={false} error="HTTP 502" />);

    expect(screen.getByText(/Couldn't reach Azure DevOps/)).toBeInTheDocument();
  });

  it("renders each stage's name and status", () => {
    render(
      <PipelineStatusPanel
        stages={[
          { name: "Build", status: "succeeded", pending_approval_description: null },
          { name: "DEV", status: "succeeded", pending_approval_description: null },
          { name: "UAT", status: "waiting_approval", pending_approval_description: "Needs sign-off" },
        ]}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText("Build")).toBeInTheDocument();
    expect(screen.getAllByText("succeeded")).toHaveLength(2);
    expect(screen.getByText("waiting_approval")).toBeInTheDocument();
  });

  it("surfaces a pending-approval callout with its description", () => {
    render(
      <PipelineStatusPanel
        stages={[{ name: "UAT", status: "waiting_approval", pending_approval_description: "Needs sign-off" }]}
        loading={false}
        error={null}
      />
    );

    expect(screen.getByText(/Needs sign-off/)).toBeInTheDocument();
  });
});
