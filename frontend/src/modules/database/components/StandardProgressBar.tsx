import type { Standard } from "../../../lib/api";

type StandardProgressBarProps = {
  processingStatus: string;
  ocrStatus: string | null;
  aiStatus: string | null;
};

function progressMeta(
  processingStatus: string,
  ocrStatus: string | null,
  aiStatus: string | null,
): { percent: number; label: string; hint: string; tone: "default" | "active" | "success" | "danger" } {
  if (processingStatus === "failed") {
    if (aiStatus === "failed") {
      return { percent: 78, label: "AI 失败", hint: "AI 解析失败，可重新入队", tone: "danger" };
    }
    if (ocrStatus === "failed") {
      return { percent: 28, label: "OCR 失败", hint: "OCR 失败，可重新入队", tone: "danger" };
    }
    return { percent: 40, label: "处理失败", hint: "处理失败，可重新入队", tone: "danger" };
  }
  switch (processingStatus) {
    case "queued_ocr":
      return { percent: 8, label: "等待 OCR", hint: "已入 OCR 队列", tone: "default" };
    case "parsing":
      return { percent: 38, label: "OCR 中", hint: "正在执行 OCR", tone: "active" };
    case "queued_ai":
      return { percent: 54, label: "等待 AI", hint: "OCR 完成，等待 AI 解析", tone: "default" };
    case "processing":
      return { percent: 82, label: "AI 解析中", hint: "正在执行 AI 条款解析", tone: "active" };
    case "completed":
      return { percent: 100, label: "完成", hint: "规范已可查阅", tone: "success" };
    default:
      return { percent: 0, label: "待处理", hint: "尚未开始处理", tone: "default" };
  }
}

export function standardStatusLabel(std: Pick<Standard, "processing_status" | "ocr_status" | "ai_status">): string {
  return progressMeta(std.processing_status, std.ocr_status, std.ai_status).label;
}

export function StandardProgressBar({
  processingStatus,
  ocrStatus,
  aiStatus,
}: StandardProgressBarProps) {
  const meta = progressMeta(processingStatus, ocrStatus, aiStatus);

  return (
    <div className={`standard-progress standard-progress--${meta.tone}`}>
      <div className="standard-progress__top">
        <span className="standard-progress__label">{meta.label}</span>
        <span className="standard-progress__percent">{meta.percent}%</span>
      </div>
      <div className="standard-progress__track">
        <div className="standard-progress__fill" style={{ width: `${meta.percent}%` }} />
      </div>
      <div className="standard-progress__hint">{meta.hint}</div>
    </div>
  );
}
