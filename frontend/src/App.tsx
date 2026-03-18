import { ErrorBoundary } from "./components/ErrorBoundary";
import { NavigationProvider } from "./lib/NavigationContext";
import { AppShell } from "./components/layout/AppShell";

export function App() {
  return (
    <ErrorBoundary>
      <NavigationProvider>
        <AppShell />
      </NavigationProvider>
    </ErrorBoundary>
  );
}
