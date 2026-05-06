import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const {
  useNavigationMock,
  fetchTenderDocumentParseStatusMock,
  fetchTenderSourceChunksMock,
} = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  fetchTenderDocumentParseStatusMock: vi.fn(),
  fetchTenderSourceChunksMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchTenderDocumentParseStatus: fetchTenderDocumentParseStatusMock,
    fetchTenderSourceChunks: fetchTenderSourceChunksMock,
  };
});

import { ParseContent } from "./ParseContent";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("ParseContent tender document flow", () => {
  it("renders parse summary and source chunks from the tender-document APIs", async () => {
    useNavigationMock.mockReturnValue({ projectId: "proj-1", documentId: "doc-1" });
    fetchTenderDocumentParseStatusMock.mockResolvedValueOnce({
      tender_document_id: "doc-1",
      document_status: "completed",
      total_file_count: 2,
      pending_file_count: 0,
      parsing_file_count: 0,
      completed_file_count: 2,
      failed_file_count: 0,
      skipped_file_count: 0,
      chunk_count: 2,
      files: [],
    });
    fetchTenderSourceChunksMock.mockResolvedValueOnce([
      {
        id: "chunk-1",
        tender_document_id: "doc-1",
        tender_document_file_id: "file-1",
        chunk_type: "heading",
        source_file: "招标文件.docx",
        document_type: "tender_document",
        section_title: "第一章 招标公告",
        source_locator: "paragraph:1",
        title: "第一章 招标公告",
        text: "第一章 招标公告",
        table_json: null,
        page_start: null,
        page_end: null,
        sheet_name: null,
        row_start: null,
        row_end: null,
        paragraph_index: 1,
        sort_order: 0,
        confidence: 0.9,
      },
      {
        id: "chunk-1-1",
        tender_document_id: "doc-1",
        tender_document_file_id: "file-1",
        chunk_type: "paragraph",
        source_file: "招标文件.docx",
        document_type: "tender_document",
        section_title: "第一章 招标公告",
        source_locator: "paragraph:2",
        title: null,
        text: "本项目采用资格后审，投标人应按要求提交完整材料。",
        table_json: null,
        page_start: 1,
        page_end: 1,
        sheet_name: null,
        row_start: null,
        row_end: null,
        paragraph_index: 2,
        sort_order: 1,
        confidence: 0.9,
      },
      {
        id: "chunk-2",
        tender_document_id: "doc-1",
        tender_document_file_id: "file-1",
        chunk_type: "table",
        source_file: "招标文件.docx",
        document_type: "tender_document",
        section_title: "评标办法",
        source_locator: "table:1",
        title: "评标办法",
        text: "评分表",
        table_json: { rows: [["项目", "分值"]] },
        page_start: null,
        page_end: null,
        sheet_name: null,
        row_start: null,
        row_end: null,
        paragraph_index: null,
        sort_order: 1,
        confidence: 0.9,
      },
    ]);

    render(withClient(<ParseContent />));

    expect(await screen.findByText("已解析文件")).toBeInTheDocument();
    expect(screen.getAllByText("2")).toHaveLength(2);
    expect(screen.getByText("第一章 招标公告")).toBeInTheDocument();
    expect(screen.getByText("本项目采用资格后审，投标人应按要求提交完整材料。")).toBeInTheDocument();
    expect(screen.getByText("评标办法")).toBeInTheDocument();
  });
});
