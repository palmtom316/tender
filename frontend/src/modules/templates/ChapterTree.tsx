import { useRef } from "react";
import { chapterStatusLabel, type ProjectTemplateChapter } from "./templateInstanceModel";

interface Props {
  chapters: ProjectTemplateChapter[];
  selectedId?: string | null;
  onSelect: (chapter: ProjectTemplateChapter) => void;
  onReorder: (draggedId: string, targetId: string) => void;
}

export function ChapterTree({ chapters, selectedId, onSelect, onReorder }: Props) {
  const draggedIdRef = useRef<string | null>(null);
  return (
    <div className="project-template-workbench__tree" role="tree" aria-label="项目模板章节树">
      {chapters.map((chapter) => {
        const locked = Boolean(chapter.lock_owner);
        return (
          <button
            type="button"
            role="treeitem"
            key={chapter.id}
            draggable={!locked}
            className={`project-template-workbench__chapter${selectedId === chapter.id ? " is-selected" : ""}`}
            onClick={() => onSelect(chapter)}
            onDragStart={(event) => { draggedIdRef.current = chapter.id; event.dataTransfer?.setData("text/plain", chapter.id); }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const draggedId = event.dataTransfer?.getData("text/plain") || draggedIdRef.current;
              if (draggedId && draggedId !== chapter.id && !locked) onReorder(draggedId, chapter.id);
            }}
          >
            <span>{chapter.chapter_code} {chapter.chapter_title}</span>
            <em>{chapterStatusLabel(chapter)}</em>
          </button>
        );
      })}
    </div>
  );
}
