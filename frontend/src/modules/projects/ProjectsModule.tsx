import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listProjects,
  createProject,
  deleteProject,
  listTemplatePackages,
  confirmTemplateSelection,
  type Project,
} from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { EmptyState } from "../../components/ui/EmptyState";

const PROJECT_CATEGORIES = [
  { value: "sgcc_substation", label: "国网变电工程" },
  { value: "sgcc_maintenance", label: "国网运维工程" },
  { value: "sgcc_distribution", label: "国网配网工程" },
  { value: "sgcc_low_voltage_distribution", label: "国网低压营配工程" },
  { value: "user_distribution", label: "用户配电工程" },
  { value: "user_maintenance", label: "用户运维工程" },
] as const;

function formatProjectDate(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}/${month}/${day}`;
}

export function ProjectsModule() {
  const { tab, projectId, setProjectId, setDocumentId, navigate } = useNavigation();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [categoryCode, setCategoryCode] = useState<string>("sgcc_distribution");
  const [employerName, setEmployerName] = useState("");
  const [tenderPlatform, setTenderPlatform] = useState("ECP");
  const [submissionDeadline, setSubmissionDeadline] = useState("");
  const [voltageLevel, setVoltageLevel] = useState("10kV");
  const [projectPendingDelete, setProjectPendingDelete] = useState<Project | null>(null);
  const [selectedTemplatePackageId, setSelectedTemplatePackageId] = useState<string | null>(null);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);

  const { data: projects = [], isLoading, error } = useQuery({
    queryKey: ["projects"],
    queryFn: listProjects,
  });

  const {
    data: templatePackages = [],
    isLoading: isLoadingTemplatePackages,
    error: templatePackagesError,
  } = useQuery({
    queryKey: ["template-packages", categoryCode],
    queryFn: () => listTemplatePackages({ categoryCode }),
  });

  useEffect(() => {
    if (templatePackages.length === 0) {
      if (selectedTemplatePackageId !== null) setSelectedTemplatePackageId(null);
      return;
    }
    const stillValid = selectedTemplatePackageId
      ? templatePackages.some((pkg) => pkg.id === selectedTemplatePackageId)
      : false;
    if (!stillValid) {
      setSelectedTemplatePackageId(templatePackages[0].id);
    }
  }, [templatePackages, selectedTemplatePackageId]);

  useEffect(() => {
    setShowTemplatePicker(false);
  }, [categoryCode]);

  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: async (project) => {
      if (selectedTemplatePackageId) {
        await confirmTemplateSelection(project.id, selectedTemplatePackageId);
      }
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({ queryKey: ["template-packages"] });
      setName("");
      setEmployerName("");
      setSubmissionDeadline("");
      setSelectedTemplatePackageId(null);
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
    if (!name.trim()) return;
    if (templatePackages.length === 0) return;
    mutation.mutate({
      name: name.trim(),
      category_code: categoryCode,
      industry: "power",
      business_line: categoryCode,
      project_type: categoryCode,
      sub_type: categoryCode,
      employer_name: employerName.trim() || undefined,
      tender_platform: tenderPlatform,
      submission_target: tenderPlatform === "线下" ? "paper" : "platform_manual_upload",
      submission_deadline: submissionDeadline || undefined,
      voltage_level: voltageLevel ? [voltageLevel] : [],
      procurement_type: "single",
    });
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
            <select className="clay-input" value={categoryCode} onChange={(e) => setCategoryCode(e.target.value)} aria-label="项目类别">
              {PROJECT_CATEGORIES.map((kind) => (
                <option key={kind.value} value={kind.value}>{kind.label}</option>
              ))}
            </select>
            <div className="project-template-picker" aria-label="模板包">
              {isLoadingTemplatePackages && <p className="project-template-picker__empty">模板加载中...</p>}
              {templatePackagesError && (
                <p className="text-error project-template-picker__empty">
                  模板加载失败: {(templatePackagesError as Error).message}
                </p>
              )}
              {!isLoadingTemplatePackages && !templatePackagesError && templatePackages.length === 0 && (
                <p className="project-template-picker__empty">该类别暂无可用模板</p>
              )}
              {!isLoadingTemplatePackages && !templatePackagesError && templatePackages.length === 1 && (
                <p className="project-template-picker__empty">
                  将使用模板: <strong>{templatePackages[0].display_name}</strong>
                </p>
              )}
              {!isLoadingTemplatePackages && !templatePackagesError && templatePackages.length > 1 && (
                <>
                  <div className="project-template-picker__header">
                    <strong>
                      该类别有 {templatePackages.length} 个可用模板
                      {selectedTemplatePackageId &&
                        `，当前: ${templatePackages.find((pkg) => pkg.id === selectedTemplatePackageId)?.display_name ?? ""}`}
                    </strong>
                    <ClayButton
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setShowTemplatePicker((prev) => !prev)}
                      aria-expanded={showTemplatePicker}
                    >
                      {showTemplatePicker ? "收起" : "更换模板"}
                    </ClayButton>
                  </div>
                  {showTemplatePicker && (
                    <div className="project-template-picker__options">
                      {templatePackages.map((pkg) => {
                        const checked = selectedTemplatePackageId === pkg.id;
                        return (
                          <label
                            key={pkg.id}
                            className={`project-template-picker__option${checked ? " is-selected" : ""}`}
                          >
                            <input
                              type="radio"
                              name="selected_template_package"
                              value={pkg.id}
                              checked={checked}
                              onChange={() => setSelectedTemplatePackageId(pkg.id)}
                              aria-label={`选择模板包 ${pkg.display_name}`}
                            />
                            <span className="project-template-picker__option-main">
                              <span>{pkg.display_name}</span>
                              <span className="project-template-picker__meta">
                                {pkg.package_type} · {pkg.item_count} 项
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
            </div>
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
            <ClayButton type="submit" disabled={mutation.isPending || templatePackages.length === 0}>
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
                {formatProjectDate(p.created_at)}
              </span>
            </div>
            <div className="project-card__meta">
              {p.business_line && <span>{p.business_line}</span>}
              {p.tender_platform && <span>{p.tender_platform}</span>}
              {p.submission_deadline && <span>截止 {formatProjectDate(p.submission_deadline)}</span>}
            </div>
            <div className="project-card__meta">
              <span>{p.selected_template_package_id ? "已选模板" : "未选模板"}</span>
            </div>
          </Card>
        ))}
        {!isLoading && filtered.length === 0 && (
          <EmptyState
            icon="项"
            title="暂无项目"
            description="点击新建项目后，可上传招标文件并启动解析。"
            action={<ClayButton type="button" onClick={() => setShowForm(true)}>新建项目</ClayButton>}
          />
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
