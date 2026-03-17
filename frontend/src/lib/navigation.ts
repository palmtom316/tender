/**
 * Navigation type definitions and module configuration.
 */

export type ModuleId =
  | "projects"
  | "database"
  | "authoring"
  | "review"
  | "export"
  | "settings";

export interface TabDef {
  id: string;
  label: string;
}

export interface ModuleConfig {
  id: ModuleId;
  label: string;
  icon: string; // icon name for Icon component
  tabs: TabDef[];
}

export const MODULE_CONFIG: ModuleConfig[] = [
  {
    id: "projects",
    label: "投标项目",
    icon: "folder",
    tabs: [
      { id: "all", label: "全部项目" },
      { id: "active", label: "进行中" },
      { id: "completed", label: "已完成" },
    ],
  },
  {
    id: "database",
    label: "投标资料库",
    icon: "database",
    tabs: [
      { id: "history", label: "历史投标文件" },
      { id: "excellent", label: "优秀投标文件" },
      { id: "standards", label: "规范规程" },
      { id: "company", label: "公司资料" },
      { id: "personnel", label: "人员资料" },
    ],
  },
  {
    id: "authoring",
    label: "智能编制",
    icon: "edit",
    tabs: [
      { id: "upload", label: "文件上传" },
      { id: "parse", label: "解析结果" },
      { id: "requirements", label: "需求确认" },
      { id: "editor", label: "章节编辑" },
    ],
  },
  {
    id: "review",
    label: "审查中心",
    icon: "check-circle",
    tabs: [
      { id: "issues", label: "审查问题" },
      { id: "compliance", label: "合规矩阵" },
    ],
  },
  {
    id: "export",
    label: "导出中心",
    icon: "download",
    tabs: [
      { id: "gate", label: "导出检查" },
      { id: "history", label: "导出历史" },
    ],
  },
  {
    id: "settings",
    label: "设置",
    icon: "settings",
    tabs: [
      { id: "ai", label: "AI模型配置" },
      { id: "system", label: "系统设置" },
    ],
  },
];

/** Look up a module config by ID. */
export function getModuleConfig(id: ModuleId): ModuleConfig {
  return MODULE_CONFIG.find((m) => m.id === id)!;
}
