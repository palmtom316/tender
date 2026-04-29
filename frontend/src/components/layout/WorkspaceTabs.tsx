import { useNavigation } from "../../lib/NavigationContext";
import { getModuleConfig } from "../../lib/navigation";

export function WorkspaceTabs() {
  const { module, tab, setTab } = useNavigation();
  const config = getModuleConfig(module);

  return (
    <div className="tab-bar" role="tablist" aria-label={`${config.label} 标签页`}>
      {config.tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={tab === t.id}
          className={`tab-item ${tab === t.id ? "active" : ""}`}
          onClick={() => setTab(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
