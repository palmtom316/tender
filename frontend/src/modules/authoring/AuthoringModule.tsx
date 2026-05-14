import { useNavigation } from "../../lib/NavigationContext";
import { UploadContent } from "./UploadContent";
import { ParseContent } from "./ParseContent";
import { RequirementsContent } from "./RequirementsContent";
import { EditorContent } from "./EditorContent";
import { AuthoringWorkflowStatus } from "./AuthoringWorkflowStatus";
import { ProjectTemplateWorkbench } from "../templates/ProjectTemplateWorkbench";

export function AuthoringModule() {
  const { tab, navigate, projectId } = useNavigation();

  const status = { hasDocument: Boolean(projectId), parseStatus: projectId ? "done" as const : "idle" as const, requirementsConfirmed: false, templateStatus: "draft" };
  const chrome = (content: JSX.Element) => (
    <>
      <AuthoringWorkflowStatus status={status} activeTab={tab} onNavigate={(nextTab) => navigate("authoring", nextTab, projectId)} />
      {content}
    </>
  );

  switch (tab) {
    case "upload":
      return chrome(<UploadContent />);
    case "parse":
      return chrome(<ParseContent />);
    case "requirements":
      return chrome(<RequirementsContent />);
    case "editor":
      return chrome(<EditorContent />);
    case "template":
      return chrome(projectId ? <ProjectTemplateWorkbench projectId={projectId} /> : <div className="workflow-gate-panel" aria-label="项目模板调整"><strong>项目模板调整</strong><p>请先选择项目。</p></div>);
    default:
      return chrome(<UploadContent />);
  }
}
