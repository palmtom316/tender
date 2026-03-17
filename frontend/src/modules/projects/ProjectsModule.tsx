import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listProjects, createProject, type Project } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";

export function ProjectsModule() {
  const { tab, setProjectId, navigate } = useNavigation();
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

  const handleProjectClick = (project: Project) => {
    setProjectId(project.id);
    navigate("authoring", "upload", project.id);
  };

  // Filter by tab
  const filtered = projects.filter((p) => {
    if (tab === "active") return p.status !== "completed";
    if (tab === "completed") return p.status === "completed";
    return true;
  });

  return (
    <div>
      <div className="flex items-center justify-between" style={{ marginBottom: "var(--space-5)" }}>
        <h1 className="section-heading" style={{ marginBottom: 0 }}>投标项目</h1>
        <ClayButton onClick={() => setShowForm(!showForm)}>
          {showForm ? "取消" : "新建项目"}
        </ClayButton>
      </div>

      {showForm && (
        <Card style={{ marginBottom: "var(--space-5)" }}>
          <form className="form-row" onSubmit={handleSubmit}>
            <input
              className="clay-input"
              type="text"
              placeholder="项目名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
            <ClayButton type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "创建中..." : "创建"}
            </ClayButton>
          </form>
          {mutation.isError && (
            <p className="text-error" style={{ marginTop: "var(--space-2)" }}>
              {(mutation.error as Error).message}
            </p>
          )}
        </Card>
      )}

      {isLoading && <div className="spinner" />}
      {error && <p className="text-error">加载失败: {(error as Error).message}</p>}

      <div className="project-grid">
        {filtered.map((p) => (
          <Card
            key={p.id}
            clickable
            onClick={() => handleProjectClick(p)}
            style={{ cursor: "pointer" }}
          >
            <h2 style={{ fontSize: "var(--text-lg)", marginBottom: "var(--space-3)" }}>
              {p.name}
            </h2>
            <div className="flex items-center justify-between">
              <Badge variant={p.status === "completed" ? "success" : "primary"}>
                {p.status ?? "draft"}
              </Badge>
              <span style={{ color: "var(--color-text-muted)", fontSize: "var(--text-xs)" }}>
                {new Date(p.created_at).toLocaleDateString("zh-CN")}
              </span>
            </div>
          </Card>
        ))}
        {!isLoading && filtered.length === 0 && (
          <p className="empty-state">暂无项目，请点击"新建项目"开始</p>
        )}
      </div>
    </div>
  );
}
