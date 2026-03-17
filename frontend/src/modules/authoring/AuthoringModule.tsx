import { useNavigation } from "../../lib/NavigationContext";
import { UploadContent } from "./UploadContent";
import { ParseContent } from "./ParseContent";
import { RequirementsContent } from "./RequirementsContent";
import { EditorContent } from "./EditorContent";

export function AuthoringModule() {
  const { tab } = useNavigation();

  switch (tab) {
    case "upload":
      return <UploadContent />;
    case "parse":
      return <ParseContent />;
    case "requirements":
      return <RequirementsContent />;
    case "editor":
      return <EditorContent />;
    default:
      return <UploadContent />;
  }
}
