import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Standard } from "../../../lib/api";
import { StandardsTableCard } from "./StandardsTableCard";

const standard: Standard = {
  id: "std-1",
  standard_code: "GB 50148-2010",
  standard_name: "电气装置安装工程 电力变压器、油浸电抗器、互感器施工及验收规范",
  version_year: "2010",
  specialty: "电气",
  status: null,
  processing_status: "completed",
  ocr_status: "completed",
  ai_status: "completed",
  error_message: null,
  clause_count: 373,
  is_dev_artifact: false,
  created_at: "2026-03-26T01:00:00Z",
};

describe("StandardsTableCard", () => {
  it("does not render the legacy VL parse action", () => {
    render(
      <StandardsTableCard
        standards={[standard]}
        loading={false}
        error=""
        isDevMode
        showDevArtifacts={false}
        hiddenDevArtifactCount={0}
        onToggleShowDevArtifacts={vi.fn()}
        onRetry={vi.fn()}
        onDelete={vi.fn()}
        onOpenViewer={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: /VL解析/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查阅" })).toBeInTheDocument();
  });
});
