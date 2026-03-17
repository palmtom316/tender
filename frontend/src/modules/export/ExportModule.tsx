import { useNavigation } from "../../lib/NavigationContext";
import { ExportGateContent } from "./ExportGateContent";
import { ExportHistoryContent } from "./ExportHistoryContent";

export function ExportModule() {
  const { tab } = useNavigation();

  switch (tab) {
    case "gate":
      return <ExportGateContent />;
    case "history":
      return <ExportHistoryContent />;
    default:
      return <ExportGateContent />;
  }
}
