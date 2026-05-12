import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClayButton } from "./ClayButton";

describe("ClayButton", () => {
  it("maps secondary to outline for backwards compatibility", () => {
    render(<ClayButton variant="secondary">次级</ClayButton>);
    expect(screen.getByRole("button", { name: "次级" })).toHaveClass("clay-btn--outline");
  });

  it("exposes busy state when loading", () => {
    render(<ClayButton loading>保存</ClayButton>);
    const button = screen.getByRole("button", { name: "保存中" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});
