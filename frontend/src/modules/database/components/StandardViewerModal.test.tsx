import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { StandardParseAssets, StandardViewerData } from "../../../lib/api";
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
    expect(screen.getByText(/HTML 预览：.*C30/)).toBeInTheDocument();
    expect(screen.queryByText("钢筋保护层厚度")).not.toBeInTheDocument();
    expect(screen.getAllByText("查看原始解析数据")).toHaveLength(2);
    expect(screen.getByText(/section-hit-raw/)).not.toBeVisible();
    expect(screen.getByText(/table-hit-raw/)).not.toBeVisible();
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
        initialClauseId="commentary-1"
        onClose={() => undefined}
      />,
    );

    const pdfPanes = await screen.findAllByTestId("pdf-pane");
    expect(pdfPanes[pdfPanes.length - 1]).toHaveTextContent("PDF page 10");
  });
});
