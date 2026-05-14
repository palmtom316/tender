import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { confirmProjectTemplateInstance, fetchProjectTemplateInstance, reorderProjectTemplateChapters, updateProjectTemplateBlock } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ChapterTree } from "./ChapterTree";
import { ChapterTemplateForm } from "./ChapterTemplateForm";
import { TemplatePreviewPane } from "./TemplatePreviewPane";
import { templateInstanceCanConfirm, type ProjectTemplateBlock, type ProjectTemplateChapter, type ProjectTemplateInstance } from "./templateInstanceModel";

export function ProjectTemplateWorkbench({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const nav = useNavigation();
  const [localChapters, setLocalChapters] = useState<ProjectTemplateChapter[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = useQuery({ queryKey: ["project-template-instance", projectId], queryFn: () => fetchProjectTemplateInstance(projectId) });
  const instance = query.data as ProjectTemplateInstance | undefined;
  const chapters = localChapters ?? instance?.chapters ?? [];
  const selected = chapters.find((chapter) => chapter.id === selectedId) ?? chapters[0] ?? null;
  const confirmState = templateInstanceCanConfirm(instance ?? {});

  const reorderMutation = useMutation({
    mutationFn: (next: ProjectTemplateChapter[]) => reorderProjectTemplateChapters(instance!.id, { ordered_tree: next.map((chapter, index) => ({ chapter_id: chapter.id, parent_id: null, sort_order: index })) }),
    onError: () => { setLocalChapters(instance?.chapters ?? []); setError("保存失败，已恢复原顺序"); },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["project-template-instance", projectId] }),
  });
  const updateBlock = useMutation({ mutationFn: ({ block, fields }: { block: ProjectTemplateBlock; fields: Partial<ProjectTemplateBlock> }) => updateProjectTemplateBlock(block.id, fields) });
  const confirm = useMutation({
    mutationFn: () => confirmProjectTemplateInstance(instance!.id),
    onSuccess: () => nav.navigate("authoring", "editor", projectId),
  });

  const orderedChapters = useMemo(() => [...chapters].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)), [chapters]);

  if (query.isLoading) return <div className="spinner" />;
  if (!instance) return <p className="text-error">项目模板实例未生成</p>;

  function handleReorder(draggedId: string, targetId: string) {
    const current = orderedChapters;
    const dragged = current.find((chapter) => chapter.id === draggedId);
    const targetIndex = current.findIndex((chapter) => chapter.id === targetId);
    if (!dragged || targetIndex < 0) return;
    const without = current.filter((chapter) => chapter.id !== draggedId);
    const next = [...without.slice(0, targetIndex + 1), dragged, ...without.slice(targetIndex + 1)].map((chapter, index) => ({ ...chapter, sort_order: index }));
    setError(null);
    setLocalChapters(next);
    reorderMutation.mutate(next);
  }

  return (
    <div className="project-template-workbench">
      <header className="project-template-workbench__header">
        <div><p className="template-panel__eyebrow">项目模板实例</p><h1>{instance.display_name}</h1></div>
        <button type="button" className="clay-btn clay-btn--primary" disabled={!confirmState.canConfirm || confirm.isPending} onClick={() => confirm.mutate()}>确认模板</button>
      </header>
      {!confirmState.canConfirm && <p className="text-error">{confirmState.reason}</p>}
      {error && <p className="text-error">{error}</p>}
      <div className="project-template-workbench__grid">
        <ChapterTree chapters={orderedChapters} selectedId={selected?.id} onSelect={(chapter) => setSelectedId(chapter.id)} onReorder={handleReorder} />
        {selected && <ChapterTemplateForm chapter={selected} onSaveBlock={(block, fields) => updateBlock.mutate({ block, fields })} />}
        <TemplatePreviewPane chapter={selected} />
      </div>
    </div>
  );
}
