import { NavigationProvider } from "./lib/NavigationContext";
import { AppShell } from "./components/layout/AppShell";

export function App() {
  return (
    <NavigationProvider>
      <AppShell />
    </NavigationProvider>
  );
}
