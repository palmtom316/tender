import { Suspense, lazy } from "react";

import { useNavigation } from "../lib/NavigationContext";

const ProjectsModule = lazy(async () => import("../modules/projects/ProjectsModule").then((module) => ({
  default: module.ProjectsModule,
})));

const AuthoringModule = lazy(async () => import("../modules/authoring/AuthoringModule").then((module) => ({
  default: module.AuthoringModule,
})));

const ReviewModule = lazy(async () => import("../modules/review/ReviewModule").then((module) => ({
  default: module.ReviewModule,
})));

const ExportModule = lazy(async () => import("../modules/export/ExportModule").then((module) => ({
  default: module.ExportModule,
})));

const SettingsModule = lazy(async () => import("../modules/settings/SettingsModule").then((module) => ({
  default: module.SettingsModule,
})));

const DatabaseModule = lazy(async () => import("../modules/database/DatabaseModule").then((module) => ({
  default: module.DatabaseModule,
})));

function ModuleLoadingFallback() {
  return (
    <div className="skeleton-stack" aria-label="模块加载中">
      <div className="skeleton-card" />
      <div className="skeleton-line" />
      <div className="skeleton-line" />
    </div>
  );
}

export function ModuleRouter() {
  const { module } = useNavigation();
  let ActiveModule = ProjectsModule;

  switch (module) {
    case "projects":
      ActiveModule = ProjectsModule;
      break;
    case "database":
      ActiveModule = DatabaseModule;
      break;
    case "authoring":
      ActiveModule = AuthoringModule;
      break;
    case "review":
      ActiveModule = ReviewModule;
      break;
    case "export":
      ActiveModule = ExportModule;
      break;
    case "settings":
      ActiveModule = SettingsModule;
      break;
    default:
      ActiveModule = ProjectsModule;
  }

  return (
    <Suspense fallback={<ModuleLoadingFallback />}>
      <ActiveModule />
    </Suspense>
  );
}
