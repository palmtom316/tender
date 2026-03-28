import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { StandardSearchCard } from "./StandardSearchCard";

const { searchStandardClauses } = vi.hoisted(() => ({
  searchStandardClauses: vi.fn(),
}));

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../../lib/api")>("../../../lib/api");
  return {
    ...actual,
    searchStandardClauses,
  };
});

describe("StandardSearchCard", () => {
  it("shows an explicit empty-result message after a completed search", async () => {
    searchStandardClauses.mockResolvedValueOnce([]);

    render(<StandardSearchCard onOpenHit={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText(/输入关键词/), {
      target: { value: "变压器" },
    });
    fireEvent.click(screen.getByRole("button", { name: "查询" }));

    await waitFor(() => {
      expect(searchStandardClauses).toHaveBeenCalledWith("变压器");
    });

    expect(
      await screen.findByText("未找到匹配的规范条款，请尝试更换关键词。"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("输入关键词后，可在这里查看命中的规范条款。"),
    ).not.toBeInTheDocument();
  });
});
