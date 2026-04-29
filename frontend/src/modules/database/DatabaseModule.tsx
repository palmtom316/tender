import { Card } from "../../components/ui/Card";
import { useNavigation } from "../../lib/NavigationContext";
import { CompanyLibraryWorkbench } from "./components/CompanyLibraryWorkbench";
import { PersonnelLibraryWorkbench } from "./components/PersonnelLibraryWorkbench";
import { StandardsWorkbench } from "./components/StandardsWorkbench";
import { TemplateFieldWorkbench } from "./components/TemplateFieldWorkbench";

const TAB_DESCRIPTIONS: Record<string, string> = {
  history: "管理历史投标文件，支持按项目类型和时间筛选",
  excellent: "收集和标注优秀投标文件，供编制参考",
  templates: "配置模板包、模板项字段映射和渲染上下文",
  company: "公司资质证书、业绩证明等企业资料",
  personnel: "项目团队成员简历、资质证书等",
};

export function DatabaseModule() {
  const { tab } = useNavigation();

  if (tab === "standards") {
    return (
      <div>
        <h1 className="section-heading">规范规程库</h1>
        <StandardsWorkbench />
      </div>
    );
  }

  if (tab === "templates") {
    return (
      <div>
        <h1 className="section-heading">模板包字段面板</h1>
        <TemplateFieldWorkbench />
      </div>
    );
  }

  if (tab === "company") {
    return (
      <div>
        <h1 className="section-heading">公司资料库</h1>
        <CompanyLibraryWorkbench />
      </div>
    );
  }

  if (tab === "personnel") {
    return (
      <div>
        <h1 className="section-heading">人员资料库</h1>
        <PersonnelLibraryWorkbench />
      </div>
    );
  }

  return (
    <div>
      <h1 className="section-heading">投标资料库</h1>
      <Card>
        <div className="empty-state" style={{ padding: "var(--space-12)" }}>
          <p style={{ fontSize: "var(--text-lg)", marginBottom: "var(--space-2)", color: "var(--color-text)" }}>
            {TAB_DESCRIPTIONS[tab] ?? "资料库"}
          </p>
          <p style={{ color: "var(--color-text-muted)" }}>
            此模块正在开发中，敬请期待
          </p>
        </div>
      </Card>
    </div>
  );
}
