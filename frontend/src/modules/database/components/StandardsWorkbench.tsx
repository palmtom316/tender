import { useCallback, useEffect, useRef, useState } from "react";

import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import type {
  Standard,
  StandardParseAssets,
  StandardQualityReportResponse,
  StandardSearchHit,
  StandardViewerData,
} from "../../../lib/api";
import {
  deleteStandard,
  fetchStandardParseAssets,
  fetchStandardQualityReport,
  fetchStandardViewer,
  listStandards,
  triggerStandardProcessing,
} from "../../../lib/api";
import { StandardSearchCard } from "./StandardSearchCard";
import { StandardsTableCard } from "./StandardsTableCard";
import { StandardViewerModal } from "./StandardViewerModal";
import { UploadForm } from "./UploadForm";

function isActiveStatus(status: string): boolean {
  return ["queued_ocr", "parsing", "queued_ai", "processing"].includes(status);
}

export function StandardsWorkbench() {
  const [standards, setStandards] = useState<Standard[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState("");
  const [showDevArtifacts, setShowDevArtifacts] = useState(false);
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerMode, setViewerMode] = useState<"browse" | "search-hit">("browse");
  const [viewerData, setViewerData] = useState<StandardViewerData | null>(null);
  const [viewerParseAssets, setViewerParseAssets] = useState<StandardParseAssets | null>(null);
  const [viewerParseAssetsLoading, setViewerParseAssetsLoading] = useState(false);
  const [viewerParseAssetsError, setViewerParseAssetsError] = useState("");
  const [viewerQualityReport, setViewerQualityReport] = useState<StandardQualityReportResponse | null>(null);
  const [viewerQualityReportLoading, setViewerQualityReportLoading] = useState(false);
  const [viewerQualityReportError, setViewerQualityReportError] = useState("");
  const [initialClauseId, setInitialClauseId] = useState<string | null>(null);
  const [pendingDeleteStandardId, setPendingDeleteStandardId] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const viewerRequestRef = useRef(0);
  const viewerAbortRef = useRef<AbortController | null>(null);

  const loadStandards = useCallback(() => {
    listStandards()
      .then((data) => {
        setStandards(data);
        setActionError("");
      })
      .catch((err: unknown) => setActionError(err instanceof Error ? err.message : "加载规范失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadStandards();
  }, [loadStandards]);

  const hasActiveStandards = standards.some((std) => isActiveStatus(std.processing_status));

  useEffect(() => {
    if (!hasActiveStandards) return undefined;

    pollingRef.current = window.setInterval(() => {
      loadStandards();
    }, 5000);

    return () => {
      if (pollingRef.current !== null) {
        window.clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [hasActiveStandards, loadStandards]);

  useEffect(() => () => {
    viewerAbortRef.current?.abort();
  }, []);

  const openViewer = async (
    standardId: string,
    mode: "browse" | "search-hit",
    clauseId: string | null = null,
  ) => {
    const requestId = viewerRequestRef.current + 1;
    viewerRequestRef.current = requestId;
    viewerAbortRef.current?.abort();
    const controller = new AbortController();
    viewerAbortRef.current = controller;
    setViewerParseAssets(null);
    setViewerParseAssetsError("");
    setViewerParseAssetsLoading(true);
    setViewerQualityReport(null);
    setViewerQualityReportError("");
    setViewerQualityReportLoading(true);

    try {
      const parseAssetsPromise = fetchStandardParseAssets(standardId, { signal: controller.signal })
        .then((assets) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerParseAssets(assets);
          setViewerParseAssetsError("");
        })
        .catch((err: unknown) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerParseAssets(null);
          setViewerParseAssetsError(err instanceof Error ? err.message : "加载解析诊断失败");
        })
        .finally(() => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerParseAssetsLoading(false);
        });
      const qualityReportPromise = fetchStandardQualityReport(standardId, { signal: controller.signal })
        .then((report) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerQualityReport(report);
          setViewerQualityReportError("");
        })
        .catch((err: unknown) => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerQualityReport(null);
          setViewerQualityReportError(err instanceof Error ? err.message : "加载质量报告失败");
        })
        .finally(() => {
          if (viewerRequestRef.current !== requestId || controller.signal.aborted) return;
          setViewerQualityReportLoading(false);
        });

      const data = await fetchStandardViewer(standardId, { signal: controller.signal });
      if (viewerRequestRef.current !== requestId) return;
      setViewerData(data);
      setViewerMode(mode);
      setInitialClauseId(clauseId);
      setViewerOpen(true);
      setActionError("");
      await parseAssetsPromise;
      await qualityReportPromise;
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (viewerRequestRef.current !== requestId) return;
      setViewerParseAssetsLoading(false);
      setViewerQualityReportLoading(false);
      setActionError(err instanceof Error ? err.message : "加载查阅数据失败");
    } finally {
      if (viewerAbortRef.current === controller) {
        viewerAbortRef.current = null;
      }
    }
  };

  const handleRetry = async (id: string) => {
    try {
      await triggerStandardProcessing(id);
      loadStandards();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "重新入队失败");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteStandard(id);
      if (viewerOpen && viewerData?.id === id) {
        setViewerOpen(false);
        setViewerData(null);
        setViewerParseAssets(null);
        setViewerParseAssetsError("");
        setViewerParseAssetsLoading(false);
        setViewerQualityReport(null);
        setViewerQualityReportError("");
        setViewerQualityReportLoading(false);
      }
      loadStandards();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "删除规范失败");
    }
  };

  const handleOpenSearchHit = (hit: StandardSearchHit) => {
    void openViewer(hit.standard_id, "search-hit", hit.clause_id);
  };

  const isDevMode = import.meta.env.DEV;
  const hiddenDevArtifactCount = isDevMode
    ? standards.filter((std) => std.is_dev_artifact).length
    : 0;
  const visibleStandards = isDevMode && !showDevArtifacts
    ? standards.filter((std) => !std.is_dev_artifact)
    : standards;

  return (
    <div className="standards-workbench">
      <UploadForm onUploaded={loadStandards} />

      <div className="standards-workbench__cards">
        <StandardsTableCard
          standards={visibleStandards}
          loading={loading}
          error={actionError}
          isDevMode={isDevMode}
          showDevArtifacts={showDevArtifacts}
          hiddenDevArtifactCount={!showDevArtifacts ? hiddenDevArtifactCount : 0}
          onToggleShowDevArtifacts={setShowDevArtifacts}
          onRetry={(id) => void handleRetry(id)}
          onDelete={(id) => setPendingDeleteStandardId(id)}
          onOpenViewer={(id) => void openViewer(id, "browse")}
        />

        <StandardSearchCard onOpenHit={handleOpenSearchHit} />
      </div>

      <StandardViewerModal
        open={viewerOpen}
        mode={viewerMode}
        viewerData={viewerData}
        parseAssets={viewerParseAssets}
        parseAssetsLoading={viewerParseAssetsLoading}
        parseAssetsError={viewerParseAssetsError}
        qualityReport={viewerQualityReport?.report ?? null}
        qualityReportLoading={viewerQualityReportLoading}
        qualityReportError={viewerQualityReportError}
        initialClauseId={initialClauseId}
        onClose={() => {
          viewerAbortRef.current?.abort();
          viewerAbortRef.current = null;
          setViewerOpen(false);
          setViewerParseAssetsLoading(false);
          setViewerParseAssetsError("");
          setViewerQualityReport(null);
          setViewerQualityReportError("");
          setViewerQualityReportLoading(false);
        }}
      />
      <ConfirmDialog
        open={pendingDeleteStandardId !== null}
        title="删除规范"
        description="删除后将移除整份规范、解析结果与源 PDF，且无法恢复。"
        confirmLabel="确认删除"
        onCancel={() => setPendingDeleteStandardId(null)}
        onConfirm={() => {
          const targetId = pendingDeleteStandardId;
          if (!targetId) return;
          setPendingDeleteStandardId(null);
          void handleDelete(targetId);
        }}
      />
    </div>
  );
}
