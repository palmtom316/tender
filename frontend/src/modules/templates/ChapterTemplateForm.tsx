import { useState } from "react";
import { groupBlocksByFormSection, type ProjectTemplateBlock, type ProjectTemplateChapter } from "./templateInstanceModel";

interface Props {
  chapter: ProjectTemplateChapter;
  onSaveBlock: (block: ProjectTemplateBlock, fields: Partial<ProjectTemplateBlock>) => void;
}

export function ChapterTemplateForm({ chapter, onSaveBlock }: Props) {
  const sections = groupBlocksByFormSection(chapter.blocks ?? []);
  const fixed = sections.fixedText[0];
  const [fixedText, setFixedText] = useState(fixed?.content_text ?? "");
  const [showAi, setShowAi] = useState(false);
  const locked = Boolean(chapter.lock_owner);

  return (
    <section className="project-template-workbench__form" aria-label="章节模板表单">
      <div className="project-template-workbench__form-header">
        <h2>{chapter.chapter_code} {chapter.chapter_title}</h2>
        {locked && <span className="text-error">{chapter.lock_owner} 正在编辑</span>}
      </div>
      {fixed && (
        <label className="form-label">
          固定文本
          <textarea aria-label="固定文本内容" className="clay-input" value={fixedText} disabled={locked} onChange={(event) => setFixedText(event.target.value)} />
          <button type="button" className="clay-btn clay-btn--outline clay-btn--sm" disabled={locked} onClick={() => onSaveBlock(fixed, { content_text: fixedText })}>保存固定文本</button>
        </label>
      )}
      <section>
        <button type="button" className="clay-btn clay-btn--ghost clay-btn--sm" onClick={() => setShowAi((value) => !value)}>AI 提示词</button>
        {showAi && sections.aiPrompts.map((block) => (
          <textarea key={block.id} aria-label="AI 提示词内容" className="clay-input" defaultValue={block.prompt_text ?? ""} disabled={locked} />
        ))}
      </section>
      <section className="project-template-workbench__mini-grid">
        <span>变量 {sections.variables.length}</span>
        <span>素材位 {sections.assetPlaceholders.length}</span>
        <span>分页 {sections.pageBreaks.length}</span>
        <span>页眉页脚 {sections.headerFooters.length}</span>
        <span>签章 {sections.sealMarks.length}</span>
        <span>报价附件 {sections.pricingAttachments.length}</span>
      </section>
    </section>
  );
}
