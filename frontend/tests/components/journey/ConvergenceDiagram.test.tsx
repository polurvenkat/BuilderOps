import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConvergenceDiagram } from "../../../src/components/journey/ConvergenceDiagram";

describe("ConvergenceDiagram", () => {
  it("renders three progress paths with dasharray reflecting their progress props", () => {
    const { container } = render(
      <ConvergenceDiagram standardsProgress={1} pipelineProgress={0.5} testingProgress={0} />
    );

    const paths = container.querySelectorAll("path[data-line]");
    expect(paths).toHaveLength(3);

    const standards = container.querySelector('path[data-line="standards"]');
    const pipeline = container.querySelector('path[data-line="pipeline"]');
    const testing = container.querySelector('path[data-line="testing"]');

    expect(standards?.getAttribute("stroke-dasharray")).toBe("100 100");
    expect(pipeline?.getAttribute("stroke-dasharray")).toBe("50 100");
    expect(testing?.getAttribute("stroke-dasharray")).toBe("0 100");
  });

  it("uses the approved track colors", () => {
    const { container } = render(
      <ConvergenceDiagram standardsProgress={1} pipelineProgress={1} testingProgress={1} />
    );

    expect(container.querySelector('path[data-line="standards"]')?.getAttribute("stroke")).toBe("#A79AE8");
    expect(container.querySelector('path[data-line="pipeline"]')?.getAttribute("stroke")).toBe("#3FBBA0");
    expect(container.querySelector('path[data-line="testing"]')?.getAttribute("stroke")).toBe("#E7975C");
  });
});
