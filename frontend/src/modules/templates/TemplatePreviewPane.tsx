import { groupBlocksByFormSection, type ProjectTemplateChapter } from "./templateInstanceModel";

export function TemplatePreviewPane({ chapter }: { chapter: ProjectTemplateChapter | null }) {
  if (!chapter) return <aside className="project-template-workbench__preview">请选择章节</aside>;
  const sections = groupBlocksByFormSection(chapter.blocks ?? []);
  return (
    <aside className="project-template-workbench__preview" aria-label="模板预览">
      <h2>预览</h2>
      <strong>{chapter.chapter_code} {chapter.chapter_title}</strong>
      {sections.fixedText.map((block) => <p key={block.id}>{block.content_text || "[固定文本]"}</p>)}
      {sections.pageBreaks.map((block) => <p key={block.id}>[分页] {block.label}</p>)}
      {sections.headerFooters.map((block) => <p key={block.id}>[页眉页脚] {block.label}</p>)}
      {sections.sealMarks.map((block) => <p key={block.id}>[签章] {block.label}</p>)}
      {sections.pricingAttachments.map((block) => <p key={block.id}>[报价附件] {block.label}</p>)}
      <small>预览展示结构标记，不代表最终 DOCX 精排。</small>
    </aside>
  );
}
