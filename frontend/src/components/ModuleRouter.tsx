import { useNavigation } from "../lib/NavigationContext";
import { ProjectsModule } from "../modules/projects/ProjectsModule";
import { DatabaseModule } from "../modules/database/DatabaseModule";
import { AuthoringModule } from "../modules/authoring/AuthoringModule";
import { ReviewModule } from "../modules/review/ReviewModule";
import { ExportModule } from "../modules/export/ExportModule";
import { SettingsModule } from "../modules/settings/SettingsModule";

export function ModuleRouter() {
  const { module } = useNavigation();

  switch (module) {
    case "projects":
      return <ProjectsModule />;
    case "database":
      return <DatabaseModule />;
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
