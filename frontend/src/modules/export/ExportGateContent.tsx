import { useQuery } from "@tanstack/react-query";
import { fetchExportGates } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";

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

  const { data: gatesData, isLoading } = useQuery({
    queryKey: ["export-gates", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchExportGates(projectId, { signal });
    },
    enabled: !!projectId,
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  const gates = gatesData?.gates;

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
            passed={gates.format_passed}
            label="格式校验"
            detail={gates.format_passed ? "格式合规" : "格式不合规"}
          />
        </div>
      )}

      {gatesData && (
        <ClayButton
          size="lg"
          disabled={!gatesData.can_export}
          style={{ marginBottom: "var(--space-8)" }}
        >
          {gatesData.can_export ? "开始导出" : "门禁未通过，无法导出"}
        </ClayButton>
      )}
    </div>
  );
}
