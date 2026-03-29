import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { getDocumentMock, renderMock, getPageMock } = vi.hoisted(() => {
  const renderMock = vi.fn(() => ({ promise: Promise.resolve() }));
  const getPageMock = vi.fn(async () => ({
    getViewport: () => ({ width: 200, height: 300 }),
    render: renderMock,
  }));
  return {
    getDocumentMock: vi.fn(),
    renderMock,
    getPageMock,
  };
});

vi.mock("pdfjs-dist", () => ({
  getDocument: getDocumentMock,
  GlobalWorkerOptions: {},
}));

vi.mock("pdfjs-dist/build/pdf.worker.min.mjs?url", () => ({
  default: "/mock-pdf-worker.mjs",
}));

import { StandardPdfPane } from "./StandardPdfPane";

describe("StandardPdfPane", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    localStorage.setItem("tender_token", "dev-token");

    Object.defineProperty(window, "devicePixelRatio", {
      value: 1,
      configurable: true,
    });

    HTMLCanvasElement.prototype.getContext = vi.fn(() => (
      { setTransform: vi.fn() } as unknown as CanvasRenderingContext2D
    )) as unknown as typeof HTMLCanvasElement.prototype.getContext;
  });

  it("fetches the protected PDF bytes before handing them to pdf.js", async () => {
    const pdfBytes = new Uint8Array([37, 80, 68, 70, 45, 49, 46, 55]);
    const fetchMock = vi.fn(async () => ({
      ok: true,
      arrayBuffer: async () => pdfBytes.buffer,
    }));
    vi.stubGlobal("fetch", fetchMock);

    getDocumentMock.mockReturnValue({
      promise: Promise.resolve({
        numPages: 3,
        getPage: getPageMock,
      }),
      destroy: vi.fn(),
    });

    render(<StandardPdfPane pdfUrl="/api/standards/std-1/pdf" targetPage={2} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/standards/std-1/pdf", {
        headers: { Authorization: "Bearer dev-token" },
        signal: expect.any(AbortSignal),
      });
    });

    await waitFor(() => {
      expect(getDocumentMock).toHaveBeenCalledWith({ data: pdfBytes });
    });

    await waitFor(() => {
      expect(getPageMock).toHaveBeenCalledWith(2);
      expect(renderMock).toHaveBeenCalled();
    });
  });
});
