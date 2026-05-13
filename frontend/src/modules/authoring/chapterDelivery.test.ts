import { describe, expect, it } from "vitest";
import type { BidChapter, ChartAsset } from "../../lib/api";
import {
  buildChartTaskCards,
  buildMaterialSlots,
  chapterDeliveryKind,
  deliveryKindLabel,
  readableContextCount,
} from "./chapterDelivery";

function chapter(overrides: Partial<BidChapter>): BidChapter {
  return {
    id: "chapter-1",
    chapter_code: "3",
    chapter_title: "企业资信情况",
    volume_type: "business",
    sort_order: 1,
    metadata_json: {},
    ...overrides,
  };
}

describe("chapterDelivery", () => {
  it("classifies confirmed technical chapters as ai_content", () => {
    expect(chapterDeliveryKind(chapter({ chapter_code: "8", volume_type: "technical" }))).toBe("ai_content");
    expect(deliveryKindLabel("ai_content")).toBe("AI 正文");
  });

  it("classifies non-technical chapters as material_composition", () => {
    expect(chapterDeliveryKind(chapter({ chapter_code: "3", volume_type: "business" }))).toBe("material_composition");
    expect(deliveryKindLabel("material_composition")).toBe("资料编排");
  });

  it("builds material slots from business assembly missing materials", () => {
    const slots = buildMaterialSlots(chapter({ chapter_code: "3" }), {
      missing_materials: [
        { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "未选择证书" },
        { chapter_code: "4", material_name: "项目经理", material_type: "person", reason: "其他章节" },
      ],
    });

    expect(slots).toEqual([
      expect.objectContaining({
        label: "安全生产许可证",
        sourceLabel: "证书/附件",
        status: "missing",
        helpText: "未选择证书",
      }),
    ]);
  });

  it("provides default material slots when no backend slot data exists", () => {
    const slots = buildMaterialSlots(chapter({ chapter_title: "企业资信情况" }), undefined);

    expect(slots.map((slot) => slot.label)).toContain("企业营业执照");
    expect(slots.map((slot) => slot.label)).toContain("资质证书");
  });

  it("marks slot as ready and exposes bound label after binding", () => {
    const slots = buildMaterialSlots(
      chapter({ chapter_code: "3" }),
      {
        missing_materials: [
          { chapter_code: "3", material_key: "safety_license", material_name: "安全生产许可证", material_type: "certificate", reason: "缺证书" },
        ],
      },
      { safety_license: "安全生产许可证（推荐）" },
    );

    expect(slots).toEqual([
      expect.objectContaining({
        label: "安全生产许可证",
        status: "ready",
        boundLabel: "安全生产许可证（推荐）",
      }),
    ]);
  });

  it("builds chart task cards from recommended charts and assets", () => {
    const assets: ChartAsset[] = [
      {
        id: "asset-1",
        project_id: "proj-1",
        outline_node_id: "chapter-1",
        chart_type: "quality_system",
        title: "质量管理体系图",
        spec_json: {},
        rendered_svg: "<svg />",
        placeholder_key: "quality_system",
        status: "draft",
        created_at: "2026-05-10T00:00:00Z",
      },
    ];

    const tasks = buildChartTaskCards(["quality_system", "schedule_gantt"], assets);

    expect(tasks).toEqual([
      expect.objectContaining({ key: "quality_system", title: "质量管理体系图", status: "draft", assetId: "asset-1" }),
      expect.objectContaining({ key: "schedule_gantt", title: "施工进度横道图", status: "not_generated", assetId: null }),
    ]);
  });

  it("counts context arrays in readable Chinese labels", () => {
    expect(readableContextCount({ constraints: [{ id: 1 }], scoring_items: [] }, "constraints")).toBe("约束：1");
    expect(readableContextCount({ constraints: [{ id: 1 }], scoring_items: [] }, "scoring_items")).toBe("评分：0");
  });
});
