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

    expect(await screen.findByText("没有匹配条款")).toBeInTheDocument();
    expect(
      screen.getByText("尝试更换关键词，或确认规范已完成 AI 解析。"),
    ).toBeInTheDocument();
    expect(screen.queryByText("检索规范条款")).not.toBeInTheDocument();
  });
});
