import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listProjects, createProject, deleteProject, type Project } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";

export function ProjectsModule() {
  const { tab, projectId, setProjectId, setDocumentId, navigate } = useNavigation();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [projectPendingDelete, setProjectPendingDelete] = useState<Project | null>(null);

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

  const deleteMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: (_result, deletedProjectId) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      if (projectId === deletedProjectId) {
        setProjectId(null);
        setDocumentId(null);
        navigate("projects", "all", null);
      }
      setProjectPendingDelete(null);
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

  const handleProjectDelete = (event: React.MouseEvent, project: Project) => {
    event.stopPropagation();
    setProjectPendingDelete(project);
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
              aria-label="项目名称"
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
            className="project-card"
            style={{ cursor: "pointer" }}
          >
            <div className="project-card__header">
              <h2 style={{ fontSize: "var(--text-lg)", marginBottom: 0 }}>
                {p.name}
              </h2>
              <ClayButton
                type="button"
                variant="ghost"
                size="sm"
                className="project-card__delete"
                onClick={(event) => handleProjectDelete(event, p)}
                aria-label={`删除项目 ${p.name}`}
              >
                删除
              </ClayButton>
            </div>
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

      <ConfirmDialog
        open={projectPendingDelete !== null}
        title="删除项目"
        description={
          projectPendingDelete
            ? `将删除项目“${projectPendingDelete.name}”及其关联招标文件、解析结果和抽取数据，此操作不可撤销。`
            : ""
        }
        confirmLabel="确认删除"
        busy={deleteMutation.isPending}
        onCancel={() => {
          if (!deleteMutation.isPending) setProjectPendingDelete(null);
        }}
        onConfirm={() => {
          if (projectPendingDelete) deleteMutation.mutate(projectPendingDelete.id);
        }}
      />
    </div>
  );
}
