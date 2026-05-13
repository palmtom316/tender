import { useState } from "react";

import { ClayButton } from "../../../components/ui/ClayButton";
import {
  backupCompanybaseUrl,
  importCompanybaseWorkbook,
  validateCompanybaseWorkbook,
  type CompanybaseReport,
} from "../../../lib/api";

const SUMMARY_LABELS = ["公司主体", "公司资料", "人员资料", "附件索引"];

export function CompanybaseImportWorkbench() {
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<CompanybaseReport | null>(null);
  const [status, setStatus] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (action: "validate" | "dry-run" | "import") => {
    if (!file) {
      setError("请先选择 companybase_master.xlsx");
      return;
    }
    if (action === "import" && !window.confirm("确认把资料包写入当前本地数据库？")) return;
    setBusy(true);
    setError(null);
    try {
      const next = action === "validate"
        ? await validateCompanybaseWorkbook(file)
        : await importCompanybaseWorkbook(file, action === "dry-run");
      setReport(next);
      setStatus(action === "import" ? "正式导入完成" : action === "dry-run" ? "Dry-run 完成" : "校验完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "资料包处理失败");
    } finally {
      setBusy(false);
    }
  };

  const downloadBackup = () => {
    window.location.href = backupCompanybaseUrl();
  };

  const hasBlockingIssues = (report?.p0_count ?? 0) > 0;

  return (
    <section className="template-panel companybase-workbench" aria-label="资料包导入备份">
      <div className="template-panel__header">
        <div>
          <div className="template-panel__eyebrow">Companybase</div>
          <h2>公司及人员资料包</h2>
          <p className="template-panel__description">
            用 Excel 资料包批量测试公司主体、公司资料、人员资料和附件索引；先校验和 dry-run，再确认写库。
          </p>
        </div>
        <ClayButton type="button" variant="outline" onClick={downloadBackup}>下载资料包备份</ClayButton>
      </div>

      <div className="asset-toolbar__filters">
        <input
          className="clay-input"
          aria-label="选择资料包 Excel"
          type="file"
          accept=".xlsx"
          onChange={(event) => {
            setFile(event.target.files?.[0] ?? null);
            setReport(null);
            setStatus("");
            setError(null);
          }}
        />
        <ClayButton type="button" onClick={() => void run("validate")} disabled={busy || !file}>
          校验资料包
        </ClayButton>
        <ClayButton type="button" variant="outline" onClick={() => void run("dry-run")} disabled={busy || !file}>
          Dry-run 预演导入
        </ClayButton>
        <ClayButton type="button" variant="primary" onClick={() => void run("import")} disabled={busy || !file || hasBlockingIssues}>
          确认导入
        </ClayButton>
      </div>

      {file && <p className="subtle-copy">当前文件：{file.name}</p>}
      {status && <div className="status-banner status-banner--success">{status}</div>}
      {error && <div className="status-banner status-banner--danger">{error}</div>}

      {report ? <ReportView report={report} /> : (
        <div className="template-strip-empty">
          选择 `companybase_master.xlsx` 后先校验。P0 阻断问题必须修复；P1 是提醒，不阻断导入。
        </div>
      )}
    </section>
  );
}

function ReportView({ report }: { report: CompanybaseReport }) {
  const issueRows = report.issues ?? [];
  return (
    <div className="company-library-dashboard">
      <div className="template-summary">
        {SUMMARY_LABELS.map((label) => (
          <div key={label} className="template-summary__pill">
            <span>{label}</span>
            <strong>{report.summary[label] ?? 0}</strong>
          </div>
        ))}
        <div className="template-summary__pill"><span>P0</span><strong>{report.p0_count}</strong></div>
        <div className="template-summary__pill"><span>P1</span><strong>{report.p1_count}</strong></div>
        <div className="template-summary__pill"><span>新增</span><strong>{report.actions.created}</strong></div>
        <div className="template-summary__pill"><span>更新</span><strong>{report.actions.updated}</strong></div>
        <div className="template-summary__pill"><span>跳过</span><strong>{report.actions.skipped}</strong></div>
      </div>

      <div className="template-panel">
        <h3 className="panel-title-tight">校验问题</h3>
        {issueRows.length === 0 ? <div className="template-strip-empty">没有发现问题。</div> : (
          <table className="asset-table">
            <thead><tr><th>级别</th><th>Sheet</th><th>行</th><th>说明</th></tr></thead>
            <tbody>
              {issueRows.map((issue, index) => (
                <tr key={`${issue.sheet}-${issue.row}-${index}`}>
                  <td>{issue.severity}</td>
                  <td>{issue.sheet}</td>
                  <td>{issue.row ?? "—"}</td>
                  <td>{issue.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
