import { useNavigation } from "../../lib/NavigationContext";
import { ReviewIssuesContent } from "./ReviewIssuesContent";
import { ComplianceContent } from "./ComplianceContent";

export function ReviewModule() {
  const { tab } = useNavigation();

  switch (tab) {
    case "issues":
      return <ReviewIssuesContent />;
    case "compliance":
      return <ComplianceContent />;
    default:
      return <ReviewIssuesContent />;
  }
}
