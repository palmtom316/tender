import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

const { fetchRun, fetchBatches, retryFailed } = vi.hoisted(() => ({
  fetchRun: vi.fn(),
  fetchBatches: vi.fn(),
  retryFailed: vi.fn(),
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual("../../lib/api");
  return {
    ...actual,
    fetchAiExtractionRun: fetchRun,
    fetchAiExtractionBatches: fetchBatches,
    retryFailedAiExtractionBatches: retryFailed,
  };
});

import { AiExtractionRunPanel } from "./AiExtractionRunPanel";

function withClient(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{node}</QueryClientProvider>;
}

describe("AiExtractionRunPanel", () => {
  it("renders summary, file coverage and failed batches", async () => {
    fetchRun.mockResolvedValueOnce({
      id: "run-1",
      status: "partial",
      total_batches: 5,
      succeeded_batches: 3,
      failed_batches: 1,
      skipped_batches: 1,
      total_chunks: 200,
      covered_chunks: 150,
      extracted_requirements: 30,
      total_input_tokens: 1200,
      total_output_tokens: 340,
      file_coverage: [
        {
          source_file: "招标文件.docx",
          batches: 3,
          succeeded: 2,
          failed: 1,
          needs_review: 0,
          skipped: 0,
          chunks: 200,
          extracted_requirements: 30,
          skip_reason: null,
        },
      ],
    });
    fetchBatches.mockResolvedValueOnce([
      {
        id: "b1",
        source_file: "招标文件.docx",
        batch_index: 2,
        status: "failed",
        chunk_count: 40,
        model: "deepseek-v4-pro",
        reasoning_effort: "max",
        retry_count: 2,
        max_retries: 3,
        extracted_requirements: 0,
        dropped_invalid: 0,
        error_type: "ReadError",
        error_message: "upstream timeout",
        skip_reason: null,
      },
    ]);

    render(withClient(<AiExtractionRunPanel runId="run-1" />));

    expect(await screen.findByText("AI 抽取任务进度")).toBeInTheDocument();
    expect(screen.getByText("部分完成")).toBeInTheDocument();
    expect(screen.getByText("招标文件.docx")).toBeInTheDocument();
    expect(screen.getByText("ReadError")).toBeInTheDocument();
  });

  it("clicks retry button to call retryFailedAiExtractionBatches", async () => {
    fetchRun.mockResolvedValue({
      id: "run-1",
      status: "partial",
      total_batches: 1,
      succeeded_batches: 0,
      failed_batches: 1,
      skipped_batches: 0,
      total_chunks: 10,
      covered_chunks: 0,
      extracted_requirements: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      file_coverage: [],
    });
    fetchBatches.mockResolvedValue([]);
    retryFailed.mockResolvedValueOnce({
      id: "run-1",
      status: "running",
      total_batches: 1,
      succeeded_batches: 0,
      failed_batches: 0,
      skipped_batches: 0,
      total_chunks: 10,
      covered_chunks: 0,
      extracted_requirements: 0,
      total_input_tokens: 0,
      total_output_tokens: 0,
      file_coverage: [],
    });

    render(withClient(<AiExtractionRunPanel runId="run-1" />));
    const button = await screen.findByRole("button", { name: "重试失败批次" });
    button.click();

    await waitFor(() => expect(retryFailed).toHaveBeenCalledWith("run-1"));
  });
});
