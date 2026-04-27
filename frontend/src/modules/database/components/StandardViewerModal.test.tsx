import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StandardParseAssets, StandardQualityReport, StandardViewerData } from "../../../lib/api";
import { StandardViewerModal } from "./StandardViewerModal";

vi.mock("./StandardPdfPane", () => ({
  StandardPdfPane: ({ targetPage }: { targetPage: number | null }) => (
    <div data-testid="pdf-pane">PDF page {targetPage ?? "n/a"}</div>
  ),
}));

const viewerData: StandardViewerData = {
  id: "std-1",
  standard_code: "GB 50010-2010",
  standard_name: "混凝土结构设计规范",
  version_year: "2010",
  specialty: "结构",
  status: null,
  processing_status: "completed",
  ocr_status: "completed",
  ai_status: "completed",
  error_message: null,
  queue_position: null,
  clause_count: 1,
  is_dev_artifact: false,
  created_at: "2026-03-21T08:00:00Z",
  processing_started_at: "2026-03-21T08:00:00Z",
  processing_finished_at: "2026-03-21T08:05:00Z",
  document_id: "doc-1",
  pdf_url: "/api/files/std-1.pdf",
  clause_tree: [
    {
      id: "clause-1",
      clause_no: "4.2.3",
      node_type: "clause",
      node_key: null,
      node_label: null,
      clause_title: "混凝土强度等级",
      clause_text: "混凝土强度等级不得低于 C30。",
      summary: "约束最低强度等级",
      tags: ["结构"],
      clause_type: "normative",
      source_type: "table",
      source_label: "表格: 混凝土强度等级",
      page_start: 10,
      page_end: 10,
      sort_order: 1,
      parent_id: null,
      children: [],
    },
  ],
};

const parseAssets: StandardParseAssets = {
  standard_id: "std-1",
  document: {
    id: "doc-1",
    parser_name: "MinerU",
    parser_version: "2.0",
    raw_payload: { pages: 200 },
  },
  sections: [
    {
      id: "section-noise",
      section_code: "4.2.2",
      title: "钢筋保护层",
      level: 2,
      text: "钢筋最小保护层厚度应符合要求。",
      text_source: "mineru_markdown",
      sort_order: 1,
      page_start: 10,
      page_end: 10,
      raw_json: { type: "section", title: "钢筋保护层", debug_token: "section-noise-raw" },
    },
    {
      id: "section-hit",
      section_code: "4.2.3",
      title: "混凝土强度等级",
      level: 2,
      text: "混凝土强度等级不得低于 C30，且环境类别应满足耐久性要求。",
      text_source: "mineru_markdown",
      sort_order: 2,
      page_start: 10,
      page_end: 10,
      raw_json: { type: "section", title: "混凝土强度等级", debug_token: "section-hit-raw" },
    },
  ],
  tables: [
    {
      id: "table-noise",
      section_id: null,
      page: 10,
      page_start: 10,
      page_end: 10,
      table_title: "钢筋保护层厚度",
      table_html: "<table><tr><td>25</td></tr></table>",
      raw_json: { cells: [["25"]], debug_token: "table-noise-raw" },
    },
    {
      id: "table-hit",
      section_id: null,
      page: 10,
      page_start: 10,
      page_end: 10,
      table_title: "混凝土强度等级",
      table_html: "<table><tr><td>C30</td></tr></table>",
      raw_json: { cells: [["C30"]], debug_token: "table-hit-raw" },
    },
  ],
};

const qualityReport: StandardQualityReport = {
  overview: {
    status: "review",
    summary: "当前解析质量可继续抽查，但仍有风险信号需要复核。",
  },
  metrics: {
    page_count: 12,
    raw_section_count: 16,
    normalized_section_count: 12,
    table_count: 2,
    clause_count: 1,
    commentary_clause_count: 0,
    table_clause_count: 1,
    anchored_section_count: 10,
    anchored_clause_count: 1,
    section_anchor_coverage: 0.833,
    clause_anchor_coverage: 1,
    backfilled_anchor_count: 1,
    dropped_noise_count: 4,
    validation_issue_count: 2,
    validation_phrase_flag_count: 3,
    validation_severity_counts: { warning: 2 },
    validation_issue_code_counts: { "page.missing_anchor": 1, "numbering.gap": 1 },
    toc_noise_count: 2,
    front_matter_noise_count: 1,
    suspicious_year_code_count: 0,
    unanchored_heading_noise_count: 1,
    terminal_heading_noise_count: 0,
  },
  gates: [
    { code: "section_anchor_coverage", status: "warn", message: "清洗后段落锚点覆盖率为 83.3%。" },
    { code: "structured_validation", status: "warn", message: "结构化校验发现 2 个问题，建议抽样复核。" },
  ],
  warnings: [],
  top_issues: [
    {
      code: "page.missing_anchor",
      severity: "warning",
      message: "Clause 4.2.4: missing page anchors",
      clause_no: "4.2.4",
      page_start: null,
      page_end: null,
    },
  ],
  recommended_skills: [
    {
      skill_name: "standard-parse-recovery",
      description: "解析恢复工具",
      tool_names: [],
      active: true,
      reason: "结构化校验仍有问题，建议用恢复技能排查编号断裂、页码锚点和条款补丁。",
      trigger_codes: ["structured_validation"],
    },
  ],
};

describe("StandardViewerModal diagnostics", () => {
  it("prioritizes the most relevant raw section and table for the selected clause", async () => {
    render(
      <StandardViewerModal
        open
        mode="search-hit"
        viewerData={viewerData}
        parseAssets={parseAssets}
        parseAssetsLoading={false}
        parseAssetsError=""
        qualityReport={qualityReport}
        initialClauseId="clause-1"
        onClose={() => undefined}
      />,
    );

    expect(screen.getByText("PDF 组件加载中...")).toBeInTheDocument();
    expect(await screen.findByTestId("pdf-pane")).toBeInTheDocument();
    expect(screen.getByText("解析诊断")).toBeInTheDocument();
    expect(screen.getByText("MinerU 2.0")).toBeInTheDocument();
    expect(screen.getByText("4.2.3 混凝土强度等级")).toBeInTheDocument();
    expect(screen.queryByText("4.2.2 钢筋保护层")).not.toBeInTheDocument();
    expect(screen.getByText("text_source: mineru_markdown · sort_order: 2")).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("C30")).toBeInTheDocument();
    expect(screen.queryByText(/HTML 预览/u)).not.toBeInTheDocument();
    expect(screen.queryByText("钢筋保护层厚度")).not.toBeInTheDocument();
    expect(screen.getAllByText("查看原始解析数据")).toHaveLength(2);
    expect(screen.getByText(/section-hit-raw/)).not.toBeVisible();
    expect(screen.getByText(/table-hit-raw/)).not.toBeVisible();
    expect(screen.getByText("入库质量")).toBeInTheDocument();
    expect(screen.getByText("需复核")).toBeInTheDocument();
    expect(screen.getByText("standard-parse-recovery")).toBeInTheDocument();
  });

  it("falls back to the parent clause page when a commentary node carries polluted appendix metadata", async () => {
    const commentaryViewerData: StandardViewerData = {
      ...viewerData,
      clause_tree: [
        {
          ...viewerData.clause_tree[0],
          children: [
            {
              id: "commentary-1",
              clause_no: "4.2.3",
              node_type: "commentary",
              node_key: "4.2.3#commentary",
              node_label: null,
              clause_title: null,
              clause_text: "条文说明正文",
              summary: "说明摘要",
              tags: ["说明"],
              clause_type: "commentary",
              source_type: "text",
              source_label: "2 术语 (1/5)",
              page_start: 39,
              page_end: 63,
              sort_order: 99,
              parent_id: null,
              children: [],
            },
          ],
        },
      ],
    };

    render(
      <StandardViewerModal
        open
        mode="browse"
        viewerData={commentaryViewerData}
        parseAssets={parseAssets}
        parseAssetsLoading={false}
        parseAssetsError=""
        qualityReport={qualityReport}
        initialClauseId="commentary-1"
        onClose={() => undefined}
      />,
    );

    const pdfPanes = await screen.findAllByTestId("pdf-pane");
    expect(pdfPanes[pdfPanes.length - 1]).toHaveTextContent("PDF page 10");
  });
});
