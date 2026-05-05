import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import {
  type AiExtractionRunStatus,
  fetchAiExtractionBatches,
  fetchAiExtractionRun,
  retryFailedAiExtractionBatches,
} from "../../lib/api";

const STATUS_LABELS: Record<AiExtractionRunStatus, string> = {
  pending: "等待开始",
  running: "执行中",
  completed: "已完成",
  partial: "部分完成",
  failed: "失败",
  cancelled: "已取消",
};

const STATUS_VARIANTS: Record<AiExtractionRunStatus, "warning" | "info" | "success" | "danger" | "default"> = {
  pending: "warning",
  running: "info",
  completed: "success",
  partial: "warning",
  failed: "danger",
  cancelled: "default",
};

function isTerminal(status: AiExtractionRunStatus) {
  return status === "completed" || status === "failed" || status === "cancelled";
}

type AiExtractionRunPanelProps = {
  runId: string;
};

export function AiExtractionRunPanel({ runId }: AiExtractionRunPanelProps) {
  const queryClient = useQueryClient();

  const runQuery = useQuery({
    queryKey: ["ai-extraction-run", runId],
    queryFn: ({ signal }) => fetchAiExtractionRun(runId, { signal }),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isTerminal(status) ? false : 5000;
    },
  });

  const failedBatchesQuery = useQuery({
    queryKey: ["ai-extraction-batches", runId, "failed"],
    queryFn: ({ signal }) => fetchAiExtractionBatches(runId, "failed", { signal }),
    refetchInterval: 5000,
  });

  const retryMutation = useMutation({
    mutationFn: () => retryFailedAiExtractionBatches(runId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["ai-extraction-run", runId] });
      await queryClient.invalidateQueries({ queryKey: ["ai-extraction-batches", runId] });
    },
  });

  if (runQuery.isLoading) {
    return (
      <Card className="ai-extraction-panel ai-extraction-panel--loading" aria-busy="true">
        正在加载抽取任务...
      </Card>
    );
  }

  if (runQuery.isError || !runQuery.data) {
    return (
      <Card className="ai-extraction-panel ai-extraction-panel--error">
        <p>AI 抽取任务加载失败</p>
      </Card>
    );
  }

  const run = runQuery.data;
  const failedBatches = failedBatchesQuery.data ?? [];

  return (
    <Card className="ai-extraction-panel">
      <div className="ai-extraction-panel__header">
        <div>
          <span className="ai-extraction-panel__eyebrow">Extraction Run</span>
          <h2>AI 抽取任务进度</h2>
        </div>
        <Badge variant={STATUS_VARIANTS[run.status]}>{STATUS_LABELS[run.status]}</Badge>
      </div>

      <div className="ai-extraction-panel__metrics">
        <div>
          <span>总批次</span>
          <strong>{run.total_batches}</strong>
        </div>
        <div>
          <span>成功</span>
          <strong>{run.succeeded_batches}</strong>
        </div>
        <div>
          <span>失败</span>
          <strong>{run.failed_batches}</strong>
        </div>
        <div>
          <span>跳过</span>
          <strong>{run.skipped_batches}</strong>
        </div>
      </div>

      <div className="ai-extraction-panel__table-wrap">
        <table className="ai-extraction-panel__table">
          <caption>文件覆盖</caption>
          <thead>
            <tr>
              <th>文件</th>
              <th>Chunks</th>
              <th>批次</th>
              <th>成功</th>
              <th>失败</th>
              <th>需复核</th>
              <th>跳过</th>
              <th>抽取条数</th>
              <th>跳过原因</th>
            </tr>
          </thead>
          <tbody>
            {run.file_coverage.map((row) => (
              <tr key={row.source_file}>
                <td>{row.source_file}</td>
                <td>{row.chunks}</td>
                <td>{row.batches}</td>
                <td>{row.succeeded}</td>
                <td>{row.failed}</td>
                <td>{row.needs_review}</td>
                <td>{row.skipped}</td>
                <td>{row.extracted_requirements}</td>
                <td>{row.skip_reason ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {failedBatches.length > 0 && (
        <section className="ai-extraction-panel__failed">
          <div className="ai-extraction-panel__failed-header">
            <h3>失败批次</h3>
            <ClayButton
              size="sm"
              variant="outline"
              onClick={() => retryMutation.mutate()}
              disabled={retryMutation.isPending}
            >
              重试失败批次
            </ClayButton>
          </div>
          <ul className="ai-extraction-panel__failed-list">
            {failedBatches.map((batch) => (
              <li key={batch.id}>
                <strong>
                  {batch.source_file}#{batch.batch_index}
                </strong>
                <span>{batch.error_type ?? "UnknownError"}</span>
                <span>
                  · 重试 {batch.retry_count}/{batch.max_retries}
                </span>
                {batch.error_message && <p>{batch.error_message}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </Card>
  );
}
