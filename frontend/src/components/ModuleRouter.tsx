import { Suspense, lazy } from "react";

import { useNavigation } from "../lib/NavigationContext";
import { ProjectsModule } from "../modules/projects/ProjectsModule";
import { AuthoringModule } from "../modules/authoring/AuthoringModule";
import { ReviewModule } from "../modules/review/ReviewModule";
import { ExportModule } from "../modules/export/ExportModule";
import { SettingsModule } from "../modules/settings/SettingsModule";

const DatabaseModule = lazy(async () => import("../modules/database/DatabaseModule").then((module) => ({
  default: module.DatabaseModule,
})));

function ModuleLoadingFallback() {
  return (
    <div className="empty-state" style={{ padding: "var(--space-12)" }}>
      <div className="spinner" />
      <p>模块加载中...</p>
    </div>
  );
}

export function ModuleRouter() {
  const { module } = useNavigation();

  switch (module) {
    case "projects":
      return <ProjectsModule />;
    case "database":
      return (
        <Suspense fallback={<ModuleLoadingFallback />}>
          <DatabaseModule />
        </Suspense>
      );
    case "authoring":
      return <AuthoringModule />;
    case "review":
      return <ReviewModule />;
    case "export":
      return <ExportModule />;
    case "settings":
      return <SettingsModule />;
    default:
      return <ProjectsModule />;
  }
}
