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
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可编辑生成的章节草稿。</p>
      </div>
    );
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
          {isLoading && (
            <div className="skeleton-stack" aria-label="章节草稿加载中">
              <div className="skeleton-line" />
              <div className="skeleton-line" />
              <div className="skeleton-line" />
            </div>
          )}
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
            <div className="empty-state">
              <span className="empty-state__icon">章</span>
              <p className="empty-state__title">暂无章节草稿</p>
              <p className="empty-state__description">完成解析和要求确认后，生成的章节草稿会出现在这里。</p>
            </div>
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
                className="clay-textarea draft-editor"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                aria-label={`${selected.chapter_code} 章节正文`}
              />
            </>
          ) : (
            <div className="empty-state">
              <span className="empty-state__icon">编</span>
              <p className="empty-state__title">选择章节开始编辑</p>
              <p className="empty-state__description">左侧选择章节后，可在这里调整正文并保存。</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
