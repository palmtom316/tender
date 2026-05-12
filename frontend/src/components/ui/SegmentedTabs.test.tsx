import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SegmentedTabs } from "./SegmentedTabs";

const items = [
  { id: "vehicle", label: "车辆", count: 2 },
  { id: "equipment", label: "施工机械", count: 4 },
];

describe("SegmentedTabs", () => {
  it("marks the selected tab accessibly and calls onChange", () => {
    const onChange = vi.fn();
    render(<SegmentedTabs ariaLabel="资产分类" items={items} value="vehicle" onChange={onChange} />);

    expect(screen.getByRole("tab", { name: "车辆 2" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "施工机械 4" }));
    expect(onChange).toHaveBeenCalledWith("equipment");
  });
});
