import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./EmptyState";


describe("EmptyState", () => {
  it("renders title, description, icon, and action", () => {
    render(
      <EmptyState
        icon="项"
        title="先选择投标项目"
        description="选择项目后，可继续上传和解析招标文件。"
        action={<button type="button">去选择</button>}
      />,
    );

    expect(screen.getByText("项")).toBeInTheDocument();
    expect(screen.getByText("先选择投标项目")).toBeInTheDocument();
    expect(screen.getByText("选择项目后，可继续上传和解析招标文件。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "去选择" })).toBeInTheDocument();
  });
});
