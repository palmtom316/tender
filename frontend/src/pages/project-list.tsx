import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listProjects, createProject, type Project } from "../lib/api";

export function ProjectListPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");

  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setName("");
      setShowForm(false);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (name.trim()) {
      mutation.mutate({ name: name.trim() });
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <h1>项目列表</h1>
        <button className="btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "取消" : "新建项目"}
        </button>
      </div>

      {showForm && (
        <form className="card create-form" onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="项目名称"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            {mutation.isPending ? "创建中..." : "创建"}
          </button>
          {mutation.isError && (
            <p className="error">{(mutation.error as Error).message}</p>
          )}
        </form>
      )}

      {isLoading && <p>加载中...</p>}
      {error && <p className="error">加载失败: {(error as Error).message}</p>}

      <div className="project-grid">
        {projects.map((p: Project) => (
          <a key={p.id} className="card project-card" href={`/projects/${p.id}/upload`}>
            <h2>{p.name}</h2>
            <div className="meta">
              <span className="badge">{p.status ?? "draft"}</span>
              <span className="date">
                {new Date(p.created_at).toLocaleDateString("zh-CN")}
              </span>
            </div>
          </a>
        ))}
        {!isLoading && projects.length === 0 && (
          <p className="empty">暂无项目，请点击"新建项目"开始</p>
        )}
      </div>
    </div>
  );
}
