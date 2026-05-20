import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  confirmAdHocTaskCardOutline,
  fetchAdHocTaskCard,
  generateAdHocTaskCardOutline,
  updateAdHocTaskCard,
  type AdHocTaskCard as ApiAdHocTaskCard,
  type AdHocTaskCardInput as ApiAdHocTaskCardInput,
  type BidChapter,
} from "../../lib/api";
import { Badge } from "../../components/ui/Badge";
import { ClayButton } from "../../components/ui/ClayButton";
import { LoadingState } from "../../components/ui/LoadingState";
import {
  canGenerateDraft,
  canGenerateOutline,
  missingRequiredInputs,
  taskCardStatusLabel,
} from "./adHocChapterTaskCard";

type Card = ApiAdHocTaskCard;
type CardInput = ApiAdHocTaskCardInput;

function answerValue(value: unknown) {
  if (value === null || value === undefined) return "";
  return String(value);
}

function safeText(value: unknown) {
  return typeof value === "string" && value.trim() ? value : "待确认";
}

function outlineToText(outline: Array<Record<string, unknown>> | undefined) {
  return (outline ?? [])
    .map((row) => {
      const heading = safeText(row.heading);
      const purpose = safeText(row.purpose);
      return `${heading}：${purpose}`;
    })
    .join("\n");
}

function parseOutlineText(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [heading, ...rest] = line.split(/[：:]/);
      return {
        heading: heading.trim(),
        purpose: rest.join("：").trim() || "按招标来源和已确认输入编写。",
      };
    });
}

const CHAPTER_TYPE_LABELS: Record<string, string> = {
  technical_special_plan: "技术专项方案",
  material_attachment: "资料附件",
  table_checklist: "表格清单",
};

export function AdHocChapterTaskCard({
  projectId,
  chapter,
  onGenerateDraft,
  generatingDraft,
}: {
  projectId: string;
  chapter: BidChapter;
  onGenerateDraft: () => void;
  generatingDraft?: boolean;
}) {
  const queryClient = useQueryClient();
  const queryKey = ["ad-hoc-task-card", projectId, chapter.id];
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [outlineText, setOutlineText] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchAdHocTaskCard(projectId, chapter.id, { signal }),
    enabled: Boolean(projectId && chapter.id),
    retry: false,
  });

  const card = data?.card as Card | undefined;

  useEffect(() => {
    if (!card) return;
    setAnswers(Object.fromEntries((card.missing_inputs ?? []).map((item) => [item.key, answerValue(item.answer)])));
    setOutlineText(outlineToText(card.outline));
  }, [card]);

  const requiredMissing = useMemo(() => (card ? missingRequiredInputs({
    missing_inputs: (card.missing_inputs ?? []).map((item) => ({
      ...item,
      answer: answers[item.key] ?? item.answer,
    })),
  }) : []), [answers, card]);

  const optimisticCard = useMemo(() => {
    if (!card) return null;
    return {
      ...card,
      missing_inputs: (card.missing_inputs ?? []).map((item) => ({
        ...item,
        answer: answers[item.key] ?? item.answer,
      })),
    };
  }, [answers, card]);

  const saveAnswers = useMutation({
    mutationFn: () => updateAdHocTaskCard(projectId, chapter.id, { answers }),
    onSuccess: (next) => {
      queryClient.setQueryData(queryKey, next);
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
    },
  });

  const generateOutline = useMutation({
    mutationFn: async () => {
      await updateAdHocTaskCard(projectId, chapter.id, { answers });
      return generateAdHocTaskCardOutline(projectId, chapter.id);
    },
    onSuccess: (next) => {
      queryClient.setQueryData(queryKey, next);
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
    },
  });

  const confirmOutline = useMutation({
    mutationFn: () => confirmAdHocTaskCardOutline(projectId, chapter.id, parseOutlineText(outlineText)),
    onSuccess: (next) => {
      queryClient.setQueryData(queryKey, next);
      queryClient.invalidateQueries({ queryKey: ["bid-outline", projectId] });
    },
  });

  if (isLoading) return <LoadingState label="新增章节任务卡加载中" rows={3} compact />;
  if (error) {
    return (
      <section className="chapter-delivery-card" aria-label="新增章节任务卡">
        <div className="chapter-delivery-card__header">
          <div>
            <strong>新增章节任务卡</strong>
            <p>任务卡加载失败，请检查该章节是否已由目录映射标记为新增章节。</p>
          </div>
        </div>
      </section>
    );
  }
  if (!card || !optimisticCard) return null;

  return (
    <section className="chapter-delivery-card" aria-label="新增章节任务卡">
      <div className="chapter-delivery-card__header">
        <div>
          <strong>{chapter.chapter_code} {chapter.chapter_title}</strong>
          <p>先补业务事实和招标来源，再确认大纲；未确认前不生成正文。</p>
        </div>
        <Badge variant={card.status === "draft_ready" ? "success" : "warning"}>
          {taskCardStatusLabel(card.status)}
        </Badge>
      </div>

      <div className="workflow-gate-panel__chips">
        <span>{requiredMissing.length > 0 ? `还缺 ${requiredMissing.length} 项必填信息` : "必填信息已补齐"}</span>
        <span>类型：{CHAPTER_TYPE_LABELS[card.chapter_type ?? "technical_special_plan"] ?? "技术专项方案"}</span>
      </div>

      <div className="material-slot-list">
        <article className="material-slot-item">
          <div>
            <strong>招标来源</strong>
            {(card.source_anchors ?? []).length === 0 ? <p>暂无来源，请补充招标文件定位。</p> : null}
            {(card.source_anchors ?? []).map((anchor, index) => (
              <div key={`${anchor.requirement_id ?? index}`}>
                <span>{safeText(anchor.source_locator)}</span>
                <p>{safeText(anchor.text)}</p>
              </div>
            ))}
          </div>
        </article>
        <article className="material-slot-item">
          <div>
            <strong>必须响应</strong>
            {(card.must_respond ?? []).length === 0 ? <p>待从招标要求提取。</p> : null}
            {(card.must_respond ?? []).map((point) => <p key={point}>{point}</p>)}
          </div>
        </article>
      </div>

      <div className="material-slot-list">
        {(card.missing_inputs ?? []).map((input: CardInput) => (
          <label key={input.key} className="material-slot-item">
            <div>
              <strong>{input.label}{input.required ? " *" : ""}</strong>
              {input.input_type === "choice" ? (
                <select
                  className="clay-input"
                  aria-label={input.label}
                  value={answers[input.key] ?? ""}
                  onChange={(event) => setAnswers((current) => ({ ...current, [input.key]: event.target.value }))}
                >
                  <option value="">请选择</option>
                  {(input.options ?? []).map((option) => <option key={option} value={option}>{option}</option>)}
                </select>
              ) : (
                <input
                  className="clay-input"
                  aria-label={input.label}
                  value={answers[input.key] ?? ""}
                  onChange={(event) => setAnswers((current) => ({ ...current, [input.key]: event.target.value }))}
                />
              )}
            </div>
          </label>
        ))}
      </div>

      <div className="chart-task-card__actions">
        <ClayButton size="sm" variant="secondary" onClick={() => saveAnswers.mutate()} disabled={saveAnswers.isPending}>
          保存信息
        </ClayButton>
        <ClayButton
          size="sm"
          variant="secondary"
          onClick={() => generateOutline.mutate()}
          disabled={!canGenerateOutline(optimisticCard) || generateOutline.isPending}
        >
          生成章节大纲
        </ClayButton>
        <ClayButton
          size="sm"
          variant="secondary"
          onClick={() => confirmOutline.mutate()}
          disabled={!outlineText.trim() || confirmOutline.isPending}
        >
          确认大纲
        </ClayButton>
        <ClayButton
          size="sm"
          onClick={onGenerateDraft}
          disabled={!canGenerateDraft(card) || generatingDraft}
        >
          生成正文
        </ClayButton>
      </div>

      <label>
        <strong>章节大纲</strong>
        <textarea
          className="clay-textarea draft-editor"
          aria-label="新增章节大纲"
          value={outlineText}
          onChange={(event) => setOutlineText(event.target.value)}
          placeholder="生成大纲后可在此审阅或微调。"
        />
      </label>
    </section>
  );
}
