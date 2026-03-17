import { useNavigation } from "../../lib/NavigationContext";
import { Sidebar } from "./Sidebar";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { NotificationMarquee } from "./NotificationMarquee";
import { CopilotPanel } from "./CopilotPanel";
import { ModuleRouter } from "../ModuleRouter";

export function AppShell() {
  const { sidebarCollapsed } = useNavigation();

  return (
    <div className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <Sidebar />
      <div className="workspace">
        <NotificationMarquee />
        <WorkspaceTabs />
        <div className="workspace-content">
          <ModuleRouter />
        </div>
      </div>
      <CopilotPanel />
    </div>
  );
}
