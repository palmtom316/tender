import { Card } from "../../../components/ui/Card";
import { Badge } from "../../../components/ui/Badge";
import { ClayButton } from "../../../components/ui/ClayButton";
import { Icon } from "../../../components/ui/Icon";
import type { Standard } from "../../../lib/api";
import { StandardProgressBar } from "./StandardProgressBar";

type StandardsTableCardProps = {
  standards: Standard[];
  loading: boolean;
  error: string;
  isDevMode: boolean;
  showDevArtifacts: boolean;
  hiddenDevArtifactCount: number;
  onToggleShowDevArtifacts: (nextValue: boolean) => void;
  onRetry: (standardId: string) => void;
  onDelete: (standardId: string) => void;
  onOpenViewer: (standardId: string) => void;
};

export function StandardsTableCard({
  standards,
  loading,
  error,
  isDevMode,
  showDevArtifacts,
  hiddenDevArtifactCount,
  onToggleShowDevArtifacts,
  onRetry,
  onDelete,
  onOpenViewer,
}: StandardsTableCardProps) {
  return (
    <Card className="standards-table-card">
      <div className="standards-table-card__header">
        <div>
          <h2>规范规程列表</h2>
          <p>统一管理整份规范的处理状态、重试、删除与查阅入口。</p>
        </div>
        {isDevMode && (
          <label className="standards-table-card__toggle">
            <input
              type="checkbox"
              checked={showDevArtifacts}
              onChange={(event) => onToggleShowDevArtifacts(event.target.checked)}
            />
            <span>
              显示测试残留
              {hiddenDevArtifactCount > 0 ? `（已隐藏 ${hiddenDevArtifactCount} 条）` : ""}
            </span>
          </label>
        )}
      </div>

      {error && <div className="warning-banner">{error}</div>}

      {loading ? (
        <div className="empty-state">
          <div className="spinner" />
        </div>
      ) : standards.length === 0 ? (
        <div className="empty-state">
          {isDevMode && hiddenDevArtifactCount > 0
            ? `当前仅剩 ${hiddenDevArtifactCount} 条测试残留，打开上方开关可查看。`
            : "暂无规范，请先批量上传规范 PDF 文件。"}
        </div>
      ) : (
        <div className="standards-table-card__table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>规范编号</th>
                <th>规范名称</th>
                <th>专业</th>
                <th>状态</th>
                <th>编辑</th>
                <th>查阅</th>
              </tr>
            </thead>
            <tbody>
              {standards.map((std) => (
                <tr key={std.id}>
                  <td>{std.standard_code}</td>
                  <td>
                    <div className="standards-table-card__name">
                      <span>{std.standard_name}</span>
                      {std.is_dev_artifact && <Badge variant="warning">测试残留</Badge>}
                    </div>
                    <div className="standards-table-card__meta">
                      {std.version_year ? `${std.version_year}版` : "版本未标注"}
                      <span>{std.clause_count} 条款</span>
                    </div>
                  </td>
                  <td>{std.specialty ?? "-"}</td>
                  <td>
                    <StandardProgressBar
                      processingStatus={std.processing_status}
                      ocrStatus={std.ocr_status}
                      aiStatus={std.ai_status}
                    />
                  </td>
                  <td>
                    <div className="standards-table-card__actions">
                      <ClayButton type="button" variant="ghost" size="sm" onClick={() => onDelete(std.id)}>
                        <Icon name="trash" size={14} /> 删除
                      </ClayButton>
                      {std.processing_status === "failed" && (
                        <ClayButton type="button" variant="ghost" size="sm" onClick={() => onRetry(std.id)}>
                          <Icon name="refresh" size={14} /> 重试
                        </ClayButton>
                      )}
                    </div>
                  </td>
                  <td>
                    <ClayButton type="button" variant="secondary" size="sm" onClick={() => onOpenViewer(std.id)}>
                      查阅
                    </ClayButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
