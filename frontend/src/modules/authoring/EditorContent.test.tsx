import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const {
  useNavigationMock,
  fetchDraftsMock,
  fetchTechnicalChapterContextMock,
  updateDraftMock,
  fetchBidOutlineMock,
  previewBidOutlineReconciliationMock,
  fetchTechnicalWritingPlanMock,
  listChartAssetsMock,
  generateChartAssetMock,
  approveChartAssetMock,
  generateBidOutlineMock,
  confirmBidOutlineMock,
  assembleBusinessBidMock,
  generateBidChapterMock,
  generateTechnicalChapterMock,
} = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  fetchDraftsMock: vi.fn(),
  fetchTechnicalChapterContextMock: vi.fn(),
  updateDraftMock: vi.fn(),
  fetchBidOutlineMock: vi.fn(),
  previewBidOutlineReconciliationMock: vi.fn(),
  fetchTechnicalWritingPlanMock: vi.fn(),
  listChartAssetsMock: vi.fn(),
  generateChartAssetMock: vi.fn(),
  approveChartAssetMock: vi.fn(),
  generateBidOutlineMock: vi.fn(),
  confirmBidOutlineMock: vi.fn(),
  assembleBusinessBidMock: vi.fn(),
  generateBidChapterMock: vi.fn(),
  generateTechnicalChapterMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchDrafts: fetchDraftsMock,
    fetchTechnicalChapterContext: fetchTechnicalChapterContextMock,
    updateDraft: updateDraftMock,
    fetchBidOutline: fetchBidOutlineMock,
    previewBidOutlineReconciliation: previewBidOutlineReconciliationMock,
    fetchTechnicalWritingPlan: fetchTechnicalWritingPlanMock,
    listChartAssets: listChartAssetsMock,
    generateChartAsset: generateChartAssetMock,
    approveChartAsset: approveChartAssetMock,
    generateBidOutline: generateBidOutlineMock,
    confirmBidOutline: confirmBidOutlineMock,
    assembleBusinessBid: assembleBusinessBidMock,
    generateBidChapter: generateBidChapterMock,
    generateTechnicalChapter: generateTechnicalChapterMock,
  };
});

import { EditorContent } from "./EditorContent";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("EditorContent chart workflow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNavigationMock.mockReturnValue({ projectId: "proj-1" });
    fetchDraftsMock.mockResolvedValue([
      {
        id: "draft-1",
        project_id: "proj-1",
        chapter_code: "10.1",
        content_md: "## 质量保证措施\n正文",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ]);
    fetchBidOutlineMock.mockResolvedValue({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        {
          id: "chapter-1",
          project_id: "proj-1",
          outline_id: "outline-1",
          chapter_code: "10.1",
          chapter_title: "质量保证措施",
          volume_type: "technical",
          sort_order: 1,
        },
      ],
    });
    previewBidOutlineReconciliationMock.mockResolvedValue({
      project_id: "proj-1",
      outline: {},
      diffs: [
        {
          chapter_id: "chapter-1",
          chapter_code: "13",
          chapter_title: "技术规范书规定的其他应提交的文件",
          volume_type: "technical",
          operation: "tender_conflict_override",
          requirement_count: 1,
          reason: "招标文件要求技术规范响应文件单独成册",
          source_locator: "技术规范书 p12",
          proposed_action: "separate_volume",
        },
      ],
      unresolved_critical_count: 0,
      can_confirm: true,
      blocking_requirements: [],
    });
    fetchTechnicalWritingPlanMock.mockResolvedValue({ project_id: "proj-1", outline_id: "outline-1", chapter_count: 1, chapters: [] });
    fetchTechnicalChapterContextMock.mockResolvedValue({
      constraints: [{ id: "constraint-1" }],
      scoring_items: [{ id: "score-1" }],
      standard_clauses: [{ id: "standard-1" }],
      personnel_selections: [{ id: "person-1" }],
      equipment_selections: [{ id: "equipment-1" }],
      chart_assets: [{ id: "asset-1" }],
      company_assets: { performances: [{ id: "perf-1" }], certificates: [{ id: "cert-1" }] },
    });
    listChartAssetsMock.mockResolvedValue([
      {
        id: "asset-1",
        project_id: "proj-1",
        outline_node_id: "chapter-1",
        chart_type: "quality_system",
        title: "质量管理体系图",
        spec_json: {},
        rendered_svg: "<svg xmlns=\"http://www.w3.org/2000/svg\"/>",
        placeholder_key: "quality_system",
        status: "draft",
        created_at: "2026-05-10T00:00:00Z",
      },
    ]);
    generateChartAssetMock.mockResolvedValue({
      id: "asset-2",
      chart_type: "risk_matrix",
      title: "风险分级管控矩阵",
      placeholder_key: "risk_matrix",
      status: "draft",
    });
    approveChartAssetMock.mockResolvedValue({ id: "asset-1", status: "approved" });
    updateDraftMock.mockResolvedValue({});
  });

  it("generates a selected chart type and inserts the placeholder into the current draft", async () => {
    render(withClient(<EditorContent />));

    expect(await screen.findByText("招标冲突覆盖")).toBeInTheDocument();
    expect(screen.getByText("技术规范书 p12")).toBeInTheDocument();
    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);
    expect(await screen.findByText("章节生成上下文")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText((_, element) => element?.textContent === "约束：1")).toBeInTheDocument());
    expect(screen.getByText((_, element) => element?.textContent === "评分：1")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "标准：1")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "业绩：1")).toBeInTheDocument();
    fireEvent.change(await screen.findByLabelText("图表类型"), { target: { value: "risk_matrix" } });
    fireEvent.click(screen.getByRole("button", { name: "生成图表草案" }));

    await waitFor(() =>
      expect(generateChartAssetMock).toHaveBeenCalledWith("proj-1", expect.objectContaining({
        chart_type: "risk_matrix",
        title: "风险分级管控矩阵",
        placeholder_key: "risk_matrix",
        outline_node_id: "chapter-1",
      })),
    );

    fireEvent.click(await screen.findByRole("button", { name: "插入 quality_system" }));
    expect((screen.getByLabelText("10.1 章节正文") as HTMLTextAreaElement).value).toContain("{{chart:quality_system}}");
  });

  it("approves a generated chart asset", async () => {
    render(withClient(<EditorContent />));

    fireEvent.click(await screen.findByRole("button", { name: "审批图表" }));

    await waitFor(() => expect(approveChartAssetMock).toHaveBeenCalledWith("asset-1"));
  });
});
