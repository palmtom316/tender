import { useNavigation } from "../../lib/NavigationContext";
import { UploadContent } from "./UploadContent";
import { ParseContent } from "./ParseContent";
import { RequirementsContent } from "./RequirementsContent";
import { EditorContent } from "./EditorContent";
import { AuthoringWorkflowStatus } from "./AuthoringWorkflowStatus";

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
      return chrome(<div className="workflow-gate-panel" aria-label="项目模板调整"><strong>项目模板调整</strong><p>项目模板实例将在下一步接入三栏表单化工作台。</p></div>);
    default:
      return chrome(<UploadContent />);
  }
}
