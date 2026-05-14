import { useEffect, useState, type ReactNode } from "react";
import { groupBlocksByFormSection, type ProjectTemplateBlock, type ProjectTemplateChapter } from "./templateInstanceModel";

interface Props {
  chapter: ProjectTemplateChapter;
  onSaveBlock: (block: ProjectTemplateBlock, fields: Partial<ProjectTemplateBlock>) => void;
}

type BlockDraft = {
  label: string;
  content_text: string;
  prompt_text: string;
  placeholder_key: string;
  asset_type: string;
  required: boolean;
  render_options_json: Record<string, unknown>;
};

function toText(value: unknown): string {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map((item) => Array.isArray(item) ? item.join(" | ") : String(item)).join("\n");
  return String(value);
}

function toList(value: string): string[] {
  return value.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean);
}

function toRows(value: string): string[][] {
  return value.split(/\r?\n/).map((row) => row.split("|").map((cell) => cell.trim()).filter(Boolean)).filter((row) => row.length > 0);
}

function createDraft(block: ProjectTemplateBlock): BlockDraft {
  return {
    label: block.label ?? "",
    content_text: block.content_text ?? "",
    prompt_text: block.prompt_text ?? "",
    placeholder_key: block.placeholder_key ?? "",
    asset_type: block.asset_type ?? "",
    required: Boolean(block.required),
    render_options_json: { ...(block.render_options_json ?? {}) },
  };
}

function TemplateBlockPanel({
  block,
  locked,
  title,
  saveLabel,
  children,
  onSave,
}: {
  block: ProjectTemplateBlock;
  locked: boolean;
  title: string;
  saveLabel: string;
  children: (draft: BlockDraft, setDraft: (next: BlockDraft) => void) => ReactNode;
  onSave: (block: ProjectTemplateBlock, draft: BlockDraft) => void;
}) {
  const [draft, setDraft] = useState<BlockDraft>(() => createDraft(block));
  useEffect(() => setDraft(createDraft(block)), [block.id]);
  return (
    <section className="project-template-workbench__block" aria-label={title}>
      <div className="project-template-workbench__block-header">
        <strong>{title}</strong>
        <span>{block.label}</span>
      </div>
      {children(draft, setDraft)}
      <button type="button" className="clay-btn clay-btn--outline clay-btn--sm" disabled={locked} onClick={() => onSave(block, draft)}>{saveLabel}</button>
    </section>
  );
}

export function ChapterTemplateForm({ chapter, onSaveBlock }: Props) {
  const sections = groupBlocksByFormSection(chapter.blocks ?? []);
  const locked = Boolean(chapter.lock_owner);

  function saveDraft(block: ProjectTemplateBlock, draft: BlockDraft) {
    onSaveBlock(block, {
      label: draft.label,
      content_text: draft.content_text,
      prompt_text: draft.prompt_text,
      placeholder_key: draft.placeholder_key || null,
      asset_type: draft.asset_type || null,
      required: draft.required,
      render_options_json: draft.render_options_json,
    });
  }

  return (
    <section className="project-template-workbench__form" aria-label="章节模板表单">
      <div className="project-template-workbench__form-header">
        <div>
          <p className="template-panel__eyebrow">章节模板</p>
          <h2>{chapter.chapter_code} {chapter.chapter_title}</h2>
        </div>
        {locked && <span className="text-error">{chapter.lock_owner} 正在编辑</span>}
      </div>

      {sections.fixedText.map((block) => (
        <TemplateBlockPanel key={block.id} block={block} locked={locked} title="固定文本" saveLabel="保存固定文本" onSave={saveDraft}>
          {(draft, setDraft) => (
            <label className="form-label">
              固定文本内容
              <textarea aria-label="固定文本内容" className="clay-input" value={draft.content_text} disabled={locked} onChange={(event) => setDraft({ ...draft, content_text: event.target.value })} />
            </label>
          )}
        </TemplateBlockPanel>
      ))}

      {sections.tableDefinitions.map((block) => (
        <TemplateBlockPanel key={block.id} block={block} locked={locked} title="表格" saveLabel="保存表格" onSave={saveDraft}>
          {(draft, setDraft) => (
            <div className="project-template-workbench__fields">
              <label className="form-label">表格标题<input aria-label="表格标题" className="clay-input" value={toText(draft.render_options_json.title ?? draft.label)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, title: event.target.value } })} /></label>
              <label className="form-label">表头<textarea aria-label="表头" className="clay-input" value={toText(draft.render_options_json.headers)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, headers: toList(event.target.value) } })} /></label>
              <label className="form-label">固定行<textarea aria-label="固定行" className="clay-input" value={toText(draft.render_options_json.fixed_rows)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, fixed_rows: toRows(event.target.value) } })} /></label>
              <label className="form-label">表格说明<textarea aria-label="表格说明" className="clay-input" value={toText(draft.render_options_json.note)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, note: event.target.value } })} /></label>
              <label className="project-template-workbench__check"><input type="checkbox" checked={Boolean(draft.render_options_json.repeat_header)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, repeat_header: event.target.checked } })} />跨页重复表头</label>
            </div>
          )}
        </TemplateBlockPanel>
      ))}

      {sections.assetPlaceholders.map((block) => (
        <TemplateBlockPanel key={block.id} block={block} locked={locked} title="公司资质/证明文件" saveLabel="保存资产占位符" onSave={saveDraft}>
          {(draft, setDraft) => (
            <div className="project-template-workbench__fields project-template-workbench__fields--two">
              <label className="form-label">占位符名称<input aria-label="资产占位符名称" className="clay-input" value={draft.label} disabled={locked} onChange={(event) => setDraft({ ...draft, label: event.target.value })} /></label>
              <label className="form-label">占位符键<input aria-label="资产占位符键" className="clay-input" value={draft.placeholder_key} disabled={locked} onChange={(event) => setDraft({ ...draft, placeholder_key: event.target.value })} /></label>
              <label className="form-label">资产类型<input aria-label="资产类型" className="clay-input" value={draft.asset_type} disabled={locked} onChange={(event) => setDraft({ ...draft, asset_type: event.target.value })} /></label>
              <label className="form-label">匹配规则<input aria-label="资产匹配规则" className="clay-input" value={toText(draft.render_options_json.matching_rule)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, matching_rule: event.target.value } })} /></label>
              <label className="form-label project-template-workbench__fields-full">帮助说明<textarea aria-label="资产帮助说明" className="clay-input" value={toText(draft.render_options_json.help_text)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, help_text: event.target.value } })} /></label>
              <label className="project-template-workbench__check"><input type="checkbox" checked={draft.required} disabled={locked} onChange={(event) => setDraft({ ...draft, required: event.target.checked })} />必填</label>
            </div>
          )}
        </TemplateBlockPanel>
      ))}

      {sections.aiPrompts.map((block) => (
        <TemplateBlockPanel key={block.id} block={block} locked={locked} title="AI 提示词" saveLabel="保存AI提示词" onSave={saveDraft}>
          {(draft, setDraft) => (
            <label className="form-label">
              AI 提示词内容
              <textarea aria-label="AI 提示词内容" className="clay-input" value={draft.prompt_text} disabled={locked} onChange={(event) => setDraft({ ...draft, prompt_text: event.target.value })} />
            </label>
          )}
        </TemplateBlockPanel>
      ))}

      {sections.chartPrompts.map((block) => (
        <TemplateBlockPanel key={block.id} block={block} locked={locked} title="AI 图表" saveLabel="保存AI图表" onSave={saveDraft}>
          {(draft, setDraft) => (
            <div className="project-template-workbench__fields project-template-workbench__fields--two">
              <label className="form-label project-template-workbench__fields-full">AI 图表生成提示词<textarea aria-label="AI 图表生成提示词" className="clay-input" value={draft.prompt_text} disabled={locked} onChange={(event) => setDraft({ ...draft, prompt_text: event.target.value })} /></label>
              <label className="form-label">图表类型<input aria-label="图表类型" className="clay-input" value={toText(draft.render_options_json.chart_type)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, chart_type: event.target.value } })} /></label>
              <label className="form-label">占位符键<input aria-label="图表占位符键" className="clay-input" value={draft.placeholder_key} disabled={locked} onChange={(event) => setDraft({ ...draft, placeholder_key: event.target.value })} /></label>
              <label className="form-label project-template-workbench__fields-full">图表代码<textarea aria-label="图表代码" className="clay-input" value={toText(draft.render_options_json.source_code)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, source_code: event.target.value } })} /></label>
            </div>
          )}
        </TemplateBlockPanel>
      ))}

      {sections.pageFormats.map((block) => (
        <TemplateBlockPanel key={block.id} block={block} locked={locked} title="页面格式" saveLabel="保存页面格式" onSave={saveDraft}>
          {(draft, setDraft) => (
            <div className="project-template-workbench__fields project-template-workbench__fields--two">
              <label className="form-label">分页规则<input aria-label="分页规则" className="clay-input" value={toText(draft.render_options_json.page_break ?? draft.label)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, page_break: event.target.value } })} /></label>
              <label className="form-label">标题级别<input aria-label="标题级别" className="clay-input" value={toText(draft.render_options_json.title_level)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, title_level: event.target.value } })} /></label>
              <label className="form-label">分节符<input aria-label="分节符" className="clay-input" value={toText(draft.render_options_json.section_break)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, section_break: event.target.value } })} /></label>
              <label className="form-label">页眉页脚引用<input aria-label="页眉页脚引用" className="clay-input" value={toText(draft.render_options_json.header_footer_ref)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, header_footer_ref: event.target.value } })} /></label>
              <label className="form-label">页边距<input aria-label="页边距" className="clay-input" value={toText(draft.render_options_json.margins)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, margins: event.target.value } })} /></label>
              <label className="form-label">纸张方向<input aria-label="纸张方向" className="clay-input" value={toText(draft.render_options_json.orientation)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, orientation: event.target.value } })} /></label>
              <label className="form-label">页码规则<input aria-label="页码规则" className="clay-input" value={toText(draft.render_options_json.page_numbering)} disabled={locked} onChange={(event) => setDraft({ ...draft, render_options_json: { ...draft.render_options_json, page_numbering: event.target.value } })} /></label>
            </div>
          )}
        </TemplateBlockPanel>
      ))}
    </section>
  );
}
