import { useState, useEffect, useRef } from "react";
import { MODULE_CONFIG, type ModuleId } from "../../lib/navigation";
import { useNavigation } from "../../lib/NavigationContext";
import { Icon } from "../ui/Icon";
import { fetchMe, logout, type MeResponse } from "../../lib/api";

export function Sidebar() {
  const { module, setModule, sidebarCollapsed, toggleSidebar, navigate } = useNavigation();
  const [showMenu, setShowMenu] = useState(false);
  const [currentUser, setCurrentUser] = useState<MeResponse | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchMe({ signal: controller.signal })
      .then(setCurrentUser)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    if (!showMenu) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMenu]);

  const handleLogout = async () => {
    try {
      await logout();
    } catch {
      // ignore
    }
    setCurrentUser(null);
    setShowMenu(false);
    window.location.reload();
  };

  const handleUserManage = () => {
    setShowMenu(false);
    navigate("settings", "users");
  };

  const displayName = currentUser?.display_name ?? "用户";
  const initial = displayName.charAt(0).toUpperCase();

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

      <div className="sidebar-footer" ref={menuRef}>
        <button
          className="sidebar-avatar"
          onClick={() => setShowMenu((v) => !v)}
          title={displayName}
          style={{ border: "none", background: "transparent", cursor: "pointer", width: "100%" }}
        >
          <span className="avatar-circle">{initial}</span>
          <span>{displayName}</span>
        </button>

        {showMenu && (
          <div className="sidebar-user-menu">
            <div className="user-menu-header">
              <strong>{displayName}</strong>
              <span className="user-menu-role">{currentUser?.role ?? ""}</span>
            </div>
            <div className="user-menu-divider" />
            <button className="user-menu-item" onClick={handleUserManage}>
              <Icon name="users" size={16} />
              <span>用户管理</span>
            </button>
            <button className="user-menu-item user-menu-danger" onClick={handleLogout}>
              <Icon name="log-out" size={16} />
              <span>退出登录</span>
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
