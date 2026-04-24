import { useState, useEffect } from "react";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { Icon } from "../../components/ui/Icon";
import {
  fetchAgentConfigs,
  updateAgentConfig,
  testAgentConnection,
  fetchSkillDefinitions,
  createSkillDefinition,
  updateSkillDefinition,
  deleteSkillDefinition,
  syncDefaultSkills,
  fetchUsers,
  createUser,
  updateUser,
  deleteUser,
  type AgentConfig,
  type AgentConfigUpdate,
  type SkillDefinition,
  type SkillDefinitionCreate,
  type SkillDefinitionUpdate,
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
  if (tab === "skills") {
    return <SkillsSettings />;
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
// AI Agent Settings — compact, single-page layout
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
      {loading && <p style={{ color: "var(--color-text-muted)" }}>加载中...</p>}
      {error && (
        <Card>
          <p style={{ color: "var(--color-danger)" }}>加载失败: {error}</p>
          <ClayButton onClick={() => loadConfigs()}>重试</ClayButton>
        </Card>
      )}
      <div className="agent-config-grid">
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
  const [testing, setTesting] = useState(false);
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

  const handleTest = async () => {
    setTesting(true);
    setFeedback(null);
    try {
      const result = await testAgentConnection(config.agent_key);
      setFeedback({
        type: result.success ? "success" : "error",
        msg: result.message,
      });
    } catch (e) {
      setFeedback({ type: "error", msg: (e as Error).message });
    } finally {
      setTesting(false);
      setTimeout(() => setFeedback(null), 5000);
    }
  };

  const isOcr = config.agent_type === "ocr";

  return (
    <Card>
      {/* Header */}
      <div className="flex items-center gap-2" style={{ marginBottom: "var(--space-3)" }}>
        <strong>{config.display_name}</strong>
        <Badge variant={isOcr ? "warning" : "info"}>
          {isOcr ? "OCR" : "LLM"}
        </Badge>
      </div>
      {config.description && (
        <p style={{ color: "var(--color-text-muted)", fontSize: "var(--text-xs)", marginBottom: "var(--space-3)", lineHeight: 1.3 }}>
          {config.description}
        </p>
      )}

      {/* Primary config — 2 column layout */}
      <div className="agent-form-grid">
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">Base URL</label>
          <input className="clay-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" style={{ fontSize: "var(--text-sm)" }} />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">API Key</label>
          <input className="clay-input" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={config.api_key_display || "sk-..."} style={{ fontSize: "var(--text-sm)" }} />
        </div>
        {!isOcr && (
          <div className="form-group" style={{ margin: 0 }}>
            <label className="form-label">主模型</label>
            <select className="clay-input" value={primaryModel} onChange={(e) => setPrimaryModel(e.target.value)} style={{ fontSize: "var(--text-sm)" }}>
              <option value="">-- 选择 --</option>
              {MODEL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Fallback config — collapsible for LLM agents */}
      {!isOcr && (
        <details style={{ marginTop: "var(--space-2)" }}>
          <summary style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)", cursor: "pointer", userSelect: "none" }}>
            备选模型 (Fallback)
          </summary>
          <div className="agent-form-grid" style={{ marginTop: "var(--space-2)" }}>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Fallback URL</label>
              <input className="clay-input" value={fallbackBaseUrl} onChange={(e) => setFallbackBaseUrl(e.target.value)} placeholder="https://..." style={{ fontSize: "var(--text-sm)" }} />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">Fallback Key</label>
              <input className="clay-input" type="password" value={fallbackApiKey} onChange={(e) => setFallbackApiKey(e.target.value)} placeholder={config.fallback_api_key_display || "sk-..."} style={{ fontSize: "var(--text-sm)" }} />
            </div>
            <div className="form-group" style={{ margin: 0 }}>
              <label className="form-label">备选模型</label>
              <select className="clay-input" value={fallbackModel} onChange={(e) => setFallbackModel(e.target.value)} style={{ fontSize: "var(--text-sm)" }}>
                <option value="">-- 选择 --</option>
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>
        </details>
      )}

      {/* Actions + feedback */}
      <div className="flex items-center gap-2" style={{ marginTop: "var(--space-3)" }}>
        <ClayButton onClick={handleSave} disabled={saving} size="sm">
          {saving ? "..." : "保存"}
        </ClayButton>
        <ClayButton onClick={handleTest} disabled={testing} size="sm" variant="secondary">
          {testing ? "测试中..." : "测试连接"}
        </ClayButton>
        {feedback && (
          <span style={{
            color: feedback.type === "success" ? "var(--color-success)" : "var(--color-danger)",
            fontSize: "var(--text-xs)",
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {feedback.msg}
          </span>
        )}
      </div>
    </Card>
  );
}

function SkillsSettings() {
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillDefinition | null>(null);

  const loadSkills = async (signal?: AbortSignal) => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchSkillDefinitions({ signal });
      setSkills(data);
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
    loadSkills(controller.signal);
    return () => controller.abort();
  }, []);

  const handleSync = async () => {
    try {
      setSyncing(true);
      setFeedback(null);
      const result = await syncDefaultSkills();
      await loadSkills();
      setFeedback(`已同步 ${result.total} 个 skill（新增 ${result.inserted}，更新 ${result.updated}）`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  };

  const handleCreated = (skill: SkillDefinition) => {
    setSkills((prev) => [...prev, skill].sort((a, b) => a.skill_name.localeCompare(b.skill_name)));
    setShowForm(false);
  };

  const handleUpdated = (skill: SkillDefinition) => {
    setSkills((prev) =>
      prev
        .map((item) => (item.skill_name === skill.skill_name ? skill : item))
        .sort((a, b) => a.skill_name.localeCompare(b.skill_name)),
    );
    setEditingSkill(null);
  };

  const handleDelete = async (skillName: string) => {
    if (!confirm(`确定删除 skill “${skillName}”？`)) return;
    try {
      await deleteSkillDefinition(skillName);
      setSkills((prev) => prev.filter((item) => item.skill_name !== skillName));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--space-6)", gap: "var(--space-3)", flexWrap: "wrap" }}>
        <div>
          <h1 className="section-heading" style={{ margin: 0 }}>Skills</h1>
          <p style={{ marginTop: "var(--space-2)", color: "var(--color-text-muted)", fontSize: "var(--text-sm)" }}>
            将工作流能力和 repo-local skill catalog 接入 Tender 系统，支持同步、启停与维护。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ClayButton onClick={handleSync} disabled={syncing} variant="secondary">
            {syncing ? "同步中..." : "同步默认 Skills"}
          </ClayButton>
          <ClayButton onClick={() => { setShowForm(true); setEditingSkill(null); }}>
            新增 Skill
          </ClayButton>
        </div>
      </div>

      {feedback && (
        <Card style={{ marginBottom: "var(--space-4)" }}>
          <p style={{ color: "var(--color-success)", margin: 0 }}>{feedback}</p>
        </Card>
      )}

      {loading && <p style={{ color: "var(--color-text-muted)" }}>加载中...</p>}
      {error && (
        <Card style={{ marginBottom: "var(--space-4)" }}>
          <p style={{ color: "var(--color-danger)" }}>加载失败: {error}</p>
          <ClayButton onClick={() => loadSkills()}>重试</ClayButton>
        </Card>
      )}

      {(showForm || editingSkill) && (
        <SkillDefinitionForm
          skill={editingSkill}
          onSaved={editingSkill ? handleUpdated : handleCreated}
          onCancel={() => { setShowForm(false); setEditingSkill(null); }}
        />
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
        {skills.map((skill) => (
          <Card key={skill.skill_name} style={{ maxWidth: 820 }}>
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "var(--space-3)" }}>
              <div style={{ flex: 1 }}>
                <div className="flex items-center gap-2" style={{ marginBottom: "var(--space-2)", flexWrap: "wrap" }}>
                  <strong>{skill.skill_name}</strong>
                  <Badge variant={skill.active ? "info" : "default"}>
                    {skill.active ? "已启用" : "已停用"}
                  </Badge>
                  <Badge variant="warning">v{skill.version}</Badge>
                  {skill.prompt_template_id && (
                    <Badge variant="default">Prompt 已关联</Badge>
                  )}
                </div>
                <p style={{ color: "var(--color-text-muted)", fontSize: "var(--text-sm)", marginBottom: "var(--space-3)" }}>
                  {skill.description || "暂无描述"}
                </p>
                <div style={{ fontSize: "var(--text-sm)", marginBottom: "var(--space-2)" }}>
                  <strong>工具链：</strong>
                </div>
                <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                  {skill.tool_names.length > 0 ? skill.tool_names.map((tool) => (
                    <Badge key={tool} variant="default">{tool}</Badge>
                  )) : (
                    <span style={{ color: "var(--color-text-muted)", fontSize: "var(--text-sm)" }}>未配置</span>
                  )}
                </div>
                <div style={{ marginTop: "var(--space-3)", fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
                  创建时间：{new Date(skill.created_at).toLocaleString()}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <ClayButton
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setEditingSkill(skill);
                    setShowForm(false);
                  }}
                >
                  编辑
                </ClayButton>
                <ClayButton
                  size="sm"
                  onClick={() => handleDelete(skill.skill_name)}
                >
                  删除
                </ClayButton>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}

interface SkillDefinitionFormProps {
  skill: SkillDefinition | null;
  onSaved: (skill: SkillDefinition) => void;
  onCancel: () => void;
}

function SkillDefinitionForm({ skill, onSaved, onCancel }: SkillDefinitionFormProps) {
  const isEdit = skill !== null;
  const [skillName, setSkillName] = useState(skill?.skill_name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [toolNamesText, setToolNamesText] = useState((skill?.tool_names ?? []).join(", "));
  const [promptTemplateId, setPromptTemplateId] = useState(skill?.prompt_template_id ?? "");
  const [version, setVersion] = useState(String(skill?.version ?? 1));
  const [active, setActive] = useState(skill?.active ?? true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parseToolNames = () =>
    toolNamesText
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);

  const handleSubmit = async () => {
    setSaving(true);
    setError(null);

    if (!skillName.trim()) {
      setError("请填写 skill 名称");
      setSaving(false);
      return;
    }

    const versionNumber = Number(version);
    if (!Number.isInteger(versionNumber) || versionNumber < 1) {
      setError("版本号必须是大于等于 1 的整数");
      setSaving(false);
      return;
    }

    try {
      if (isEdit) {
        const payload: SkillDefinitionUpdate = {
          description,
          tool_names: parseToolNames(),
          prompt_template_id: promptTemplateId.trim() || null,
          version: versionNumber,
          active,
        };
        const updated = await updateSkillDefinition(skill.skill_name, payload);
        onSaved(updated);
      } else {
        const payload: SkillDefinitionCreate = {
          skill_name: skillName.trim(),
          description,
          tool_names: parseToolNames(),
          prompt_template_id: promptTemplateId.trim() || null,
          version: versionNumber,
          active,
        };
        const created = await createSkillDefinition(payload);
        onSaved(created);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card style={{ maxWidth: 820, marginBottom: "var(--space-6)" }}>
      <h3 style={{ marginBottom: "var(--space-4)" }}>{isEdit ? "编辑 Skill" : "新增 Skill"}</h3>
      <div className="form-group">
        <label className="form-label">Skill 名称</label>
        <input
          className="clay-input"
          value={skillName}
          onChange={(e) => setSkillName(e.target.value)}
          disabled={isEdit}
          placeholder="generate_section"
        />
      </div>
      <div className="form-group">
        <label className="form-label">描述</label>
        <textarea
          className="clay-input"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          placeholder="说明这个 skill 负责什么工作"
        />
      </div>
      <div className="form-group">
        <label className="form-label">工具名称</label>
        <textarea
          className="clay-input"
          value={toolNamesText}
          onChange={(e) => setToolNamesText(e.target.value)}
          rows={3}
          placeholder="用逗号或换行分隔，例如：load_project_facts, llm_generate_section"
        />
      </div>
      <div className="agent-form-grid">
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">Prompt Template ID</label>
          <input
            className="clay-input"
            value={promptTemplateId}
            onChange={(e) => setPromptTemplateId(e.target.value)}
            placeholder="可选 UUID"
          />
        </div>
        <div className="form-group" style={{ margin: 0 }}>
          <label className="form-label">版本</label>
          <input
            className="clay-input"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            inputMode="numeric"
          />
        </div>
      </div>
      <div className="form-group">
        <label style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", cursor: "pointer" }}>
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          <span className="form-label" style={{ margin: 0 }}>启用 Skill</span>
        </label>
      </div>
      {error && <p style={{ color: "var(--color-danger)", fontSize: "var(--text-sm)", marginBottom: "var(--space-3)" }}>{error}</p>}
      <div className="flex items-center gap-3">
        <ClayButton onClick={handleSubmit} disabled={saving}>
          {saving ? "保存中..." : "保存"}
        </ClayButton>
        <ClayButton onClick={onCancel}>取消</ClayButton>
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
