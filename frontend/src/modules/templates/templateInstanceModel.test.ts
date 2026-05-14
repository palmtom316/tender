import { describe, expect, it } from "vitest";
import { chapterStatusLabel, groupBlocksByFormSection, reconciliationSeverityCounts, templateInstanceCanConfirm } from "./templateInstanceModel";

describe("templateInstanceModel", () => {
  it("groups API blocks into form sections", () => {
    const sections = groupBlocksByFormSection([
      { id: "b1", block_type: "fixed_text", label: "固定", sort_order: 1 },
      { id: "b2", block_type: "ai_prompt", label: "提示", sort_order: 2 },
      { id: "b3", block_type: "seal_mark", label: "盖章", sort_order: 3 },
      { id: "b4", block_type: "excel_attachment", label: "报价", sort_order: 4 },
    ] as any);

    expect(sections.fixedText).toHaveLength(1);
    expect(sections.aiPrompts).toHaveLength(1);
    expect(sections.sealMarks[0].label).toBe("盖章");
    expect(sections.pricingAttachments[0].block_type).toBe("excel_attachment");
  });

  it("detects unresolved critical template blockers before confirmation", () => {
    expect(templateInstanceCanConfirm({ status: "draft", reconciliation_summary: { critical: 1 }, unanswered_requirement_count: 0, pending_seal_checklist_count: 0 } as any)).toEqual({ canConfirm: false, reason: "仍有 1 个阻断级模板差异" });
    expect(templateInstanceCanConfirm({ status: "draft", reconciliation_summary: { critical: 0 }, unanswered_requirement_count: 2, pending_seal_checklist_count: 0 } as any).reason).toContain("2 条要求未响应");
    expect(templateInstanceCanConfirm({ status: "draft", reconciliation_summary: { critical: 0 }, unanswered_requirement_count: 0, pending_seal_checklist_count: 1 } as any).reason).toContain("1 项签章未确认");
    expect(templateInstanceCanConfirm({ status: "draft", reconciliation_summary: { critical: 0 }, unanswered_requirement_count: 0, pending_seal_checklist_count: 0 } as any).canConfirm).toBe(true);
  });

  it("maps chapter status and severity counts", () => {
    expect(chapterStatusLabel({ enabled: false } as any)).toBe("已停用");
    expect(chapterStatusLabel({ chapter_status: "confirmed" } as any)).toBe("已确认");
    expect(reconciliationSeverityCounts({ counts_by_severity: { critical: 2, medium: 3 } })).toEqual({ critical: 2, medium: 3, low: 0 });
  });
});
