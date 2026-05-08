import { ErrorBoundary } from "./components/ErrorBoundary";
import { NavigationProvider } from "./lib/NavigationContext";
import { ThemeProvider } from "./lib/ThemeContext";
import { AppShell } from "./components/layout/AppShell";

export function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <NavigationProvider>
          <AppShell />
        </NavigationProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
