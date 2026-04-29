import { useState } from "react";

import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import { Icon } from "../../../components/ui/Icon";
import type { BatchStandardUploadItem } from "../../../lib/api";
import { uploadStandards } from "../../../lib/api";

type UploadRow = {
  id: string;
  file: File;
  standard_code: string;
  standard_name: string;
  version_year: string;
  specialty: string;
};

function buildUploadRows(files: FileList | null, existingRows: UploadRow[]): { rows: UploadRow[]; error: string } {
  if (!files || files.length === 0) {
    return { rows: existingRows, error: "" };
  }

  const existingNames = new Set(existingRows.map((row) => row.file.name));
  const nextRows = [...existingRows];
  const duplicates: string[] = [];

  for (const file of Array.from(files)) {
    if (existingNames.has(file.name)) {
      duplicates.push(file.name);
      continue;
    }
    existingNames.add(file.name);
    nextRows.push({
      id: `${file.name}-${file.size}-${file.lastModified}`,
      file,
      standard_code: "",
      standard_name: "",
      version_year: "",
      specialty: "",
    });
  }

  return {
    rows: nextRows,
    error: duplicates.length > 0 ? `已忽略重复文件：${duplicates.join("、")}` : "",
  };
}

export function UploadForm({ onUploaded }: { onUploaded: () => void }) {
  const [rows, setRows] = useState<UploadRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [fileInputKey, setFileInputKey] = useState(0);

  const handleFilesSelected = (event: React.ChangeEvent<HTMLInputElement>) => {
    const result = buildUploadRows(event.target.files, rows);
    setRows(result.rows);
    setError(result.error);
  };

  const updateRow = (id: string, field: keyof Omit<UploadRow, "id" | "file">, value: string) => {
    setRows((current) => current.map((row) => (
      row.id === id ? { ...row, [field]: value } : row
    )));
  };

  const removeRow = (id: string) => {
    setRows((current) => current.filter((row) => row.id !== id));
  };

  const canSubmit = rows.length > 0 && rows.every((row) => row.standard_code.trim() && row.standard_name.trim());

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;

    setUploading(true);
    setError("");
    try {
      const payload: BatchStandardUploadItem[] = rows.map((row) => ({
        file: row.file,
        standard_code: row.standard_code.trim(),
        standard_name: row.standard_name.trim(),
        version_year: row.version_year.trim() || undefined,
        specialty: row.specialty.trim() || undefined,
      }));
      await uploadStandards(payload);
      setRows([]);
      setFileInputKey((value) => value + 1);
      onUploaded();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card>
      <form onSubmit={handleSubmit}>
        <div className="standard-upload-header">
          <div>
            <h3 style={{ marginBottom: "var(--space-1)", fontWeight: 600 }}>
              <Icon name="upload-cloud" size={18} /> 批量上传规范文件
            </h3>
            <p className="standard-upload-subtitle">一次可选多个 PDF，提交前必须逐条填写规范编号和规范名称。</p>
          </div>
          <label className="standard-upload-picker">
            <input
              key={fileInputKey}
              type="file"
              accept=".pdf"
              multiple
              onChange={handleFilesSelected}
            />
            <span>选择 PDF 文件</span>
          </label>
        </div>

        {rows.length > 0 ? (
          <div className="standard-upload-table">
            <div className="standard-upload-table__header">
              <span>文件名</span>
              <span>规范编号 *</span>
              <span>规范名称 *</span>
              <span>版本年份</span>
              <span>专业类别</span>
              <span>操作</span>
            </div>
            {rows.map((row) => (
              <div className="standard-upload-row" key={row.id}>
                <div className="standard-upload-file">
                  <strong>{row.file.name}</strong>
                  <span>{Math.max(1, Math.round(row.file.size / 1024))} KB</span>
                </div>
                <input
                  className="clay-input"
                  value={row.standard_code}
                  onChange={(event) => updateRow(row.id, "standard_code", event.target.value)}
                  placeholder="如 GB 50010-2010"
                />
                <input
                  className="clay-input"
                  value={row.standard_name}
                  onChange={(event) => updateRow(row.id, "standard_name", event.target.value)}
                  placeholder="如 混凝土结构设计规范"
                />
                <input
                  className="clay-input"
                  value={row.version_year}
                  onChange={(event) => updateRow(row.id, "version_year", event.target.value)}
                  placeholder="如 2010"
                />
                <input
                  className="clay-input"
                  value={row.specialty}
                  onChange={(event) => updateRow(row.id, "specialty", event.target.value)}
                  placeholder="如 结构"
                />
                <ClayButton type="button" variant="ghost" size="sm" onClick={() => removeRow(row.id)}>
                  移除
                </ClayButton>
              </div>
            ))}
          </div>
        ) : (
          <div className="standard-upload-empty">
            <Icon name="book" size={20} />
            <span>尚未选择文件</span>
          </div>
        )}

        {error && <p className="text-error" style={{ marginBottom: "var(--space-2)" }}>{error}</p>}

        <div className="standard-upload-actions">
          <ClayButton type="submit" disabled={!canSubmit || uploading}>
            {uploading ? "上传并入队中..." : "上传并自动入队"}
          </ClayButton>
          <span className="standard-upload-tip">上传后将自动进入 OCR/AI 流水线，不再需要手动开始处理。</span>
        </div>
      </form>
    </Card>
  );
}
