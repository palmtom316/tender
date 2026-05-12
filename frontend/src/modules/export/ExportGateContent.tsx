import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createDeliveryPackage, createExport, fetchExportGates } from "../../lib/api";
import type { ExportMode } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Icon } from "../../components/ui/Icon";
import { EmptyState } from "../../components/ui/EmptyState";

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
    <Card className={`gate-card ${passed ? "gate-card--passed" : "gate-card--blocked"}`}>
      <div className="gate-header">
        <span className="gate-icon">
          <Icon name={passed ? "check-circle" : "x-circle"} size={15} />
        </span>
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
    return <EmptyState icon="项" title="请先选择投标项目" description="选择项目后，可查看审校、合规或导出状态。" />;
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
            passed={gates.critical_constraints_resolved}
            label="关键约束闭环"
            detail={
              gates.critical_constraints_resolved
                ? "关键约束均已处理"
                : `${gates.unresolved_critical_constraint_count} 项关键约束仍未处理`
            }
          />
          <GateIndicator
            passed={gates.template_required_items_rendered}
            label="模板渲染完整性"
            detail={
              gates.template_required_items_rendered
                ? "必需模板项均已渲染"
                : `${gates.required_template_failed_count} 个必需模板项渲染失败${
                    gates.failed_required_template_items?.length
                      ? `：${gates.failed_required_template_items.join("、")}`
                      : ""
                  }`
            }
          />
          <GateIndicator
            passed={gates.stale_artifacts_clear}
            label="内容时效"
            detail={
              gates.stale_artifacts_clear
                ? "目录、草稿和图表均为当前版本"
                : `${gates.stale_artifact_count} 项草稿、目录或图表已过期`
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

      <fieldset className="export-mode-picker">
        <legend>输出模式</legend>
        <div className="export-mode-picker__options">
          {EXPORT_MODE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="export-mode-picker__option"
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
                <span className="export-mode-picker__description">
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
