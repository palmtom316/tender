import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
  updateBidChapterMock,
  fetchBusinessTemplatePreviewMock,
  fetchProjectTemplateInstanceMock,
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
  updateBidChapterMock: vi.fn(),
  fetchBusinessTemplatePreviewMock: vi.fn(),
  fetchProjectTemplateInstanceMock: vi.fn(),
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
    updateBidChapter: updateBidChapterMock,
    fetchBusinessTemplatePreview: fetchBusinessTemplatePreviewMock,
    fetchProjectTemplateInstance: fetchProjectTemplateInstanceMock,
  };

  it("blocks business generation when project template instance is not confirmed", async () => {
    fetchProjectTemplateInstanceMock.mockResolvedValueOnce({ id: "inst-1", project_id: "proj-1", display_name: "项目模板", status: "draft", unanswered_requirement_count: 3, pending_seal_checklist_count: 1, chapters: [] });
    render(withClient(<EditorContent />));

    expect(await screen.findByText("项目模板尚未确认，生成已阻断")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "资格商务装配" })).toBeDisabled();
  });

});

import { EditorContent } from "./EditorContent";

afterEach(() => {
  cleanup();
});

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
          metadata_json: { target_pages: 80 },
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
    fetchProjectTemplateInstanceMock.mockResolvedValue({ id: "inst-1", project_id: "proj-1", display_name: "项目模板", status: "ready_for_authoring", unanswered_requirement_count: 0, pending_seal_checklist_count: 0, chapters: [] });
    fetchTechnicalChapterContextMock.mockResolvedValue({
      constraints: [{ id: "constraint-1" }],
      scoring_items: [{ id: "score-1" }],
      standard_clauses: [{ id: "standard-1" }],
      personnel_selections: [{ id: "person-1" }],
      equipment_selections: [{ id: "equipment-1" }],
      chart_assets: [{ id: "asset-1" }],
      recommended_charts: ["quality_system", "response_matrix", "critical_path"],
      generation_controls: { target_pages: 80, target_pages_source: "user" },
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
    updateBidChapterMock.mockResolvedValue({ id: "chapter-1", metadata_json: { target_pages: 96 } });
    updateDraftMock.mockResolvedValue({});
    fetchBusinessTemplatePreviewMock.mockResolvedValue({ package_title: "国网配网工程商务标", chapters: [] });
  });

  it("generates a chart task draft and inserts the placeholder into the current draft", async () => {
    render(withClient(<EditorContent />));

    expect(await screen.findByText("招标冲突覆盖")).toBeInTheDocument();
    expect(screen.getByText("技术规范书 p12")).toBeInTheDocument();
    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);

    expect(await screen.findByText("章节写作要求")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText((_, element) => element?.textContent === "约束：1")).toBeInTheDocument());
    expect(screen.getByText((_, element) => element?.textContent === "评分：1")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "标准：1")).toBeInTheDocument();
    expect(screen.getByLabelText("10.1 目标页数")).toHaveValue(80);

    const taskRegion = await screen.findByLabelText("图表任务");
    expect(within(taskRegion).getByText("质量管理体系图")).toBeInTheDocument();
    expect(within(taskRegion).getByText("条款响应矩阵")).toBeInTheDocument();
    expect(within(taskRegion).getByText("关键路径图")).toBeInTheDocument();

    fireEvent.click(within(taskRegion).getAllByRole("button", { name: "生成图表草案" })[0]);

    await waitFor(() =>
      expect(generateChartAssetMock).toHaveBeenCalledWith("proj-1", expect.objectContaining({
        chart_type: "response_matrix",
        title: "条款响应矩阵",
        placeholder_key: "response_matrix",
        outline_node_id: "chapter-1",
      })),
    );

    fireEvent.click(within(taskRegion).getAllByRole("button", { name: "插入图表" })[0]);
    expect((screen.getByLabelText("10.1 章节正文") as HTMLTextAreaElement).value).toContain("{{chart:quality_system}}");
  });

  it("approves a generated chart asset", async () => {
    render(withClient(<EditorContent />));

    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);
    const taskRegion = await screen.findByLabelText("图表任务");
    fireEvent.click(within(taskRegion).getByRole("button", { name: "审批图表" }));

    await waitFor(() => expect(approveChartAssetMock).toHaveBeenCalledWith("asset-1"));
  });

  it("shows chart task options and generation summary", async () => {
    render(withClient(<EditorContent />));

    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);
    const taskRegion = await screen.findByLabelText("图表任务");
    await waitFor(() => expect(within(taskRegion).getByText("关键路径图")).toBeInTheDocument());
    fireEvent.click(within(taskRegion).getAllByRole("button", { name: "生成图表草案" })[1]);

    await waitFor(() =>
      expect(generateChartAssetMock).toHaveBeenCalledWith("proj-1", expect.objectContaining({
        chart_type: "critical_path",
        title: "关键路径图",
        placeholder_key: "critical_path",
      })),
    );
  });

  it("shows template stale warnings for drafts and chart assets", async () => {
    fetchProjectTemplateInstanceMock.mockResolvedValue({ id: "inst-1", project_id: "proj-1", display_name: "项目模板", status: "ready_for_authoring", unanswered_requirement_count: 0, pending_seal_checklist_count: 0, chapters: [] });
    fetchDraftsMock.mockResolvedValue([
      {
        id: "draft-1",
        chapter_code: "10.1",
        content_md: "正文",
        updated_at: "2026-05-14T00:00:00Z",
        is_stale: true,
        is_stale_by_template: true,
        stale_reason: "项目模板修订 7 更新了本章 AI 提示词",
      },
    ]);
    fetchBidOutlineMock.mockResolvedValue({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "技术标",
      status: "confirmed",
      chapters: [{ id: "chapter-1", chapter_code: "10.1", chapter_title: "质量保证措施", volume_type: "technical", sort_order: 1 }],
    });
    fetchTechnicalChapterContextMock.mockResolvedValue({
      recommended_charts: ["quality_system"],
      chart_assets: [{ id: "asset-1" }],
    });
    listChartAssetsMock.mockResolvedValue([
      {
        id: "asset-1",
        project_id: "proj-1",
        outline_node_id: null,
        chart_type: "quality_system",
        title: "质量管理体系图",
        spec_json: {},
        placeholder_key: "quality_system",
        rendered_svg: null,
        status: "stale_pending_regeneration",
        is_stale_by_template: true,
        metadata_json: {},
        created_at: "2026-05-14T00:00:00Z",
      },
    ]);

    render(withClient(<EditorContent />));

    fireEvent.click((await screen.findAllByText("10.1", { selector: ".outline-code" }))[1]);

    expect(await screen.findByText("模板已更新，需重新生成正文")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "按新模板重新生成正文" })).toBeInTheDocument();
    expect(await screen.findByText("模板已更新，需重新生成图表")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "按新模板重新生成图表" })).toBeInTheDocument();
  });

  it("saves target pages and passes them to technical generation", async () => {
    render(withClient(<EditorContent />));

    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);
    const targetInput = await screen.findByLabelText("10.1 目标页数");
    fireEvent.change(targetInput, { target: { value: "96" } });
    fireEvent.click(screen.getByRole("button", { name: "保存篇幅" }));

    await waitFor(() =>
      expect(updateBidChapterMock).toHaveBeenCalledWith("chapter-1", expect.objectContaining({
        metadata_json: expect.objectContaining({ target_pages: 96 }),
      })),
    );

    fireEvent.click(screen.getByRole("button", { name: "技术生成" }));

    await waitFor(() =>
      expect(generateTechnicalChapterMock).toHaveBeenCalledWith("proj-1", "chapter-1", expect.objectContaining({
        target_pages: 96,
      })),
    );
  });

  it("shows material composition language for non-technical chapters", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        {
          id: "chapter-business-1",
          project_id: "proj-1",
          outline_id: "outline-1",
          chapter_code: "3",
          chapter_title: "企业资信情况",
          volume_type: "business",
          sort_order: 1,
          metadata_json: {},
        },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      {
        id: "draft-business-1",
        project_id: "proj-1",
        chapter_code: "3",
        content_md: "## 企业资信情况\n我公司具备承担本项目的相关资质。",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [
        { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" },
      ],
      boundary: "商务资料装配完成，仍有缺失资料。",
    });

    render(withClient(<EditorContent />));

    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(assembleBusinessBidMock).toHaveBeenCalled());
    const chapterLabels = await screen.findAllByText("3");
    fireEvent.click(chapterLabels[1]);

    expect((await screen.findAllByText("资料编排")).length).toBeGreaterThan(0);
    expect(screen.getByText("资料位清单")).toBeInTheDocument();
    expect(screen.getByText("安全生产许可证")).toBeInTheDocument();
    expect(await screen.findByText("待补资料")).toBeInTheDocument();
  });

  it("shows business template chapter preview pages for business chapters", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        {
          id: "chapter-business-1",
          project_id: "proj-1",
          outline_id: "outline-1",
          chapter_code: "1",
          chapter_title: "商务偏差表",
          volume_type: "business",
          sort_order: 1,
          metadata_json: {},
        },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      {
        id: "draft-business-1",
        project_id: "proj-1",
        chapter_code: "1",
        content_md: "商务偏差表草稿",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [],
      boundary: "完成",
    });
    fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
      package_title: "国网配网工程商务标",
      chapters: [
        {
          chapter_code: "1",
          chapter_title: "商务偏差表",
          page_start: 1,
          page_end: 1,
          pages: [{ page_number: 1, blocks: ["商务偏差表", "序号 采购文件条目号"] }],
        },
      ],
    });

    render(withClient(<EditorContent />));
    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(assembleBusinessBidMock).toHaveBeenCalled());
    await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: "查看章节 1 商务偏差表" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "查看章节 1 商务偏差表" }));

    expect(await screen.findByText("模板页面预览")).toBeInTheDocument();
    expect(screen.getByText("第 1 页")).toBeInTheDocument();
    expect(screen.getByText("序号 采购文件条目号")).toBeInTheDocument();
  });

  it("switches preview pages and material checklist when selecting another business chapter", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        { id: "chapter-business-1", project_id: "proj-1", outline_id: "outline-1", chapter_code: "1", chapter_title: "商务偏差表", volume_type: "business", sort_order: 1, metadata_json: {} },
        { id: "chapter-business-2", project_id: "proj-1", outline_id: "outline-1", chapter_code: "2", chapter_title: "承诺函", volume_type: "business", sort_order: 2, metadata_json: {} },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      { id: "draft-business-1", project_id: "proj-1", chapter_code: "1", content_md: "商务偏差表草稿", updated_at: "2026-05-10T00:00:00Z" },
      { id: "draft-business-2", project_id: "proj-1", chapter_code: "2", content_md: "承诺函草稿", updated_at: "2026-05-10T00:00:00Z" },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [{ chapter_code: "2", material_name: "信用中国查询报告", material_type: "evidence_asset", reason: "缺资料" }],
      boundary: "完成",
    });
    fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
      package_title: "国网配网工程商务标",
      chapters: [
        { chapter_code: "1", chapter_title: "商务偏差表", page_start: 1, page_end: 1, pages: [{ page_number: 1, blocks: ["商务偏差表正文"] }] },
        { chapter_code: "2", chapter_title: "承诺函", page_start: 2, page_end: 3, pages: [{ page_number: 2, blocks: ["承诺函正文"] }] },
      ],
    });

    render(withClient(<EditorContent />));
    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole("button", { name: "查看章节 2 承诺函" }));

    expect(await screen.findByText("承诺函正文")).toBeInTheDocument();
    expect(screen.getByText("信用中国查询报告")).toBeInTheDocument();
  });

  it("uses a unified chapter directory instead of a separate business template list", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        { id: "chapter-business-1", project_id: "proj-1", outline_id: "outline-1", chapter_code: "1", chapter_title: "商务偏差表", volume_type: "business", sort_order: 1, metadata_json: {} },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      { id: "draft-business-1", project_id: "proj-1", chapter_code: "1", content_md: "商务偏差表草稿", updated_at: "2026-05-10T00:00:00Z" },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({ project_id: "proj-1", run: {}, chapters: [], response_matrix: [], missing_materials: [], boundary: "完成" });
    fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
      package_title: "国网配网工程商务标",
      chapters: [
        { chapter_code: "1", chapter_title: "商务偏差表", page_start: 1, page_end: 1, pages: [{ page_number: 1, blocks: ["商务偏差表"] }] },
      ],
    });

    render(withClient(<EditorContent />));
    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());

    expect(screen.queryByText("商务模板章节")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "查看章节 1 商务偏差表" })).toBeInTheDocument());
  });

  it("renders business preview as paper-like page cards", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        { id: "chapter-business-1", project_id: "proj-1", outline_id: "outline-1", chapter_code: "1", chapter_title: "商务偏差表", volume_type: "business", sort_order: 1, metadata_json: {} },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      { id: "draft-business-1", project_id: "proj-1", chapter_code: "1", content_md: "商务偏差表草稿", updated_at: "2026-05-10T00:00:00Z" },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({ project_id: "proj-1", run: {}, chapters: [], response_matrix: [], missing_materials: [], boundary: "完成" });
    fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
      package_title: "国网配网工程商务标",
      chapters: [
        { chapter_code: "1", chapter_title: "商务偏差表", page_start: 1, page_end: 2, pages: [{ page_number: 1, blocks: ["商务偏差表", "序号 采购文件条目号"] }] },
      ],
    });

    render(withClient(<EditorContent />));
    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole("button", { name: "查看章节 1 商务偏差表" }));

    const previewRegion = await screen.findByLabelText("模板页面预览");
    expect(within(previewRegion).getByText("第 1 页")).toBeInTheDocument();
    expect(within(previewRegion).getByText("商务偏差表")).toBeInTheDocument();
    expect(within(previewRegion).getByText("序号 采购文件条目号")).toBeInTheDocument();
  });

  it("highlights material placeholders inside business preview pages", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        { id: "chapter-business-1", project_id: "proj-1", outline_id: "outline-1", chapter_code: "3", chapter_title: "企业资信情况", volume_type: "business", sort_order: 1, metadata_json: {} },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      { id: "draft-business-1", project_id: "proj-1", chapter_code: "3", content_md: "企业资信情况草稿", updated_at: "2026-05-10T00:00:00Z" },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [{ chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" }],
      boundary: "完成",
    });
    fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
      package_title: "国网配网工程商务标",
      chapters: [
        { chapter_code: "3", chapter_title: "企业资信情况", page_start: 1, page_end: 1, pages: [{ page_number: 1, blocks: ["{{ asset.safety_license }}", "企业资信情况说明"] }] },
      ],
    });

    render(withClient(<EditorContent />));
    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole("button", { name: "查看章节 3 企业资信情况" }));

    expect(await screen.findByText("待插资料位")).toBeInTheDocument();
    expect(screen.getByText("asset.safety_license")).toBeInTheDocument();
  });

  it("shows bound material feedback inside the preview card after binding", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        { id: "chapter-business-1", project_id: "proj-1", outline_id: "outline-1", chapter_code: "3", chapter_title: "企业资信情况", volume_type: "business", sort_order: 1, metadata_json: {} },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      { id: "draft-business-1", project_id: "proj-1", chapter_code: "3", content_md: "企业资信情况草稿", updated_at: "2026-05-10T00:00:00Z" },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [{ chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" }],
      boundary: "完成",
    });
    fetchBusinessTemplatePreviewMock.mockResolvedValueOnce({
      package_title: "国网配网工程商务标",
      chapters: [
        { chapter_code: "3", chapter_title: "企业资信情况", page_start: 1, page_end: 1, pages: [{ page_number: 1, blocks: ["{{ asset.safety_license }}", "企业资信情况说明"] }] },
      ],
    });

    render(withClient(<EditorContent />));
    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(fetchBusinessTemplatePreviewMock).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole("button", { name: "查看章节 3 企业资信情况" }));
    fireEvent.click(await screen.findByRole("button", { name: "选择资料位 安全生产许可证" }));
    fireEvent.click((await screen.findAllByRole("button", { name: /绑定到当前资料位/i }))[0]);

    expect(await screen.findByText(/已绑定资料：安全生产许可证（公司基础资料）/)).toBeInTheDocument();
  });

  it("shows candidate material groups for a selected business material slot", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        {
          id: "chapter-business-1",
          project_id: "proj-1",
          outline_id: "outline-1",
          chapter_code: "3",
          chapter_title: "企业资信情况",
          volume_type: "business",
          sort_order: 1,
          metadata_json: {},
        },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      {
        id: "draft-business-1",
        project_id: "proj-1",
        chapter_code: "3",
        content_md: "## 企业资信情况\n我公司具备承担本项目的相关资质。",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [
        { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" },
      ],
      boundary: "商务资料装配完成，仍有缺失资料。",
    });

    render(withClient(<EditorContent />));

    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(assembleBusinessBidMock).toHaveBeenCalled());
    fireEvent.click((await screen.findAllByText("3"))[1]);
    fireEvent.click(await screen.findByRole("button", { name: "选择资料位 安全生产许可证" }));

    expect(await screen.findByText("当前资料位：安全生产许可证")).toBeInTheDocument();
    expect(screen.getByText("资料候选区")).toBeInTheDocument();
    expect(screen.getByText("公司资料候选")).toBeInTheDocument();
    expect(screen.getByText("证照/附件候选")).toBeInTheDocument();
  });

  it("binds a candidate material to the selected slot in the business workbench", async () => {
    fetchBidOutlineMock.mockResolvedValueOnce({
      id: "outline-1",
      project_id: "proj-1",
      outline_name: "默认目录",
      status: "confirmed",
      chapters: [
        {
          id: "chapter-business-1",
          project_id: "proj-1",
          outline_id: "outline-1",
          chapter_code: "3",
          chapter_title: "企业资信情况",
          volume_type: "business",
          sort_order: 1,
          metadata_json: {},
        },
      ],
    });
    fetchDraftsMock.mockResolvedValueOnce([
      {
        id: "draft-business-1",
        project_id: "proj-1",
        chapter_code: "3",
        content_md: "## 企业资信情况\n我公司具备承担本项目的相关资质。",
        updated_at: "2026-05-10T00:00:00Z",
      },
    ]);
    assembleBusinessBidMock.mockResolvedValueOnce({
      project_id: "proj-1",
      run: {},
      chapters: [],
      response_matrix: [],
      missing_materials: [
        { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" },
      ],
      boundary: "商务资料装配完成，仍有缺失资料。",
    });

    render(withClient(<EditorContent />));

    const assembleButton = await screen.findByRole("button", { name: "资格商务装配" });
    await waitFor(() => expect(assembleButton).not.toBeDisabled());
    fireEvent.click(assembleButton);
    await waitFor(() => expect(assembleBusinessBidMock).toHaveBeenCalled());
    fireEvent.click((await screen.findAllByText("3"))[1]);
    fireEvent.click(await screen.findByRole("button", { name: "选择资料位 安全生产许可证" }));
    fireEvent.click((await screen.findAllByRole("button", { name: /绑定到当前资料位/i }))[0]);

    expect(await screen.findByText(/已绑定资料：/)).toBeInTheDocument();
    expect(screen.getByText("已匹配")).toBeInTheDocument();
  });

  it("keeps technical chapters on AI content flow without business candidate panel", async () => {
    render(withClient(<EditorContent />));
    fireEvent.click((await screen.findAllByText("10.1"))[1]);

    expect(await screen.findByLabelText("图表任务")).toBeInTheDocument();
    expect(screen.queryByLabelText("资料候选区")).not.toBeInTheDocument();
  });

  it("shows chart task cards with purpose, source, approval and insert actions", async () => {
    render(withClient(<EditorContent />));

    const chapterLabels = await screen.findAllByText("10.1");
    fireEvent.click(chapterLabels[1]);

    const taskRegion = await screen.findByLabelText("图表任务");
    expect(within(taskRegion).getByText("质量管理体系图")).toBeInTheDocument();
    expect(within(taskRegion).getByText("响应质量保证体系要求，展示质量管理职责链路。")).toBeInTheDocument();
    expect(within(taskRegion).getByText("{{chart:quality_system}}")).toBeInTheDocument();
    expect(within(taskRegion).getByRole("button", { name: "审批图表" })).toBeInTheDocument();
    expect(within(taskRegion).getByRole("button", { name: "插入图表" })).toBeInTheDocument();
  });

});
