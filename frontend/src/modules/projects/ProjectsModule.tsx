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
  const [businessLine, setBusinessLine] = useState("10kV");
  const [employerName, setEmployerName] = useState("");
  const [tenderPlatform, setTenderPlatform] = useState("ECP");
  const [submissionDeadline, setSubmissionDeadline] = useState("");
  const [voltageLevel, setVoltageLevel] = useState("10kV");
  const [bidBondAmount, setBidBondAmount] = useState("");
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
      setEmployerName("");
      setSubmissionDeadline("");
      setBidBondAmount("");
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
      mutation.mutate({
        name: name.trim(),
        industry: "power",
        business_line: businessLine,
        project_type: businessLine,
        employer_name: employerName.trim() || undefined,
        tender_platform: tenderPlatform,
        submission_target: tenderPlatform === "线下" ? "paper" : "platform_manual_upload",
        submission_deadline: submissionDeadline || undefined,
        voltage_level: voltageLevel ? [voltageLevel] : [],
        bid_bond_amount: bidBondAmount.trim() || undefined,
        procurement_type: "single",
      });
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
      <div className="page-header">
        <h1 className="section-heading">投标项目</h1>
        <ClayButton onClick={() => setShowForm(!showForm)}>
          {showForm ? "取消" : "新建项目"}
        </ClayButton>
      </div>

      {showForm && (
        <Card className="feedback-card">
          <form className="project-create-form" onSubmit={handleSubmit}>
            <input
              className="clay-input"
              type="text"
              placeholder="项目名称"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label="项目名称"
              autoFocus
            />
            <select className="clay-input" value={businessLine} onChange={(e) => setBusinessLine(e.target.value)} aria-label="业务线">
              <option value="变电劳务及专业分包">变电劳务及专业分包</option>
              <option value="10kV">10kV 项目</option>
              <option value="电力运维">电力运维项目</option>
              <option value="用户高低压供配电">用户高低压供配电工程</option>
            </select>
            <select className="clay-input" value={voltageLevel} onChange={(e) => setVoltageLevel(e.target.value)} aria-label="电压等级">
              <option value="500kV">500kV</option>
              <option value="220kV">220kV</option>
              <option value="110kV">110kV</option>
              <option value="35kV">35kV</option>
              <option value="10kV">10kV</option>
              <option value="0.4kV">0.4kV</option>
            </select>
            <input className="clay-input" type="text" placeholder="发包人" value={employerName} onChange={(e) => setEmployerName(e.target.value)} aria-label="发包人" />
            <select className="clay-input" value={tenderPlatform} onChange={(e) => setTenderPlatform(e.target.value)} aria-label="招投标平台">
              <option value="ECP">国网 ECP</option>
              <option value="南网平台">南网平台</option>
              <option value="公共资源交易平台">公共资源交易平台</option>
              <option value="线下">线下递交</option>
            </select>
            <input className="clay-input" type="datetime-local" value={submissionDeadline} onChange={(e) => setSubmissionDeadline(e.target.value)} aria-label="递交截止时间" />
            <input className="clay-input" type="text" placeholder="保证金，如 10万元" value={bidBondAmount} onChange={(e) => setBidBondAmount(e.target.value)} aria-label="保证金" />
            <ClayButton type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "创建中..." : "创建"}
            </ClayButton>
          </form>
          {mutation.isError && (
            <p className="text-error form-message">
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
          >
            <div className="project-card__header">
              <h2 className="project-card__title">{p.name}</h2>
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
                {p.workflow_status ?? p.status ?? "created"}
              </Badge>
              <span className="project-card__date">
                {new Date(p.created_at).toLocaleDateString("zh-CN")}
              </span>
            </div>
            <div className="project-card__meta">
              {p.business_line && <span>{p.business_line}</span>}
              {p.tender_platform && <span>{p.tender_platform}</span>}
              {p.submission_deadline && <span>截止 {new Date(p.submission_deadline).toLocaleString("zh-CN")}</span>}
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
