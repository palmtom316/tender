import { describe, expect, it } from "vitest";
import {
  canGenerateDraft,
  canGenerateOutline,
  isExportBlockingAdHocStatus,
  missingRequiredInputs,
  taskCardStatusLabel,
} from "./adHocChapterTaskCard";

const card = {
  status: "needs_input",
  chapter_type: "technical_special_plan",
  missing_inputs: [
    { key: "site_type", label: "项目现场类型", input_type: "choice", required: true, answer: null },
    { key: "special_constraint", label: "特殊限制", input_type: "text", required: false, answer: null },
    { key: "has_site_drawing", label: "现场图", input_type: "choice", required: true, answer: "uploaded" },
  ],
  outline: [],
};

describe("adHocChapterTaskCard", () => {
  it("labels statuses", () => {
    expect(taskCardStatusLabel("needs_input")).toBe("待补充信息");
  });

  it("returns only required unanswered inputs", () => {
    expect(missingRequiredInputs(card).map((item) => item.key)).toEqual(["site_type"]);
  });

  it("checks outline and draft actions", () => {
    expect(canGenerateOutline(card)).toBe(false);
    expect(canGenerateOutline({ ...card, missing_inputs: card.missing_inputs.map((item) => ({ ...item, answer: "uploaded" })) })).toBe(true);
    expect(canGenerateOutline({ ...card, status: "draft_ready", missing_inputs: [] })).toBe(false);
    expect(canGenerateDraft({ ...card, status: "outline_ready" })).toBe(false);
    expect(canGenerateDraft({ ...card, status: "outline_confirmed" })).toBe(true);
  });

  it("marks all non draft-ready statuses as export-blocking", () => {
    expect(isExportBlockingAdHocStatus("draft_ready")).toBe(false);
    for (const status of ["task_card_pending", "needs_input", "outline_ready", "outline_confirmed", "blocked_insufficient_evidence"]) {
      expect(isExportBlockingAdHocStatus(status)).toBe(true);
    }
  });
});
