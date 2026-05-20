export type AdHocTaskCardStatus =
  | "task_card_pending"
  | "needs_input"
  | "outline_ready"
  | "outline_confirmed"
  | "draft_ready"
  | "blocked_insufficient_evidence"
  | string;

export interface AdHocTaskCardInput {
  key: string;
  label: string;
  input_type: string;
  options?: string[];
  required?: boolean;
  answer?: unknown;
}

export interface AdHocTaskCard {
  status: AdHocTaskCardStatus;
  chapter_type?: string;
  source_anchors?: Array<Record<string, unknown>>;
  must_respond?: string[];
  missing_inputs?: AdHocTaskCardInput[];
  outline?: Array<Record<string, unknown>>;
}

const STATUS_LABELS: Record<string, string> = {
  task_card_pending: "待创建任务卡",
  needs_input: "待补充信息",
  outline_ready: "大纲待确认",
  outline_confirmed: "大纲已确认",
  draft_ready: "正文已生成",
  blocked_insufficient_evidence: "证据不足",
};

export function taskCardStatusLabel(status: AdHocTaskCardStatus) {
  return STATUS_LABELS[status] ?? "未知状态";
}

function answered(value: unknown) {
  return value !== null && value !== undefined && !(typeof value === "string" && value.trim() === "");
}

export function missingRequiredInputs(card: Pick<AdHocTaskCard, "missing_inputs">) {
  return (card.missing_inputs ?? []).filter((item) => item.required && !answered(item.answer));
}

export function canGenerateOutline(card: AdHocTaskCard) {
  return (card.status === "task_card_pending" || card.status === "needs_input")
    && missingRequiredInputs(card).length === 0;
}

export function canGenerateDraft(card: AdHocTaskCard) {
  return card.status === "outline_confirmed";
}

export function isExportBlockingAdHocStatus(status: AdHocTaskCardStatus) {
  return status !== "draft_ready";
}
