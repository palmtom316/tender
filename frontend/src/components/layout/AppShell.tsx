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
      <a className="skip-link" href="#main-content">跳到主要内容</a>
      <Sidebar />
      <div className="workspace">
        <NotificationMarquee />
        <WorkspaceTabs />
        <main id="main-content" className="workspace-content" tabIndex={-1}>
          <ModuleRouter />
        </main>
      </div>
      <CopilotPanel />
    </div>
  );
}
