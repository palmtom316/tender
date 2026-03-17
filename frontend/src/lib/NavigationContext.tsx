import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from "react";
import { type ModuleId, MODULE_CONFIG } from "./navigation";

interface NavigationState {
  module: ModuleId;
  tab: string;
  projectId: string | null;
  documentId: string | null;
  sidebarCollapsed: boolean;
}

interface NavigationContextValue extends NavigationState {
  setModule: (module: ModuleId) => void;
  setTab: (tab: string) => void;
  setProjectId: (id: string | null) => void;
  setDocumentId: (id: string | null) => void;
  toggleSidebar: () => void;
  navigate: (module: ModuleId, tab?: string, projectId?: string | null) => void;
}

const NavigationContext = createContext<NavigationContextValue | null>(null);

/** Parse current URL into navigation state. */
function parseUrl(): Partial<NavigationState> {
  const params = new URLSearchParams(window.location.search);
  const module = params.get("m") as ModuleId | null;
  const tab = params.get("t");
  const projectId = params.get("p");
  const documentId = params.get("d");

  // Validate module
  const validModule =
    module && MODULE_CONFIG.some((m) => m.id === module) ? module : "projects";

  // Validate tab against module
  const cfg = MODULE_CONFIG.find((m) => m.id === validModule);
  const validTab =
    tab && cfg?.tabs.some((t) => t.id === tab) ? tab : cfg?.tabs[0]?.id ?? "";

  return {
    module: validModule,
    tab: validTab,
    projectId: projectId || null,
    documentId: documentId || null,
  };
}

/** Build URL search string from state. */
function buildUrl(state: NavigationState): string {
  const params = new URLSearchParams();
  params.set("m", state.module);
  params.set("t", state.tab);
  if (state.projectId) params.set("p", state.projectId);
  if (state.documentId) params.set("d", state.documentId);
  return `?${params.toString()}`;
}

export function NavigationProvider({ children }: { children: ReactNode }) {
  const initial = parseUrl();
  const [module, setModuleRaw] = useState<ModuleId>(initial.module ?? "projects");
  const [tab, setTabRaw] = useState(initial.tab ?? "all");
  const [projectId, setProjectId] = useState<string | null>(initial.projectId ?? null);
  const [documentId, setDocumentId] = useState<string | null>(initial.documentId ?? null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Sync state → URL
  useEffect(() => {
    const state: NavigationState = {
      module,
      tab,
      projectId,
      documentId,
      sidebarCollapsed,
    };
    const url = buildUrl(state);
    if (window.location.search !== url) {
      window.history.pushState(null, "", url);
    }
  }, [module, tab, projectId, documentId, sidebarCollapsed]);

  // Listen for browser back/forward
  useEffect(() => {
    const onPop = () => {
      const parsed = parseUrl();
      if (parsed.module) setModuleRaw(parsed.module);
      if (parsed.tab) setTabRaw(parsed.tab);
      setProjectId(parsed.projectId ?? null);
      setDocumentId(parsed.documentId ?? null);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const setModule = useCallback(
    (m: ModuleId) => {
      setModuleRaw(m);
      // Reset to first tab of new module
      const cfg = MODULE_CONFIG.find((c) => c.id === m);
      setTabRaw(cfg?.tabs[0]?.id ?? "");
    },
    [],
  );

  const setTab = useCallback((t: string) => {
    setTabRaw(t);
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((v) => !v);
  }, []);

  const navigate = useCallback(
    (m: ModuleId, t?: string, pid?: string | null) => {
      setModuleRaw(m);
      const cfg = MODULE_CONFIG.find((c) => c.id === m);
      setTabRaw(t ?? cfg?.tabs[0]?.id ?? "");
      if (pid !== undefined) setProjectId(pid);
    },
    [],
  );

  return (
    <NavigationContext.Provider
      value={{
        module,
        tab,
        projectId,
        documentId,
        sidebarCollapsed,
        setModule,
        setTab,
        setProjectId,
        setDocumentId,
        toggleSidebar,
        navigate,
      }}
    >
      {children}
    </NavigationContext.Provider>
  );
}

export function useNavigation(): NavigationContextValue {
  const ctx = useContext(NavigationContext);
  if (!ctx) throw new Error("useNavigation must be inside NavigationProvider");
  return ctx;
}
