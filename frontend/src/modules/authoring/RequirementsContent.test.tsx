import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { useNavigationMock, fetchWorkbenchMock, fetchTenderSummaryMock, startRunMock, bulkConfirmMock, buildConstraintSetMock, fetchConstraintSetMock, confirmConstraintSetMock, listTenderClarificationsMock, createTenderClarificationMock, uploadTenderClarificationMock, fetchProjectEquipmentAssetsMock, fetchProjectEquipmentSelectionsMock, confirmProjectEquipmentSelectionsMock, createProjectEquipmentSelectionMock, deleteProjectEquipmentSelectionMock, updateProjectEquipmentSelectionMock, fetchProjectEquipmentPreviewMock } = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  fetchWorkbenchMock: vi.fn(),
  fetchTenderSummaryMock: vi.fn(),
  startRunMock: vi.fn(),
  bulkConfirmMock: vi.fn(),
  buildConstraintSetMock: vi.fn(),
  fetchConstraintSetMock: vi.fn(),
  confirmConstraintSetMock: vi.fn(),
  listTenderClarificationsMock: vi.fn(),
  createTenderClarificationMock: vi.fn(),
  uploadTenderClarificationMock: vi.fn(),
  fetchProjectEquipmentAssetsMock: vi.fn(),
  fetchProjectEquipmentSelectionsMock: vi.fn(),
  confirmProjectEquipmentSelectionsMock: vi.fn(),
  createProjectEquipmentSelectionMock: vi.fn(),
  deleteProjectEquipmentSelectionMock: vi.fn(),
  updateProjectEquipmentSelectionMock: vi.fn(),
  fetchProjectEquipmentPreviewMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchRequirementWorkbench: fetchWorkbenchMock,
    fetchTenderSummary: fetchTenderSummaryMock,
    startTenderAiExtractionRun: startRunMock,
    bulkConfirmRequirements: bulkConfirmMock,
    buildConstraintSet: buildConstraintSetMock,
    fetchConstraintSet: fetchConstraintSetMock,
    confirmConstraintSet: confirmConstraintSetMock,
    listTenderClarifications: listTenderClarificationsMock,
    createTenderClarification: createTenderClarificationMock,
    uploadTenderClarification: uploadTenderClarificationMock,
    fetchProjectEquipmentAssets: fetchProjectEquipmentAssetsMock,
    fetchProjectEquipmentSelections: fetchProjectEquipmentSelectionsMock,
    confirmProjectEquipmentSelections: confirmProjectEquipmentSelectionsMock,
    createProjectEquipmentSelection: createProjectEquipmentSelectionMock,
    deleteProjectEquipmentSelection: deleteProjectEquipmentSelectionMock,
    updateProjectEquipmentSelection: updateProjectEquipmentSelectionMock,
    fetchProjectEquipmentPreview: fetchProjectEquipmentPreviewMock,
  };
});

vi.mock("./SourceChunkViewer", () => ({
  SourceChunkViewer: () => null,
}));

vi.mock("./AiExtractionRunPanel", () => ({
  AiExtractionRunPanel: ({ runId }: { runId: string }) => <div>panel:{runId}</div>,
}));

import { RequirementsContent } from "./RequirementsContent";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

function summary() {
  return {
    project_id: "proj-1",
    tender_document_id: "doc-1",
    project_name: "示例项目",
    tenderer: "国网某公司",
    tender_agency: null,
    project_location: null,
    construction_period: null,
    quality_requirement: null,
    control_price: null,
    bid_bond: "10万元",
    bid_open_time: null,
    bid_deadline: "2026-05-20 09:00",
    raw_facts_json: {},
    source_chunk_ids_json: [],
    extracted_model: null,
  };
}

function workbench() {
  const critical = {
    id: "pkg-1",
    category: "veto",
    topic: "signature",
    lane: "red_lines",
    confirmation_level: "critical",
    title: "签章要求",
    system_conclusion: "投标文件需逐页盖章并签字。",
    source_count: 2,
    confirmed_count: 0,
    all_confirmed: false,
    blocking: true,
    has_conflict: true,
    conflict_fields: ["copy_count"],
    key_fields: { copy_count: ["正本1份", "正本2份"] },
    confidence: 0.91,
    requirements: ["req-1", "req-2"],
    sources: [
      {
        requirement_id: "req-1",
        title: "签章要求",
        source_file: "招标文件.docx",
        source_locator: "p12",
        source_chunk_id: "chunk-1",
        text: "正本1份需盖章。",
        human_confirmed: false,
      },
      {
        requirement_id: "req-2",
        title: "签章要求",
        source_file: "答疑.docx",
        source_locator: "p2",
        source_chunk_id: "chunk-2",
        text: "正本2份需盖章。",
        human_confirmed: false,
      },
    ],
  } as const;
  const sampling = {
    ...critical,
    id: "pkg-2",
    category: "technical",
    topic: "technical",
    lane: "sampling",
    confirmation_level: "auto_accept",
    title: "施工方案",
    system_conclusion: "按技术规范编制施工方案。",
    source_count: 1,
    confirmed_count: 0,
    blocking: false,
    has_conflict: false,
    conflict_fields: [],
    key_fields: {},
    requirements: ["req-3"],
    sources: [{ ...critical.sources[0], requirement_id: "req-3", text: "按技术规范编制施工方案。" }],
  } as const;
  return {
    project_id: "proj-1",
    stats: {
      total_requirements: 3,
      package_count: 2,
      critical_count: 1,
      blocking_count: 1,
      conflict_count: 1,
      auto_accept_count: 1,
      review_count: 0,
      ignored_count: 0,
    },
    lanes: [
      { id: "red_lines", label: "废标红线", packages: [critical] },
      { id: "sampling", label: "自动采纳抽查", packages: [sampling] },
    ],
    packages: [critical, sampling],
  };
}

describe("RequirementsContent workbench", () => {
  beforeEach(() => {
    cleanup();
    localStorage.clear();
    vi.clearAllMocks();
    useNavigationMock.mockReturnValue({ projectId: "proj-1", documentId: "doc-1" });
    fetchTenderSummaryMock.mockResolvedValue(summary());
    fetchWorkbenchMock.mockResolvedValue(workbench());
    fetchConstraintSetMock.mockResolvedValue({ project_id: "proj-1", items: [] });
    buildConstraintSetMock.mockResolvedValue({ id: "set-1", status: "draft", items: [{ id: "item-1" }] });
    confirmConstraintSetMock.mockResolvedValue({ id: "set-1", status: "confirmed", items: [{ id: "item-1" }] });
    listTenderClarificationsMock.mockResolvedValue([]);
    fetchProjectEquipmentAssetsMock.mockResolvedValue([]);
    fetchProjectEquipmentSelectionsMock.mockResolvedValue([]);
    confirmProjectEquipmentSelectionsMock.mockResolvedValue([]);
    createProjectEquipmentSelectionMock.mockResolvedValue({});
    deleteProjectEquipmentSelectionMock.mockResolvedValue({ deleted: true });
    updateProjectEquipmentSelectionMock.mockResolvedValue({});
    fetchProjectEquipmentPreviewMock.mockResolvedValue({ vehicle: [], machine: [], tool: [], safety: [] });
  });

  it("renders grouped critical clauses and auto-accepted sampling", async () => {
    render(withClient(<RequirementsContent />));

    expect(await screen.findByText("招标解析工作台")).toBeInTheDocument();
    expect(await screen.findAllByText("签章要求")).not.toHaveLength(0);
    expect(screen.getAllByText("字段冲突")).not.toHaveLength(0);
    expect(screen.getAllByText("自动采纳")).not.toHaveLength(0);
    expect(screen.getByText("普通条款已自动采纳并保留抽查；这里只处理会影响废标、资格商务、技术响应和递交清单的关键条款。")).toBeInTheDocument();
  });

  it("starts ai extraction and restores the run panel", async () => {
    startRunMock.mockResolvedValueOnce({ id: "run-123" });
    render(withClient(<RequirementsContent />));

    const button = await screen.findByRole("button", { name: "提交 AI 抽取任务" });
    button.click();

    await waitFor(() => expect(startRunMock).toHaveBeenCalledWith("doc-1"));
    expect(await screen.findByText("panel:run-123")).toBeInTheDocument();
    expect(localStorage.getItem("tender:ai-extraction-run:doc-1")).toBe("run-123");
  });

  it("bulk confirms a critical package", async () => {
    bulkConfirmMock.mockResolvedValueOnce({ confirmed_count: 2 });
    render(withClient(<RequirementsContent />));

    const button = (await screen.findAllByRole("button", { name: "确认本组" }))[0];
    button.click();

    await waitFor(() => expect(bulkConfirmMock).toHaveBeenCalledWith("proj-1", ["req-1", "req-2"]));
  });

  it("shows constraint-set milestone and confirms the set", async () => {
    fetchConstraintSetMock.mockResolvedValueOnce({ id: "set-1", status: "draft", items: [{ id: "item-1" }] });
    render(withClient(<RequirementsContent />));

    expect(await screen.findByLabelText("约束集确认里程碑")).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: "确认约束集" });
    fireEvent.click(button);

    await waitFor(() => expect(confirmConstraintSetMock).toHaveBeenCalledWith("proj-1"));
  });

  it("uploads clarification file for analysis", async () => {
    uploadTenderClarificationMock.mockResolvedValueOnce({
      id: "clar-1",
      project_id: "proj-1",
      round_no: 1,
      clarification_type: "addendum",
      title: "澄清/补遗文件",
      source_file: "答疑.pdf",
      content_text: "澄清内容",
      impact_json: {},
      status: "active",
      created_at: "2026-05-07T00:00:00Z",
    });
    render(withClient(<RequirementsContent />));

    const file = new File(["pdf"], "答疑.pdf", { type: "application/pdf" });
    const fileInput = document.querySelector('input[type="file"][accept*=".doc"]') as HTMLInputElement;
    fireEvent.change(fileInput, { target: { files: [file] } });

    const button = await screen.findByRole("button", { name: "上传文件并分析" });
    button.click();

    await waitFor(() => expect(uploadTenderClarificationMock).toHaveBeenCalledWith("proj-1", expect.objectContaining({
      title: "澄清/补遗文件",
      file,
      clarification_type: "addendum",
    })));
  });
});
