import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const {
  useNavigationMock,
  listTenderDocumentsMock,
  uploadTenderDocumentMock,
  parseTenderDocumentMock,
  fetchTenderDocumentParseStatusMock,
} = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  listTenderDocumentsMock: vi.fn(),
  uploadTenderDocumentMock: vi.fn(),
  parseTenderDocumentMock: vi.fn(),
  fetchTenderDocumentParseStatusMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    listTenderDocuments: listTenderDocumentsMock,
    uploadTenderDocument: uploadTenderDocumentMock,
    parseTenderDocument: parseTenderDocumentMock,
    fetchTenderDocumentParseStatus: fetchTenderDocumentParseStatusMock,
  };
});

import { UploadContent } from "./UploadContent";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("UploadContent tender document flow", () => {
  it("uploads a tender package, selects the document, and starts parsing", async () => {
    const setDocumentId = vi.fn();
    useNavigationMock.mockReturnValue({
      projectId: "proj-1",
      documentId: null,
      setDocumentId,
    });
    listTenderDocumentsMock.mockResolvedValueOnce([]);
    uploadTenderDocumentMock.mockResolvedValueOnce({
      id: "doc-1",
      project_id: "proj-1",
      original_filename: "招标文件包.zip",
      upload_type: "zip",
      status: "completed",
      content_type: "application/zip",
      size_bytes: 1024,
      storage_key: "/tmp/doc-1.zip",
      file_sha256: "abc",
      error: null,
      file_count: 3,
      files: [],
    });
    parseTenderDocumentMock.mockResolvedValueOnce({
      tender_document_id: "doc-1",
      parsed_file_count: 1,
      failed_file_count: 0,
      skipped_file_count: 2,
      chunk_count: 8,
      files: [],
    });
    fetchTenderDocumentParseStatusMock.mockResolvedValue({
      tender_document_id: "doc-1",
      document_status: "completed",
      total_file_count: 3,
      pending_file_count: 0,
      parsing_file_count: 0,
      completed_file_count: 1,
      failed_file_count: 0,
      skipped_file_count: 2,
      chunk_count: 8,
      files: [],
    });

    render(withClient(<UploadContent />));

    const input = screen.getByLabelText("上传招标文件");
    const file = new File(["zip-content"], "招标文件包.zip", { type: "application/zip" });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(uploadTenderDocumentMock).toHaveBeenCalledWith("proj-1", file));
    await waitFor(() => expect(setDocumentId).toHaveBeenCalledWith("doc-1"));
    await waitFor(() => expect(parseTenderDocumentMock).toHaveBeenCalledWith("doc-1"));
  });
});
