import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

interface ChapterEditorPageProps {
  projectId: string;
}

interface Draft {
  id: string;
  chapter_code: string;
  content_md: string;
  updated_at: string;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN = localStorage.getItem("tender_token") ?? "dev-token";
const headers = { Authorization: `Bearer ${TOKEN}` };

async function fetchDrafts(projectId: string): Promise<Draft[]> {
  const res = await fetch(`${BASE_URL}/api/projects/${projectId}/drafts`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function updateDraft(draftId: string, contentMd: string): Promise<Draft> {
  const res = await fetch(`${BASE_URL}/api/drafts/${draftId}`, {
    method: "PUT",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ content_md: contentMd }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function ChapterEditorPage({ projectId }: ChapterEditorPageProps) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  const { data: drafts = [], isLoading } = useQuery({
    queryKey: ["drafts", projectId],
    queryFn: () => fetchDrafts(projectId),
  });

  const save = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      updateDraft(id, content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["drafts", projectId] });
    },
  });

  const selected = drafts.find((d) => d.id === selectedId);

  const handleSelect = (draft: Draft) => {
    setSelectedId(draft.id);
    setEditContent(draft.content_md);
  };

  return (
    <div className="page">
      <div className="page-header">
        <a href={`/projects/${projectId}/requirements`} className="back-link">&larr; 返回</a>
        <h1>章节编辑</h1>
      </div>

      <div className="editor-layout">
        <aside className="outline-panel">
          <h2>提纲</h2>
          {isLoading && <p>加载中...</p>}
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
            <p className="empty">暂无章节草稿</p>
          )}
        </aside>

        <main className="editor-main">
          {selected ? (
            <>
              <div className="editor-toolbar">
                <h2>{selected.chapter_code}</h2>
                <button
                  className="btn-primary"
                  onClick={() => save.mutate({ id: selected.id, content: editContent })}
                  disabled={save.isPending}
                >
                  {save.isPending ? "保存中..." : "保存"}
                </button>
              </div>
              <textarea
                className="editor-textarea"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
              />
            </>
          ) : (
            <p className="empty">请从左侧选择章节</p>
          )}
        </main>
      </div>
    </div>
  );
}
