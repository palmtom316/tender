import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { useNavigationMock, fetchExportGatesMock, createExportMock, createDeliveryPackageMock } = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  fetchExportGatesMock: vi.fn(),
  createExportMock: vi.fn(),
  createDeliveryPackageMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchExportGates: fetchExportGatesMock,
    createExport: createExportMock,
    createDeliveryPackage: createDeliveryPackageMock,
  };
});

import { ExportGateContent } from "./ExportGateContent";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("ExportGateContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useNavigationMock.mockReturnValue({ projectId: "proj-1" });
    fetchExportGatesMock.mockResolvedValue({
      can_export: false,
      gates: {
        veto_confirmed: true,
        unconfirmed_veto_count: 0,
        review_passed: false,
        blocking_issue_count: 2,
        charts_approved: false,
        unapproved_chart_count: 1,
        referenced_chart_count: 3,
        constraints_confirmed: true,
        legacy_pre_constraint_set: false,
        critical_constraints_resolved: false,
        unresolved_critical_constraint_count: 1,
        template_required_items_rendered: false,
        required_template_failed_count: 2,
        failed_required_template_items: ["授权委托书", "技术规范响应表"],
        stale_artifacts_clear: false,
        stale_artifact_count: 4,
        template_stale_artifacts_clear: false,
        stale_template_artifact_count: 2,
        format_passed: false,
        format_status: "warning_not_checked",
        format_message: "尚未执行自动格式校验",
        page_count_passed: false,
        page_count_status: "failed_estimate_below_minimum",
        page_count_evidence: [{ target_pages: 100, minimum_required_pages: 90, estimated_pages: 88, actual_pages: null }],
        coverage_passed: false,
        coverage_issue_count: 1,
        coverage_issues: [{ code: "missing_section", section_code: "8.2", severity: "P0" }],
        chart_closure_passed: false,
        chart_closure_issue_count: 1,
        chart_closure_issues: [{ code: "chart_not_inserted", chart_key: "risk_matrix", severity: "P0" }],
        ad_hoc_task_cards_ready: false,
        ad_hoc_task_card_issue_count: 1,
        ad_hoc_task_card_issues: [{ chapter_code: "99", chapter_title: "新增专项方案", message: "新增章节任务卡未完成", hint: "请先补充信息、确认大纲并生成正文。" }],
      },
    });
  });

  it("shows constraint, template render, stale artifact, chart, and format gates", async () => {
    render(withClient(<ExportGateContent />));

    expect(await screen.findByText("关键约束闭环")).toBeInTheDocument();
    expect(screen.getByText("1 项关键约束仍未处理")).toBeInTheDocument();
    expect(screen.getByText("模板渲染完整性")).toBeInTheDocument();
    expect(screen.getByText("2 个必需模板项渲染失败：授权委托书、技术规范响应表")).toBeInTheDocument();
    expect(screen.getByText("内容时效")).toBeInTheDocument();
    expect(screen.getByText("4 项草稿、目录或图表已过期")).toBeInTheDocument();
    expect(screen.getByText("模板修改后未重新生成")).toBeInTheDocument();
    expect(screen.getByText("2 项正文或图表需按新模板重新生成")).toBeInTheDocument();
    expect(screen.getByText("图表审批")).toBeInTheDocument();
    expect(screen.getByText("1 个引用图表未审批")).toBeInTheDocument();
    expect(screen.getByText("尚未执行自动格式校验")).toBeInTheDocument();
    expect(screen.getByText("页数硬闸门")).toBeInTheDocument();
    expect(screen.getByText(/目标 100 页/)).toBeInTheDocument();
    expect(screen.getByText("内容覆盖完整性")).toBeInTheDocument();
    expect(screen.getByText(/1 个覆盖缺口/)).toBeInTheDocument();
    expect(screen.getByText("图表闭环")).toBeInTheDocument();
    expect(screen.getByText(/risk_matrix/)).toBeInTheDocument();
    expect(screen.getByText("新增章节任务卡")).toBeInTheDocument();
    expect(screen.getByText(/请先补充信息、确认大纲并生成正文/)).toBeInTheDocument();
    expect(screen.queryByText(/outline_ready|needs_input|task_card_pending|blocked_insufficient_evidence/)).not.toBeInTheDocument();
  });
});
