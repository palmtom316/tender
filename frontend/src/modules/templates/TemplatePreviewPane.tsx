import { groupBlocksByFormSection, type ProjectTemplateBlock, type ProjectTemplateChapter } from "./templateInstanceModel";

function text(value: unknown, fallback = ""): string {
  if (value == null || value === "") return fallback;
  if (Array.isArray(value)) return value.map((item) => Array.isArray(item) ? item.join(" | ") : String(item)).join(" / ");
  return String(value);
}

function tableTitle(block: ProjectTemplateBlock): string {
  return text(block.render_options_json?.title, block.label);
}

export function TemplatePreviewPane({ chapter }: { chapter: ProjectTemplateChapter | null }) {
  if (!chapter) return <aside className="project-template-workbench__preview">请选择章节</aside>;
  const sections = groupBlocksByFormSection(chapter.blocks ?? []);
  return (
    <aside className="project-template-workbench__preview" aria-label="模板预览">
      <div className="project-template-workbench__docx-page">
        <div className="project-template-workbench__preview-head">
          <h2>DOCX 预览</h2>
          <span>结构预览</span>
        </div>
        <strong>{chapter.chapter_code} {chapter.chapter_title}</strong>
        {sections.pageFormats.map((block) => (
          <p key={block.id}>[页面格式] 页眉页脚 {text(block.render_options_json?.header_footer_ref, "-")}，{text(block.render_options_json?.orientation, "portrait")}</p>
        ))}
        {sections.fixedText.map((block) => <p key={block.id}>{block.content_text || "[固定文本]"}</p>)}
        {sections.tableDefinitions.map((block) => <p key={block.id}>[表格] {tableTitle(block)}</p>)}
        {sections.assetPlaceholders.map((block) => <p key={block.id}>[资产] {block.label}：{text(block.placeholder_key, "-")}</p>)}
        {sections.aiPrompts.map((block) => <p key={block.id}>[AI提示词] {block.label}</p>)}
        {sections.chartPrompts.map((block) => <p key={block.id}>[AI图表] {block.label}：{text(block.placeholder_key, "-")}</p>)}
        {sections.sealMarks.map((block) => <p key={block.id}>[签章] {block.label}</p>)}
        {sections.pricingAttachments.map((block) => <p key={block.id}>[报价附件] {block.label}</p>)}
        <small>结构预览，精排以最终 DOCX 渲染为准。</small>
      </div>
    </aside>
  );
}
