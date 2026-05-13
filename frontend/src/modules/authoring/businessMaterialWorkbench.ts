import type { MaterialSlotSummary } from "./chapterDelivery";

export interface BusinessMaterialCandidate {
  key: string;
  label: string;
  groupLabel: string;
  sourceLabel: string;
  summary: string;
}

function candidateGroupForSource(sourceLabel: string) {
  if (sourceLabel.includes("人员")) return "人员资料候选";
  if (sourceLabel.includes("业绩")) return "业绩资料候选";
  if (sourceLabel.includes("证书") || sourceLabel.includes("附件")) return "证照/附件候选";
  return "公司资料候选";
}

export function buildBusinessMaterialCandidates(
  slot: MaterialSlotSummary | null | undefined,
  chapterTitle: string,
): BusinessMaterialCandidate[] {
  if (!slot) return [];

  const sharedSummary = chapterTitle ? `适用于章节：${chapterTitle}` : "适用于当前章节";
  const candidates: BusinessMaterialCandidate[] = [
    {
      key: `${slot.key}-company`,
      label: `${slot.label}（公司基础资料）`,
      groupLabel: "公司资料候选",
      sourceLabel: "公司资料库",
      summary: sharedSummary,
    },
  ];

  const slotGroup = candidateGroupForSource(slot.sourceLabel);
  if (slotGroup !== "公司资料候选") {
    candidates.push({
      key: `${slot.key}-primary`,
      label: `${slot.label}（推荐）`,
      groupLabel: slotGroup,
      sourceLabel: slot.sourceLabel,
      summary: `优先从${slot.sourceLabel}补充该资料位。`,
    });
  }

  if (/证|许可|执照|附件/.test(slot.label) && slotGroup !== "证照/附件候选") {
    candidates.push({
      key: `${slot.key}-evidence`,
      label: `${slot.label}（附件）`,
      groupLabel: "证照/附件候选",
      sourceLabel: "证书/附件",
      summary: "从公司证照和附件资料中选择。",
    });
  }

  return candidates;
}

export function groupBusinessMaterialCandidates(candidates: BusinessMaterialCandidate[]) {
  const groups = new Map<string, BusinessMaterialCandidate[]>();
  for (const candidate of candidates) {
    const existing = groups.get(candidate.groupLabel) ?? [];
    existing.push(candidate);
    groups.set(candidate.groupLabel, existing);
  }
  return Array.from(groups.entries()).map(([groupLabel, rows]) => ({ groupLabel, rows }));
}
