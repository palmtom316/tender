import { MODULE_CONFIG, type ModuleId } from "../../lib/navigation";
import { useNavigation } from "../../lib/NavigationContext";
import { Icon } from "../ui/Icon";

export function Sidebar() {
  const { module, setModule, sidebarCollapsed, toggleSidebar } = useNavigation();

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <Icon name="sparkles" size={28} className="logo-icon" />
        <span>Tender AI</span>
      </div>

      <button
        className="sidebar-toggle"
        onClick={toggleSidebar}
        title={sidebarCollapsed ? "展开侧边栏" : "折叠侧边栏"}
      >
        <Icon name={sidebarCollapsed ? "menu" : "chevron-left"} size={18} />
      </button>

      <nav className="sidebar-nav">
        {MODULE_CONFIG.map((m) => (
          <button
            key={m.id}
            className={`sidebar-item ${module === m.id ? "active" : ""}`}
            onClick={() => setModule(m.id as ModuleId)}
            title={m.label}
          >
            <Icon name={m.icon} size={20} className="item-icon" />
            <span>{m.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-avatar">
          <span className="avatar-circle">U</span>
          <span>用户</span>
        </div>
      </div>
    </aside>
  );
}
