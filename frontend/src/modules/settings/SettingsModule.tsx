import { useState, useEffect } from "react";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";
import { Badge } from "../../components/ui/Badge";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { Icon } from "../../components/ui/Icon";
import { EmptyState } from "../../components/ui/EmptyState";
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
  { value: "deepseek-v4-flash", label: "DeepSeek V4 Flash" },
  { value: "deepseek-v4-pro", label: "DeepSeek V4 Pro" },
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
  const [pendingDeleteUser, setPendingDeleteUser] = useState<SystemUser | null>(null);

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
    try {
      await deleteUser(userId);
      setUsers((prev) => prev.filter((u) => u.id !== userId));
    } catch (e) {
      alert((e as Error).message);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="section-heading">用户管理</h1>
        <ClayButton onClick={() => { setShowForm(true); setEditingUser(null); }}>
          <span className="inline-icon-label">
            <Icon name="plus" size={16} />
            添加用户
          </span>
        </ClayButton>
      </div>

      {loading && <p className="muted-copy">加载中...</p>}
      {error && (
        <Card>
          <p className="text-error">加载失败: {error}</p>
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

      <div className="card-stack">
        {users.map((user) => (
          <Card key={user.id} className="card-narrow">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="avatar-circle avatar-circle--md">
                  {user.display_name.charAt(0)}
                </div>
                <div>
                  <div className="font-semibold">{user.display_name}</div>
                  <div className="muted-copy">
                    @{user.username}
                  </div>
                </div>
                <Badge variant={user.role === "admin" ? "danger" : user.role === "reviewer" ? "warning" : "info"}>
                  {ROLE_OPTIONS.find((r) => r.value === user.role)?.label ?? user.role}
                </Badge>
                {!user.enabled && <Badge variant="default">已禁用</Badge>}
              </div>
              <div className="flex items-center gap-2">
                <ClayButton
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="clay-btn--icon"
                  onClick={() => { setEditingUser(user); setShowForm(false); }}
                  title="编辑"
                  aria-label={`编辑用户 ${user.display_name}`}
                >
                  <Icon name="edit" size={16} />
                </ClayButton>
                <ClayButton
                  type="button"
                  variant="danger"
                  size="sm"
                  className="clay-btn--icon"
                  onClick={() => setPendingDeleteUser(user)}
                  title="删除"
                  aria-label={`删除用户 ${user.display_name}`}
                >
                  <Icon name="trash" size={16} />
                </ClayButton>
              </div>
            </div>
          </Card>
        ))}
      </div>
      <ConfirmDialog
        open={pendingDeleteUser !== null}
        title="删除用户"
        description={pendingDeleteUser ? `确定删除用户“${pendingDeleteUser.display_name}”吗？` : "确定删除该用户吗？"}
        confirmLabel="确认删除"
        onCancel={() => setPendingDeleteUser(null)}
        onConfirm={() => {
          const user = pendingDeleteUser;
          if (!user) return;
          setPendingDeleteUser(null);
          void handleDelete(user.id);
        }}
      />
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
    <Card className="card-narrow settings-form-card">
      <h3 className="settings-form-card__title">{isEdit ? "编辑用户" : "添加用户"}</h3>
      {!isEdit && (
        <div className="form-group">
          <label className="form-label">用户名</label>
          <input className="clay-input" aria-label="用户名" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="username" />
        </div>
      )}
      <div className="form-group">
        <label className="form-label">显示名称</label>
        <input className="clay-input" aria-label="显示名称" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="张三" />
      </div>
      <div className="form-group">
        <label className="form-label">角色</label>
        <select className="clay-input" aria-label="角色" value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLE_OPTIONS.map((r) => (
            <option key={r.value} value={r.value}>{r.label}</option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label className="form-label">{isEdit ? "新密码 (留空不修改)" : "密码"}</label>
        <input className="clay-input" aria-label={isEdit ? "新密码" : "密码"} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={isEdit ? "留空保持不变" : "请输入密码"} />
      </div>
      {isEdit && (
        <div className="form-group">
          <label className="checkbox-row">
            <input type="checkbox" aria-label="启用账号" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <span className="form-label">启用账号</span>
          </label>
        </div>
      )}
      {error && <p className="text-error form-group--tight">{error}</p>}
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
      <div className="page-header">
        <h1 className="section-heading">AI Agent 配置</h1>
      </div>
      {loading && <p className="muted-copy">加载中...</p>}
      {error && (
        <Card className="feedback-card">
          <p className="text-error">加载失败: {error}</p>
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
    <Card className="agent-config-card">
      <div className="agent-config-card__header">
        <strong className="agent-config-card__title">{config.display_name}</strong>
        <Badge variant={isOcr ? "warning" : "info"}>
          {isOcr ? "OCR" : "LLM"}
        </Badge>
      </div>
      {config.description && (
        <p className="agent-config-card__description">
          {config.description}
        </p>
      )}

      <div className="agent-form-grid">
        <div className="form-group">
          <label className="form-label">Base URL</label>
          <input className="clay-input" aria-label={`${config.display_name} Base URL`} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.example.com/v1" />
        </div>
        <div className="form-group">
          <label className="form-label">API Key</label>
          <input className="clay-input" aria-label={`${config.display_name} API Key`} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={config.api_key_display || "sk-..."} />
        </div>
        {!isOcr && (
          <div className="form-group">
            <label className="form-label">主模型</label>
            <select className="clay-input" aria-label={`${config.display_name} 主模型`} value={primaryModel} onChange={(e) => setPrimaryModel(e.target.value)}>
              <option value="">-- 选择 --</option>
              {MODEL_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {!isOcr && (
        <details className="agent-fallback">
          <summary className="agent-fallback__summary">
            备选模型 (Fallback)
          </summary>
          <div className="agent-form-grid agent-form-grid--spaced">
            <div className="form-group">
              <label className="form-label">Fallback URL</label>
              <input className="clay-input" aria-label={`${config.display_name} Fallback URL`} value={fallbackBaseUrl} onChange={(e) => setFallbackBaseUrl(e.target.value)} placeholder="https://..." />
            </div>
            <div className="form-group">
              <label className="form-label">Fallback Key</label>
              <input className="clay-input" aria-label={`${config.display_name} Fallback Key`} type="password" value={fallbackApiKey} onChange={(e) => setFallbackApiKey(e.target.value)} placeholder={config.fallback_api_key_display || "sk-..."} />
            </div>
            <div className="form-group">
              <label className="form-label">备选模型</label>
              <select className="clay-input" aria-label={`${config.display_name} 备选模型`} value={fallbackModel} onChange={(e) => setFallbackModel(e.target.value)}>
                <option value="">-- 选择 --</option>
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
          </div>
        </details>
      )}

      <div className="agent-config-card__actions">
        <ClayButton onClick={handleSave} disabled={saving} size="sm">
          {saving ? "..." : "保存"}
        </ClayButton>
        <ClayButton onClick={handleTest} disabled={testing} size="sm" variant="secondary">
          {testing ? "测试中..." : "测试连接"}
        </ClayButton>
        {feedback && (
          <span className={`agent-config-card__feedback agent-config-card__feedback--${feedback.type}`}>
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
  const [pendingDeleteSkillName, setPendingDeleteSkillName] = useState<string | null>(null);

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
    try {
      await deleteSkillDefinition(skillName);
      setSkills((prev) => prev.filter((item) => item.skill_name !== skillName));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div>
      <div className="page-header">
        <div className="page-header__copy">
          <h1 className="section-heading">Skills</h1>
          <p className="page-header__description">
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
        <Card className="feedback-card">
          <p className="success-message">{feedback}</p>
        </Card>
      )}

      {loading && <p className="muted-copy">加载中...</p>}
      {error && (
        <Card className="feedback-card">
          <p className="text-error">加载失败: {error}</p>
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

      <div className="card-stack">
        {skills.map((skill) => (
          <Card key={skill.skill_name} className="card-wide">
            <div className="skill-card">
              <div className="skill-card__body">
                <div className="skill-card__header">
                  <strong>{skill.skill_name}</strong>
                  <Badge variant={skill.active ? "info" : "default"}>
                    {skill.active ? "已启用" : "已停用"}
                  </Badge>
                  <Badge variant="warning">v{skill.version}</Badge>
                  {skill.prompt_template_id && (
                    <Badge variant="default">Prompt 已关联</Badge>
                  )}
                </div>
                <p className="muted-copy skill-card__description">
                  {skill.description || "暂无描述"}
                </p>
                <div className="skill-card__tools-title">工具链：</div>
                <div className="skill-card__tool-list">
                  {skill.tool_names.length > 0 ? skill.tool_names.map((tool) => (
                    <Badge key={tool} variant="default">{tool}</Badge>
                  )) : (
                    <span className="muted-copy">未配置</span>
                  )}
                </div>
                <div className="muted-copy muted-copy--xs skill-card__timestamp">
                  创建时间：{new Date(skill.created_at).toLocaleString()}
                </div>
              </div>
              <div className="skill-card__actions">
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
                  onClick={() => setPendingDeleteSkillName(skill.skill_name)}
                >
                  删除
                </ClayButton>
              </div>
            </div>
          </Card>
        ))}
      </div>
      <ConfirmDialog
        open={pendingDeleteSkillName !== null}
        title="删除 Skill"
        description={pendingDeleteSkillName ? `确定删除 skill “${pendingDeleteSkillName}”吗？` : "确定删除该 skill 吗？"}
        confirmLabel="确认删除"
        onCancel={() => setPendingDeleteSkillName(null)}
        onConfirm={() => {
          const skillName = pendingDeleteSkillName;
          if (!skillName) return;
          setPendingDeleteSkillName(null);
          void handleDelete(skillName);
        }}
      />
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
    <Card className="card-wide settings-form-card">
      <h3 className="settings-form-card__title">{isEdit ? "编辑 Skill" : "新增 Skill"}</h3>
      <div className="form-group">
        <label className="form-label">Skill 名称</label>
          <input
            className="clay-input"
            aria-label="Skill 名称"
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
            aria-label="Skill 描述"
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
            aria-label="工具名称"
            value={toolNamesText}
          onChange={(e) => setToolNamesText(e.target.value)}
          rows={3}
          placeholder="用逗号或换行分隔，例如：load_project_facts, llm_generate_section"
        />
      </div>
      <div className="agent-form-grid">
        <div className="form-group">
          <label className="form-label">Prompt Template ID</label>
          <input
            className="clay-input"
            aria-label="Prompt Template ID"
            value={promptTemplateId}
            onChange={(e) => setPromptTemplateId(e.target.value)}
            placeholder="可选 UUID"
          />
        </div>
        <div className="form-group">
          <label className="form-label">版本</label>
          <input
            className="clay-input"
            aria-label="版本"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            inputMode="numeric"
          />
        </div>
      </div>
      <div className="form-group">
        <label className="checkbox-row">
          <input type="checkbox" aria-label="启用 Skill" checked={active} onChange={(e) => setActive(e.target.checked)} />
          <span className="form-label">启用 Skill</span>
        </label>
      </div>
      {error && <p className="text-error form-group--tight">{error}</p>}
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
        <EmptyState
          icon="设"
          title="系统设置功能正在开发中"
          description="后续会在这里集中管理系统级配置。"
          spacious
        />
      </Card>
    </div>
  );
}
