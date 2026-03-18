import { useState, useEffect } from "react";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { Icon } from "../../components/ui/Icon";
import {
  fetchAgentConfigs,
  updateAgentConfig,
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
  type AgentConfig,
  type AgentConfigUpdate,
  type SystemUser,
} from "../../lib/api";

const MODEL_OPTIONS = [
  { value: "deepseek-chat", label: "DeepSeek Chat" },
  { value: "deepseek-reasoner", label: "DeepSeek Reasoner" },
  { value: "qwen-max", label: "Qwen Max" },
  { value: "qwen-plus", label: "Qwen Plus" },
  { value: "gpt-4o", label: "GPT-4o" },
  { value: "gpt-4o-mini", label: "GPT-4o Mini" },
  { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
];

const ROLE_OPTIONS = [
  { value: "editor", label: "编辑员" },
  { value: "reviewer", label: "复核员" },
  { value: "admin", label: "管理员" },
];

export function SettingsModule() {
  const { tab } = useNavigation();

  if (tab === "users") {
    return <UserManagement />;
  }
  if (tab === "system") {
    return <SystemSettings />;
  }
  return <AISettings />;
}

// ══════════════════════════════════════════════
// User Management
// ══════════════════════════════════════════════

function UserManagement() {
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState<SystemUser | null>(null);

  const loadUsers = async (signal?: AbortSignal) => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchUsers({ signal });
      setUsers(data);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    loadUsers(controller.signal);
    return () => controller.abort();
  }, []);

  const handleCreated = (user: SystemUser) => {
    setUsers((prev) => [...prev, user]);
    setShowForm(false);
  };

  const handleUpdated = (user: SystemUser) => {
    setUsers((prev) => prev.map((u) => (u.id === user.id ? user : u)));
    setEditingUser(null);
  };

  const handleDelete = async (userId: string) => {
    if (!confirm("确定删除该用户？")) return;
    try {
      await deleteUser(userId);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
    } catch (e) {
      alert((e as Error).message);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-6)" }}>
        <h1 className="section-heading" style={{ margin: 0 }}>用户管理</h1>
        <ClayButton onClick={() => { setShowForm(true); setEditingUser(null); }}>
          <span style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
            <Icon name="plus" size={16} />
            添加用户
          </span>
        </ClayButton>
      </div>

      {loading && <p style={{ color: "var(--color-text-muted)" }}>加载中...</p>}
      {error && (
        <Card>
          <p style={{ color: "var(--color-danger)" }}>加载失败: {error}</p>
          <ClayButton onClick={() => loadUsers()}>重试</ClayButton>
        </Card>
      )}

      {(showForm || editingUser) && (
        <UserForm
          user={editingUser}
          onSaved={editingUser ? handleUpdated : handleCreated}
          onCancel={() => { setShowForm(false); setEditingUser(null); }}
        />
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        {users.map((user) => (
          <Card key={user.id} style={{ maxWidth: 680 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)" }}>
                <div className="avatar-circle" style={{ width: 36, height: 36 }}>
                  {user.display_name.charAt(0)}
                </div>
                <div>
                  <div style={{ fontWeight: 600 }}>{user.display_name}</div>
                  <div style={{ fontSize: "var(--text-sm)", color: "var(--color-text-muted)" }}>
                    @{user.username}
                  </div>
                </div>
                <Badge variant={user.role === "admin" ? "danger" : user.role === "reviewer" ? "warning" : "info"}>
                  {ROLE_OPTIONS.find((r) => r.value === user.role)?.label ?? user.role}
                </Badge>
                {!user.enabled && <Badge variant="default">已禁用</Badge>}
              </div>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <button
                  className="user-menu-item"
                  style={{ padding: "var(--space-1) var(--space-2)", width: "auto" }}
                  onClick={() => { setEditingUser(user); setShowForm(false); }}
                  title="编辑"
                >
                  <Icon name="edit" size={16} />
                </button>
                <button
                  className="user-menu-item user-menu-danger"
                  style={{ padding: "var(--space-1) var(--space-2)", width: "auto" }}
                  onClick={() => handleDelete(user.id)}
                  title="删除"
                >
                  <Icon name="trash" size={16} />
                </button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

interface UserFormProps {
  user: SystemUser | null;
  onSaved: (user: SystemUser) => void;
  onCancel: () => void;
}

function UserForm({ user, onSaved, onCancel }: UserFormProps) {
  const isEdit = user !== null;
  const [username, setUsername] = useState(user?.username ?? "");
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [role, setRole] = useState(user?.role ?? "editor");
  const [password, setPassword] = useState("");
  const [enabled, setEnabled] = useState(user?.enabled ?? true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    setSaving(true);
    try {
      if (isEdit) {
        const data: Record<string, unknown> = {};
        if (displayName !== user.display_name) data.display_name = displayName;
        if (role !== user.role) data.role = role;
        if (enabled !== user.enabled) data.enabled = enabled;
        if (password.trim()) data.password = password;
        const updated = await updateUser(user.id, data);
        onSaved(updated);
      } else {
        if (!username.trim() || !password.trim() || !displayName.trim()) {
          setError("请填写所有必填字段");
          setSaving(false);
          return;
        }
        const created = await createUser({
          username: username.trim(),
          password,
          display_name: displayName.trim(),
          role,
        });
        onSaved(created);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card style={{ maxWidth: 680, marginBottom: "var(--space-6)" }}>
      <h3 style={{ marginBottom: "var(--space-4)" }}>{isEdit ? "编辑用户" : "添加用户"}</h3>
      {!isEdit && (
        <div className="form-group">
          <label className="form-label">用户名</label>
          <input className="clay-input" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
        </div>
      )}
      <div className="form-group">
        <label className="form-label">显示名称</label>
        <input className="clay-input" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="张三" />
      </div>
      <div className="form-group">
        <label className="form-label">角色</label>
        <select className="clay-input" value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLE_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label className="form-label">{isEdit ? "新密码 (留空不修改)" : "密码"}</label>
        <input className="clay-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={isEdit ? "留空保持不变" : "请输入密码"} />
      </div>
      {isEdit && (
        <div className="form-group">
          <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span className="form-label" style={{ margin: 0 }}>启用账号</span>
          </label>
        </div>
      )}
      {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)", marginBottom: "var(--space-3)" }}>{error}</p>}
      <div className="flex items-center gap-3">
        <ClayButton onClick={handleSubmit} disabled={saving}>{saving ? "保存中..." : "保存"}</ClayButton>
        <ClayButton onClick={onCancel}>取消</ClayButton>
      </div>
    </Card>
  );
}

// ══════════════════════════════════════════════
// AI Agent Settings
// ══════════════════════════════════════════════

function AISettings() {
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadConfigs = async (signal?: AbortSignal) => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchAgentConfigs({ signal });
      setConfigs(data);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError((e as Error).message);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    loadConfigs(controller.signal);
    return () => controller.abort();
  }, []);

  const handleUpdate = (updated: AgentConfig) => {
    setConfigs((prev) =>
      prev.map((c) => (c.agent_key === updated.agent_key ? updated : c)),
    );
  };

  return (
    <div>
      <h1 className="section-heading">AI Agent 配置</h1>
      {loading && (
        <p style={{ color: "var(--color-text-muted)" }}>加载中...</p>
      )}
      {error && (
        <Card>
          <p style={{ color: "var(--color-danger)" }}>加载失败: {error}</p>
          <ClayButton onClick={() => loadConfigs()}>重试</ClayButton>
        </Card>
      )}
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}>
        {configs.map((config) => (
          <AgentConfigCard
            key={config.agent_key}
            config={config}
            onUpdate={handleUpdate}
          />
        ))}
      </div>
    </div>
  );
}

interface AgentConfigCardProps {
  config: AgentConfig;
  onUpdate: (updated: AgentConfig) => void;
}

function AgentConfigCard({ config, onUpdate }: AgentConfigCardProps) {
  const [baseUrl, setBaseUrl] = useState(config.base_url);
  const [apiKey, setApiKey] = useState("");
  const [primaryModel, setPrimaryModel] = useState(config.primary_model);
  const [fallbackBaseUrl, setFallbackBaseUrl] = useState(config.fallback_base_url);
  const [fallbackApiKey, setFallbackApiKey] = useState("");
  const [fallbackModel, setFallbackModel] = useState(config.fallback_model);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    setBaseUrl(config.base_url);
    setPrimaryModel(config.primary_model);
    setFallbackBaseUrl(config.fallback_base_url);
    setFallbackModel(config.fallback_model);
    setApiKey("");
    setFallbackApiKey("");
  }, [config]);

  const handleSave = async () => {
    setSaving(true);
    setFeedback(null);

    const data: AgentConfigUpdate = {};
    if (baseUrl !== config.base_url) data.base_url = baseUrl;
    if (apiKey.trim()) data.api_key = apiKey;
    if (primaryModel !== config.primary_model) data.primary_model = primaryModel;
    if (fallbackBaseUrl !== config.fallback_base_url) data.fallback_base_url = fallbackBaseUrl;
    if (fallbackApiKey.trim()) data.fallback_api_key = fallbackApiKey;
    if (fallbackModel !== config.fallback_model) data.fallback_model = fallbackModel;

    if (Object.keys(data).length === 0) {
      setFeedback({ type: "success", msg: "无变更" });
      setSaving(false);
      setTimeout(() => setFeedback(null), 2000);
      return;
    }

    try {
      const updated = await updateAgentConfig(config.agent_key, data);
      onUpdate(updated);
      setFeedback({ type: "success", msg: "已保存" });
    } catch (e) {
      setFeedback({ type: "error", msg: (e as Error).message });
    } finally {
      setSaving(false);
      setTimeout(() => setFeedback(null), 3000);
    }
  };

  const isOcr = config.agent_type === "ocr";

  return (
    <Card style={{ maxWidth: 680 }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-4)" }}>
        <strong style={{ fontSize: "var(--text-lg)" }}>{config.display_name}</strong>
        <Badge variant={isOcr ? "warning" : "info"}>
          {isOcr ? "OCR" : "LLM"}
        </Badge>
      </div>
      {config.description && (
        <p style={{ color: "var(--color-text-muted)", fontSize: "var(--text-sm)", marginBottom: "var(--space-4)" }}>
          {config.description}
        </p>
      )}

      <div className="form-group">
        <label className="form-label">Base URL</label>
        <input className="clay-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
      </div>
      <div className="form-group">
        <label className="form-label">API Key</label>
        <input className="clay-input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={config.api_key_display || "sk-..."} />
      </div>

      {!isOcr && (
        <>
          <div className="form-group">
            <label className="form-label">主模型</label>
            <select className="clay-input" value={primaryModel} onChange={(e) => setPrimaryModel(e.target.value)}>
              <option value="">-- 选择模型 --</option>
              {MODEL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div style={{ borderTop: "1px solid var(--color-border)", marginTop: "var(--space-4)", paddingTop: "var(--space-4)" }}>
            <p style={{ fontWeight: 600, fontSize: "var(--text-sm)", marginBottom: "var(--space-3)", color: "var(--color-text-muted)" }}>
              备选模型 (Fallback)
            </p>
            <div className="form-group">
              <label className="form-label">Fallback Base URL</label>
              <input className="clay-input" value={fallbackBaseUrl} onChange={(e) => setFallbackBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
            </div>
            <div className="form-group">
              <label className="form-label">Fallback API Key</label>
              <input className="clay-input" type="password" value={fallbackApiKey} onChange={(e) => setFallbackApiKey(e.target.value)} placeholder={config.fallback_api_key_display || "sk-..."} />
            </div>
            <div className="form-group">
              <label className="form-label">备选模型</label>
              <select className="clay-input" value={fallbackModel} onChange={(e) => setFallbackModel(e.target.value)}>
                <option value="">-- 选择模型 --</option>
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>
        </>
      )}

      <div className="flex items-center gap-3" style={{ marginTop: "var(--space-4)" }}>
        <ClayButton onClick={handleSave} disabled={saving}>
          {saving ? "保存中..." : "保存配置"}
        </ClayButton>
        {feedback && (
          <span style={{ color: feedback.type === "success" ? "var(--color-success)" : "var(--color-danger)", fontSize: "var(--text-sm)" }}>
            {feedback.msg}
          </span>
        )}
      </div>
    </Card>
  );
}

function SystemSettings() {
  return (
    <div>
      <h1 className="section-heading">系统设置</h1>
      <Card>
        <div className="empty-state" style={{ padding: "var(--space-12)" }}>
          <p style={{ color: "var(--color-text-muted)" }}>
            系统设置功能正在开发中
          </p>
        </div>
      </Card>
    </div>
  );
}
