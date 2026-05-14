import { describe, expect, it } from "vitest";
import { formatTemplateEditImpact } from "./templateEditPropagation";

describe("templateEditPropagation", () => {
  it("formats template revision impact for tender engineers", () => {
    expect(
      formatTemplateEditImpact({
        revision_no: 8,
        impact: { stale_draft_count: 2, stale_chart_count: 1, stale_export_artifact_count: 3 },
      }),
    ).toBe(
      "已保存模板修订 8，受影响：正文草稿 2、图表 1、导出产物 3",
    );
  });

  it("falls back when backend returns a legacy block response", () => {
    expect(formatTemplateEditImpact({})).toBe("已保存模板块，预览已刷新");
  });
});
