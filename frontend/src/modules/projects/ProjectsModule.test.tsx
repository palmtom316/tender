import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const {
  listProjectsMock,
  createProjectMock,
  deleteProjectMock,
  listTemplatePackagesMock,
  confirmTemplateSelectionMock,
  navValue,
} = vi.hoisted(() => ({
  listProjectsMock: vi.fn(),
  createProjectMock: vi.fn(),
  deleteProjectMock: vi.fn(),
  listTemplatePackagesMock: vi.fn(),
  confirmTemplateSelectionMock: vi.fn(),
  navValue: {
    tab: "all",
    projectId: null,
    setProjectId: vi.fn(),
    setDocumentId: vi.fn(),
    navigate: vi.fn(),
  },
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    listProjects: listProjectsMock,
    createProject: createProjectMock,
    deleteProject: deleteProjectMock,
    listTemplatePackages: listTemplatePackagesMock,
    confirmTemplateSelection: confirmTemplateSelectionMock,
  };
});

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: () => navValue,
}));

import { ProjectsModule } from "./ProjectsModule";

function renderModule() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProjectsModule />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ProjectsModule", () => {
  it("uses six template kinds, preserves voltage level, and does not ask for bid bond", async () => {
    listProjectsMock.mockResolvedValue([]);
    createProjectMock.mockResolvedValue({ id: "p1", name: "测试项目", created_at: "2026-05-13T00:00:00Z" });

    renderModule();
    fireEvent.click(screen.getByRole("button", { name: "新建项目" }));

    const kindSelect = screen.getByLabelText("招标文件模板种类");
    expect(within(kindSelect).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "国网变电工程",
      "国网运维工程",
      "国网配网工程",
      "国网低压营配工程",
      "用户配电工程",
      "用户运维工程",
    ]);
    expect(screen.getByLabelText("电压等级")).toBeInTheDocument();
    expect(screen.queryByLabelText("保证金")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "测试项目" } });
    fireEvent.change(kindSelect, { target: { value: "user_maintenance" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() => expect(createProjectMock).toHaveBeenCalled());
    expect(createProjectMock.mock.calls[0][0]).toEqual(expect.objectContaining({
      project_type: "user_maintenance",
      business_line: "user_maintenance",
      sub_type: "user_maintenance",
      voltage_level: ["10kV"],
    }));
    expect(createProjectMock.mock.calls[0][0]).not.toHaveProperty("bid_bond_amount");
  });

  it("renders project dates as yyyy/mm/dd", async () => {
    listTemplatePackagesMock.mockResolvedValue([]);
    listProjectsMock.mockResolvedValue([
      { id: "p1", name: "日期项目", created_at: "2026-05-13T08:30:00Z", status: "draft", workflow_status: "created", submission_deadline: "2026-06-01T10:00:00Z" },
    ]);

    renderModule();

    expect(await screen.findByText("2026/05/13")).toBeInTheDocument();
    expect(screen.getByText("截止 2026/06/01")).toBeInTheDocument();
  });

  it("shows available template packages and confirms selected package after project creation", async () => {
    listProjectsMock.mockResolvedValue([]);
    listTemplatePackagesMock.mockResolvedValue([
      {
        id: "pkg-1",
        package_key: "sgcc-distribution-business-single-docx",
        display_name: "国网配网工程商务标",
        package_type: "business",
        category_code: "sgcc_distribution",
        source_root: "/tmp/templates",
        item_count: 1,
      },
    ]);
    createProjectMock.mockResolvedValue({ id: "p1", name: "测试项目", created_at: "2026-05-13T00:00:00Z" });
    confirmTemplateSelectionMock.mockResolvedValue({ selected_template_package_id: "pkg-1" });

    renderModule();
    fireEvent.click(screen.getByRole("button", { name: "新建项目" }));

    expect(await screen.findByText("国网配网工程商务标")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("选择模板包 国网配网工程商务标"));
    fireEvent.change(screen.getByLabelText("项目名称"), { target: { value: "测试项目" } });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() => expect(createProjectMock).toHaveBeenCalled());
    await waitFor(() => expect(confirmTemplateSelectionMock).toHaveBeenCalledWith("p1", "pkg-1"));
  });
});
