import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { App } from "../src/App";

describe("App routing", () => {
  it("renders the Fleet page at /", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <App useMemoryRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("fleet-page")).toBeInTheDocument();
  });

  it("renders the Journey page at /repos/:id", () => {
    render(
      <MemoryRouter initialEntries={["/repos/42"]}>
        <App useMemoryRouter />
      </MemoryRouter>
    );
    expect(screen.getByTestId("journey-page")).toBeInTheDocument();
  });
});
