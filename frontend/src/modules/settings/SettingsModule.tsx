import { useState } from "react";
import { useNavigation } from "../../lib/NavigationContext";
import { Card } from "../../components/ui/Card";
import { ClayButton } from "../../components/ui/ClayButton";

export function SettingsModule() {
  const { tab } = useNavigation();

  if (tab === "system") {
    return <SystemSettings />;
  }
  return <AISettings />;
}

function AISettings() {
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("gpt-4o");
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    if (apiKey.trim()) {
      localStorage.setItem("tender_ai_key", apiKey);
      localStorage.setItem("tender_ai_model", model);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    }
  };

  return (
    <div>
      <h1 className="section-heading">AI模型配置</h1>
      <Card style={{ maxWidth: 560 }}>
        <div className="form-group">
          <label className="form-label">API 密钥</label>
          <input
            className="clay-input"
            type="password"
            placeholder="sk-..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </div>
        <div className="form-group">
          <label className="form-label">模型选择</label>
          <select
            className="clay-input"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="gpt-4o">GPT-4o</option>
            <option value="gpt-4o-mini">GPT-4o Mini</option>
            <option value="claude-sonnet-4-20250514">Claude Sonnet 4</option>
            <option value="deepseek-chat">DeepSeek Chat</option>
          </select>
        </div>
        <div className="flex items-center gap-3">
          <ClayButton onClick={handleSave}>保存配置</ClayButton>
          {saved && (
            <span style={{ color: "var(--color-success)", fontSize: "var(--text-sm)" }}>
              已保存
            </span>
          )}
        </div>
      </Card>
    </div>
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
