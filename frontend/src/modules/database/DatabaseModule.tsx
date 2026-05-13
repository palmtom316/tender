import { Card } from "../../components/ui/Card";
import { useNavigation } from "../../lib/NavigationContext";
import { CompanyLibraryWorkbench } from "./components/CompanyLibraryWorkbench";
import { CompanybaseImportWorkbench } from "./components/CompanybaseImportWorkbench";
import { PersonnelLibraryWorkbench } from "./components/PersonnelLibraryWorkbench";
import { StandardsWorkbench } from "./components/StandardsWorkbench";
import { TemplateFieldWorkbench } from "./components/TemplateFieldWorkbench";

const TAB_DESCRIPTIONS: Record<string, string> = {
  templates: "配置投标文件模版、字段映射和渲染上下文",
  company: "公司资质证书、业绩证明等企业资料",
  personnel: "项目团队成员简历、资质证书等",
  companybase: "Excel 资料包导入、校验和备份",
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
        <h1 className="section-heading">投标文件模版</h1>
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

  if (tab === "companybase") {
    return (
      <div>
        <h1 className="section-heading">资料包导入/备份</h1>
        <CompanybaseImportWorkbench />
      </div>
    );
  }

  return (
    <div>
      <h1 className="section-heading">投标资料库</h1>
      <Card>
        <div className="empty-state empty-state--spacious">
          <span className="empty-state__icon">库</span>
          <p className="empty-state__title">
            {TAB_DESCRIPTIONS[tab] ?? "资料库"}
          </p>
          <p className="empty-state__description">
            后续这里会沉淀可复用的投标资料。当前可先使用规范、模板、公司和人员资料库。
          </p>
        </div>
      </Card>
    </div>
  );
}
