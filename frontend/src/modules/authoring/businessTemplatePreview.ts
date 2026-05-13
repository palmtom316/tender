import type { BidChapter, BusinessTemplatePreview, BusinessTemplatePreviewChapter } from "../../lib/api";

export function matchPreviewChapter(
  preview: BusinessTemplatePreview | undefined,
  chapter: Pick<BidChapter, "chapter_code" | "chapter_title" | "volume_type"> | null | undefined,
): BusinessTemplatePreviewChapter | null {
  if (!preview || !chapter || chapter.volume_type === "technical") return null;
  return preview.chapters.find((row) => row.chapter_code === chapter.chapter_code)
    ?? preview.chapters.find((row) => row.chapter_title.includes(chapter.chapter_title) || chapter.chapter_title.includes(row.chapter_title))
    ?? null;
}
