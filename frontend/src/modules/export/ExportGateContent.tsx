import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createDeliveryPackage, createExport, fetchExportGates } from "../../lib/api";
import type { ExportMode } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";

const EXPORT_MODE_OPTIONS: { value: ExportMode; label: string; description: string }[] = [
  {
    value: "single_docx",
    label: "单一 docx 文件",
    description: "全部章节合并为一个 .docx 文件输出",
  },
  {
    value: "multi_docx_zip",
    label: "分章节 docx 打包",
    description: "每个章节生成独立 .docx，再打包成 zip",
  },
  {
    value: "multi_doc_zip",
    label: "分章节 doc 打包",
    description: "每个章节转换为旧版 .doc 再打包成 zip（依赖 LibreOffice）",
  },
];

function GateIndicator({ passed, label, detail }: { passed: boolean; label: string; detail: string }) {
  return (
    <Card className="gate-card" style={{ borderColor: passed ? "var(--color-success)" : "var(--color-danger)" }}>
      <div className="gate-header">
        <span className="gate-icon">{passed ? "\u2705" : "\u274C"}</span>
        <strong>{label}</strong>
      </div>
      <p className="gate-detail">{detail}</p>
    </Card>
  );
}

export function ExportGateContent() {
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();
  const [exportMode, setExportMode] = useState<ExportMode>("single_docx");

  const { data: gatesData, isLoading } = useQuery({
    queryKey: ["export-gates", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchExportGates(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const exportDocx = useMutation({
    mutationFn: (mode: ExportMode) => {
      if (!projectId) throw new Error("No project selected");
      return createExport(projectId, mode);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["exports", projectId] });
    },
  });

  const delivery = useMutation({
    mutationFn: () => {
      if (!projectId) throw new Error("No project selected");
      return createDeliveryPackage(projectId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["delivery-packages", projectId] });
    },
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  const gates = gatesData?.gates;
  const currentMode = EXPORT_MODE_OPTIONS.find((option) => option.value === exportMode);
  const exportButtonLabel = (() => {
    if (!gatesData?.can_export) return "门禁未通过，无法导出";
    if (exportDocx.isPending) return "生成中...";
    switch (exportMode) {
      case "multi_docx_zip":
        return "生成分章节 docx 压缩包";
      case "multi_doc_zip":
        return "生成分章节 doc 压缩包";
      case "single_docx":
      default:
        return "生成单一 Word 文件";
    }
  })();

  return (
    <div>
      <h1 className="section-heading">导出门禁检查</h1>

      {isLoading && <div className="spinner" />}

      {gates && (
        <div className="gate-row">
          <GateIndicator
            passed={gates.veto_confirmed}
            label="否决项确认"
            detail={gates.veto_confirmed ? "全部已确认" : `${gates.unconfirmed_veto_count} 条未确认`}
          />
          <GateIndicator
            passed={gates.review_passed}
            label="审校通过"
            detail={gates.review_passed ? "无阻断问题" : `${gates.blocking_issue_count} 条 P0/P1 问题`}
          />
          <GateIndicator
            passed={gates.charts_approved}
            label="图表审批"
            detail={
              gates.charts_approved
                ? `${gates.referenced_chart_count} 个引用图表均已审批`
              : `${gates.unapproved_chart_count} 个引用图表未审批`
            }
          />
          <GateIndicator
            passed={gates.constraints_confirmed}
            label="约束确认"
            detail={
              gates.constraints_confirmed
                ? gates.legacy_pre_constraint_set
                  ? "旧项目兼容放行"
                  : "已确认约束集"
                : "请先确认约束集"
            }
          />
          <GateIndicator
            passed={gates.format_passed}
            label="格式校验"
            detail={
              gates.format_status === "warning_not_checked"
                ? gates.format_message || "格式校验未自动执行"
                : gates.format_passed
                  ? "格式合规"
                  : "格式不合规"
            }
          />
        </div>
      )}

      <fieldset
        className="export-mode-picker"
        style={{ margin: "var(--space-6) 0", border: "none", padding: 0 }}
      >
        <legend style={{ fontWeight: 600, marginBottom: "var(--space-3)" }}>输出模式</legend>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-2)" }}>
          {EXPORT_MODE_OPTIONS.map((option) => (
            <label
              key={option.value}
              style={{ display: "flex", alignItems: "flex-start", gap: "var(--space-3)", cursor: "pointer" }}
            >
              <input
                type="radio"
                name="export-mode"
                value={option.value}
                checked={exportMode === option.value}
                onChange={() => setExportMode(option.value)}
                disabled={exportDocx.isPending}
              />
              <span>
                <strong>{option.label}</strong>
                <span style={{ display: "block", color: "var(--color-text-muted)", fontSize: "0.85em" }}>
                  {option.description}
                </span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="export-actions">
        {gatesData && (
          <ClayButton
            size="lg"
            disabled={!gatesData.can_export || exportDocx.isPending}
            onClick={() => exportDocx.mutate(exportMode)}
          >
            {exportButtonLabel}
          </ClayButton>
        )}
        {gatesData?.can_export && (
          <ClayButton size="lg" onClick={() => delivery.mutate()} disabled={delivery.isPending}>
            {delivery.isPending ? "打包中..." : "生成最终交付包"}
          </ClayButton>
        )}
      </div>
      {exportDocx.isError && (
        <p className="error-message" role="alert">
          导出失败：{exportDocx.error instanceof Error ? exportDocx.error.message : String(exportDocx.error)}
        </p>
      )}
      {exportDocx.isSuccess && currentMode && (
        <p className="success-message">已生成 {currentMode.label} 输出。</p>
      )}
    </div>
  );
}
