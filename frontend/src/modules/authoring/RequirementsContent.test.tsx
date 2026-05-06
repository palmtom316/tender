import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { useNavigationMock, fetchRequirementsMock, fetchTenderSummaryMock, startRunMock } = vi.hoisted(() => ({
  useNavigationMock: vi.fn(),
  fetchRequirementsMock: vi.fn(),
  fetchTenderSummaryMock: vi.fn(),
  startRunMock: vi.fn(),
}));

vi.mock("../../lib/NavigationContext", () => ({
  useNavigation: useNavigationMock,
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchRequirements: fetchRequirementsMock,
    fetchTenderSummary: fetchTenderSummaryMock,
    startTenderAiExtractionRun: startRunMock,
    confirmRequirement: vi.fn(),
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

describe("RequirementsContent ai extraction", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("starts ai extraction and renders the run panel with returned run id", async () => {
    useNavigationMock.mockReturnValue({ projectId: "proj-1", documentId: "doc-1" });
    fetchRequirementsMock.mockResolvedValueOnce([]);
    fetchTenderSummaryMock.mockResolvedValueOnce({
      project_id: "proj-1",
      tender_document_id: "doc-1",
      project_name: "示例项目",
      tenderer: null,
      tender_agency: null,
      project_location: null,
      construction_period: null,
      quality_requirement: null,
      control_price: null,
      bid_bond: null,
      bid_open_time: null,
      bid_deadline: null,
      raw_facts_json: {},
      source_chunk_ids_json: [],
      extracted_model: null,
    });
    startRunMock.mockResolvedValueOnce({
      id: "run-123",
      tender_document_id: "doc-1",
      project_id: "proj-1",
      status: "pending",
      total_batches: 6,
      succeeded_batches: 0,
      failed_batches: 0,
      skipped_batches: 1,
      total_chunks: 120,
      covered_chunks: 0,
      extracted_requirements: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      file_coverage: [],
    });

    render(withClient(<RequirementsContent />));

    const button = await screen.findByRole("button", { name: "提交 AI 抽取任务" });
    button.click();

    await waitFor(() => expect(startRunMock).toHaveBeenCalledWith("doc-1"));
    expect(await screen.findByText("panel:run-123")).toBeInTheDocument();
    expect(localStorage.getItem("tender:ai-extraction-run:doc-1")).toBe("run-123");
  });

  it("restores the last tracked run id for the current document from localStorage", async () => {
    localStorage.setItem("tender:ai-extraction-run:doc-1", "run-restored");
    useNavigationMock.mockReturnValue({ projectId: "proj-1", documentId: "doc-1" });
    fetchRequirementsMock.mockResolvedValueOnce([]);
    fetchTenderSummaryMock.mockResolvedValueOnce({
      project_id: "proj-1",
      tender_document_id: "doc-1",
      project_name: "示例项目",
      tenderer: null,
      tender_agency: null,
      project_location: null,
      construction_period: null,
      quality_requirement: null,
      control_price: null,
      bid_bond: null,
      bid_open_time: null,
      bid_deadline: null,
      raw_facts_json: {},
      source_chunk_ids_json: [],
      extracted_model: null,
    });

    render(withClient(<RequirementsContent />));

    expect(await screen.findByText("panel:run-restored")).toBeInTheDocument();
  });
});
