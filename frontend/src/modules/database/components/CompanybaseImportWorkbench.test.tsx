import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { validateMock, importMock, backupMock } = vi.hoisted(() => ({
  validateMock: vi.fn(),
  importMock: vi.fn(),
  backupMock: vi.fn(),
}));

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual("../../../lib/api");
  return {
    ...actual,
    validateCompanybaseWorkbook: validateMock,
    importCompanybaseWorkbook: importMock,
    backupCompanybaseUrl: backupMock,
  };
});

import { CompanybaseImportWorkbench } from "./CompanybaseImportWorkbench";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CompanybaseImportWorkbench", () => {
  it("validates an uploaded workbook and renders report actions", async () => {
    validateMock.mockResolvedValue({
      summary: { 公司主体: 1, 公司资料: 1, 人员资料: 2, 附件索引: 0 },
      issues: [{ severity: "P1", sheet: "附件索引", row: 2, message: "file does not exist yet" }],
      p0_count: 0,
      p1_count: 1,
      actions: { created: 0, updated: 0, skipped: 0 },
      dry_run: true,
    });

    render(<CompanybaseImportWorkbench />);

    const file = new File(["demo"], "companybase.xlsx", { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
    fireEvent.change(screen.getByLabelText("选择资料包 Excel"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "校验资料包" }));

    await waitFor(() => expect(validateMock).toHaveBeenCalledWith(file));
    expect(await screen.findByText("公司主体")).toBeInTheDocument();
    expect(screen.getByText("人员资料")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dry-run 预演导入" })).toBeEnabled();
  });

  it("runs dry-run then confirmed import", async () => {
    importMock
      .mockResolvedValueOnce({ summary: { 公司主体: 1 }, issues: [], p0_count: 0, p1_count: 0, actions: { created: 1, updated: 0, skipped: 0 }, dry_run: true })
      .mockResolvedValueOnce({ summary: { 公司主体: 1 }, issues: [], p0_count: 0, p1_count: 0, actions: { created: 1, updated: 0, skipped: 0 }, dry_run: false });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<CompanybaseImportWorkbench />);
    const file = new File(["demo"], "companybase.xlsx");
    fireEvent.change(screen.getByLabelText("选择资料包 Excel"), { target: { files: [file] } });

    fireEvent.click(screen.getByRole("button", { name: "Dry-run 预演导入" }));
    await waitFor(() => expect(importMock).toHaveBeenCalledWith(file, true));

    fireEvent.click(screen.getByRole("button", { name: "确认导入" }));
    await waitFor(() => expect(importMock).toHaveBeenCalledWith(file, false));
    expect(await screen.findByText("正式导入完成")).toBeInTheDocument();
  });
});
