import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type PDFPageProxy } from "pdfjs-dist";
import workerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import { ClayButton } from "../../../components/ui/ClayButton";

GlobalWorkerOptions.workerSrc = workerSrc;

type StandardPdfPaneProps = {
  pdfUrl: string;
  targetPage: number | null;
};

export function StandardPdfPane({ pdfUrl, targetPage }: StandardPdfPaneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1.1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let disposed = false;
    setLoading(true);
    setError("");

    const task = getDocument(pdfUrl);
    task.promise
      .then((doc: PDFDocumentProxy) => {
        if (disposed) return;
        setPdfDoc(doc);
        setPageCount(doc.numPages);
        setPageNumber(1);
      })
      .catch((err: unknown) => {
        if (disposed) return;
        setError(err instanceof Error ? err.message : "PDF 加载失败");
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });

    return () => {
      disposed = true;
      void task.destroy();
    };
  }, [pdfUrl]);

  useEffect(() => {
    if (!targetPage || pageCount === 0) return;
    setPageNumber(Math.min(Math.max(targetPage, 1), pageCount));
  }, [pageCount, targetPage]);

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;

    let cancelled = false;

    pdfDoc.getPage(pageNumber).then((page: PDFPageProxy) => {
      if (cancelled || !canvasRef.current) return;
      const viewport = page.getViewport({ scale: zoom });
      const canvas = canvasRef.current;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const ratio = window.devicePixelRatio || 1;
      canvas.width = viewport.width * ratio;
      canvas.height = viewport.height * ratio;
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

      void page.render({
        canvasContext: ctx,
        viewport,
      }).promise;
    }).catch((err: unknown) => {
      if (!cancelled) {
        setError(err instanceof Error ? err.message : "PDF 页面渲染失败");
      }
    });

    return () => {
      cancelled = true;
    };
  }, [pageNumber, pdfDoc, zoom]);

  return (
    <div className="standard-pdf-pane">
      <div className="standard-pdf-pane__toolbar">
        <div className="standard-pdf-pane__pager">
          <ClayButton type="button" variant="ghost" size="sm" disabled={pageNumber <= 1} onClick={() => setPageNumber((value) => value - 1)}>
            上一页
          </ClayButton>
          <span>第 {pageNumber} / {pageCount || "?"} 页</span>
          <ClayButton type="button" variant="ghost" size="sm" disabled={pageCount === 0 || pageNumber >= pageCount} onClick={() => setPageNumber((value) => value + 1)}>
            下一页
          </ClayButton>
        </div>
        <div className="standard-pdf-pane__pager">
          <ClayButton type="button" variant="ghost" size="sm" onClick={() => setZoom((value) => Math.max(0.8, value - 0.1))}>
            缩小
          </ClayButton>
          <span>{Math.round(zoom * 100)}%</span>
          <ClayButton type="button" variant="ghost" size="sm" onClick={() => setZoom((value) => Math.min(2, value + 0.1))}>
            放大
          </ClayButton>
        </div>
      </div>

      <div className="standard-pdf-pane__viewport">
        {loading ? (
          <div className="empty-state">
            <div className="spinner" />
            <p>PDF 加载中...</p>
          </div>
        ) : error ? (
          <div className="empty-state text-error">{error}</div>
        ) : (
          <canvas ref={canvasRef} className="standard-pdf-pane__canvas" />
        )}
      </div>
    </div>
  );
}
