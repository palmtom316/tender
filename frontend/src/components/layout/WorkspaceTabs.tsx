import { useNavigation } from "../../lib/NavigationContext";
import { getModuleConfig } from "../../lib/navigation";

export function WorkspaceTabs() {
  const { module, tab, setTab } = useNavigation();
  const config = getModuleConfig(module);

  return (
    <div className="tab-bar">
      {config.tabs.map((t) => (
        <button
          key={t.id}
          className={`tab-item ${tab === t.id ? "active" : ""}`}
          onClick={() => setTab(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
