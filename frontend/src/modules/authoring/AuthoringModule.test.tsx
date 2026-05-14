import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { navValue } = vi.hoisted(() => ({
  navValue: {
    tab: "template",
    projectId: "p1",
    navigate: vi.fn(),
  },
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: () => navValue,
}));

vi.mock("./UploadContent", () => ({ UploadContent: () => <div>Upload</div> }));
vi.mock("./ParseContent", () => ({ ParseContent: () => <div>Parse</div> }));
vi.mock("./RequirementsContent", () => ({ RequirementsContent: () => <div>Requirements</div> }));
vi.mock("./EditorContent", () => ({ EditorContent: () => <div>Editor</div> }));
vi.mock("../templates/ProjectTemplateWorkbench", () => ({ ProjectTemplateWorkbench: () => <div aria-label="项目模板调整">Template</div> }));

import { AuthoringModule } from "./AuthoringModule";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AuthoringModule workflow strip", () => {
  it("marks template adjustment active on the template tab", () => {
    render(<AuthoringModule />);

    expect(screen.getByLabelText("项目模板调整")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /模板调整当前/ })).toHaveAttribute("aria-current", "step");
  });
});
