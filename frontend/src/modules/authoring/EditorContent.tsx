import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchDrafts, updateDraft } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { ClayButton } from "../../components/ui/ClayButton";

export function EditorContent() {
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  const { data: drafts = [], isLoading } = useQuery({
    queryKey: ["drafts", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return fetchDrafts(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const save = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      updateDraft(id, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  if (!projectId) {
    return <p className="empty-state">请先从「投标项目」模块选择一个项目</p>;
  }

  const selected = drafts.find((d) => d.id === selectedId);

  const handleSelect = (draft: { id: string; content_md: string }) => {
    setSelectedId(draft.id);
    setEditContent(draft.content_md);
  };

  return (
    <div>
      <h1 className="section-heading">章节编辑</h1>

      <div className="editor-layout">
        <aside className="outline-panel">
          <h2>提纲</h2>
          {isLoading && <div className="spinner" />}
          {drafts.map((d) => (
            <div
              key={d.id}
              className={`outline-item ${d.id === selectedId ? "active" : ""}`}
              onClick={() => handleSelect(d)}
            >
              <span className="outline-code">{d.chapter_code}</span>
              <span className="outline-date">
                {new Date(d.updated_at).toLocaleDateString("zh-CN")}
              </span>
            </div>
          ))}
          {!isLoading && drafts.length === 0 && (
            <p className="empty-state">暂无章节草稿</p>
          )}
        </aside>

        <main className="editor-main">
          {selected ? (
            <>
              <div className="editor-toolbar">
                <h2>{selected.chapter_code}</h2>
                <ClayButton
                  onClick={() => save.mutate({ id: selected.id, content: editContent })}
                  disabled={save.isPending}
                >
                  {save.isPending ? "保存中..." : "保存"}
                </ClayButton>
              </div>
              <textarea
                className="clay-textarea"
                style={{ flex: 1, minHeight: 400 }}
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
              />
            </>
          ) : (
            <p className="empty-state">请从左侧选择章节</p>
          )}
        </main>
      </div>
    </div>
  );
}
