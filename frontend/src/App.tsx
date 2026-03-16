import { ProjectListPage } from "./pages/project-list";
import { UploadPage } from "./pages/upload";
import { ParseResultsPage } from "./pages/parse-results";
import { RequirementsConfirmationPage } from "./pages/requirements-confirmation";
import { ChapterEditorPage } from "./pages/chapter-editor";
import { ReviewResultsPage } from "./pages/review-results";
import { ExportPage } from "./pages/export";

function getRoute(): { page: string; projectId?: string; documentId?: string } {
  const path = window.location.pathname;

  const exportMatch = path.match(/^\/projects\/([^/]+)\/export$/);
  if (exportMatch) return { page: "export", projectId: exportMatch[1] };

  const reviewMatch = path.match(/^\/projects\/([^/]+)\/review$/);
  if (reviewMatch) return { page: "review", projectId: reviewMatch[1] };

  const editorMatch = path.match(/^\/projects\/([^/]+)\/editor$/);
  if (editorMatch) return { page: "editor", projectId: editorMatch[1] };

  const reqMatch = path.match(/^\/projects\/([^/]+)\/requirements$/);
  if (reqMatch) return { page: "requirements", projectId: reqMatch[1] };

  const parseMatch = path.match(/^\/projects\/([^/]+)\/documents\/([^/]+)\/parse$/);
  if (parseMatch) return { page: "parse", projectId: parseMatch[1], documentId: parseMatch[2] };

  const uploadMatch = path.match(/^\/projects\/([^/]+)\/upload$/);
  if (uploadMatch) return { page: "upload", projectId: uploadMatch[1] };

  return { page: "list" };
}

export function App() {
  const route = getRoute();

  if (route.page === "export" && route.projectId) {
    return <ExportPage projectId={route.projectId} />;
  }

  if (route.page === "review" && route.projectId) {
    return <ReviewResultsPage projectId={route.projectId} />;
  }

  if (route.page === "editor" && route.projectId) {
    return <ChapterEditorPage projectId={route.projectId} />;
  }

  if (route.page === "requirements" && route.projectId) {
    return <RequirementsConfirmationPage projectId={route.projectId} />;
  }

  if (route.page === "parse" && route.projectId && route.documentId) {
    return <ParseResultsPage projectId={route.projectId} documentId={route.documentId} />;
  }

  if (route.page === "upload" && route.projectId) {
    return <UploadPage projectId={route.projectId} />;
  }

  return <ProjectListPage />;
}
