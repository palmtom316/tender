import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const {
  fetchLibraryCompaniesMock,
  fetchAssetTaxonomyMock,
  fetchCompanyProfilesMock,
  fetchEvidenceAssetsMock,
  fetchCompanyContractPerformancesMock,
  deleteLibraryCompanyMock,
  createCompanyContractPerformanceMock,
  updateCompanyContractPerformanceMock,
  deleteCompanyContractPerformanceMock,
  uploadEvidenceAssetMock,
} = vi.hoisted(() => ({
  fetchLibraryCompaniesMock: vi.fn(),
  fetchAssetTaxonomyMock: vi.fn(),
  fetchCompanyProfilesMock: vi.fn(),
  fetchEvidenceAssetsMock: vi.fn(),
  fetchCompanyContractPerformancesMock: vi.fn(),
  deleteLibraryCompanyMock: vi.fn(),
  createCompanyContractPerformanceMock: vi.fn(),
  updateCompanyContractPerformanceMock: vi.fn(),
  deleteCompanyContractPerformanceMock: vi.fn(),
  uploadEvidenceAssetMock: vi.fn(),
}));

vi.mock("../../../lib/api", async () => {
  const actual = await vi.importActual("../../../lib/api");
  return {
    ...actual,
    fetchLibraryCompanies: fetchLibraryCompaniesMock,
    fetchAssetTaxonomy: fetchAssetTaxonomyMock,
    fetchCompanyProfiles: fetchCompanyProfilesMock,
    fetchEvidenceAssets: fetchEvidenceAssetsMock,
    fetchCompanyContractPerformances: fetchCompanyContractPerformancesMock,
    deleteLibraryCompany: deleteLibraryCompanyMock,
    createCompanyContractPerformance: createCompanyContractPerformanceMock,
    updateCompanyContractPerformance: updateCompanyContractPerformanceMock,
    deleteCompanyContractPerformance: deleteCompanyContractPerformanceMock,
    uploadEvidenceAsset: uploadEvidenceAssetMock,
  };
});

import { CompanyLibraryWorkbench } from "./CompanyLibraryWorkbench";

afterEach(() => {
  cleanup();
});

describe("CompanyLibraryWorkbench", () => {
  it("deletes a library company from the list", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchLibraryCompaniesMock
      .mockResolvedValueOnce([
        { id: "lib-1", company_name: "REDACTED", company_type: "施工总承包", company_key: "REDACTED", enabled: true, metadata_json: {}, created_at: "", updated_at: "" },
        { id: "lib-2", company_name: "重庆山城电建", company_type: "输变电", company_key: "cq-sc", enabled: true, metadata_json: {}, created_at: "", updated_at: "" },
      ])
      .mockResolvedValueOnce([
        { id: "lib-2", company_name: "重庆山城电建", company_type: "输变电", company_key: "cq-sc", enabled: true, metadata_json: {}, created_at: "", updated_at: "" },
      ]);
    fetchAssetTaxonomyMock.mockResolvedValue({
      domains: [
        { domain: "company_qualification", label: "公司资质文件", categories: [["business_license", "营业执照"]] },
        { domain: "company_asset", label: "公司资产文件", categories: [["vehicle_certificate", "机动车辆证明文件"]] },
        { domain: "company_performance", label: "公司业绩文件", categories: [["contract_document", "合同"]] },
      ],
    });
    fetchCompanyProfilesMock.mockResolvedValue([]);
    fetchEvidenceAssetsMock.mockResolvedValue([]);
    fetchCompanyContractPerformancesMock.mockResolvedValue([]);
    deleteLibraryCompanyMock.mockResolvedValue({ deleted: true });

    render(<CompanyLibraryWorkbench />);

    expect(await screen.findByRole("button", { name: "删除公司库 REDACTED" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除公司库 重庆山城电建" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "删除公司库 REDACTED" }));

    await waitFor(() => expect(deleteLibraryCompanyMock).toHaveBeenCalledWith("lib-1"));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "删除公司库 REDACTED" })).not.toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "删除公司库 重庆山城电建" })).toBeInTheDocument();
  });

  it("renders contract performance ledger and submits structured form", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fetchLibraryCompaniesMock.mockResolvedValue([{ id: "lib-1", company_name: "REDACTED", company_type: "施工总承包", company_key: "REDACTED", enabled: true, metadata_json: {}, created_at: "", updated_at: "" }]);
    fetchAssetTaxonomyMock.mockResolvedValue({
      domains: [
        { domain: "company_qualification", label: "公司资质文件", categories: [["business_license", "营业执照"]] },
        { domain: "company_asset", label: "公司资产文件", categories: [["vehicle_certificate", "机动车辆证明文件"]] },
        { domain: "company_performance", label: "公司业绩文件", categories: [["contract_document", "合同"]] },
        { domain: "personnel", label: "人员资料", categories: [["id_card", "身份证"]] },
      ],
    });
    fetchCompanyProfilesMock.mockResolvedValue([]);
    fetchEvidenceAssetsMock.mockResolvedValue([]);
    fetchCompanyContractPerformancesMock
      .mockResolvedValueOnce([
        {
          id: "perf-1",
          library_company_id: "lib-1",
          auto_number: 1,
          contract_name: "配网工程合同",
          party_a_company: "国网重庆公司",
          contract_category: "施工合同",
          engineering_category: "电力工程",
      contract_amount: "880000.00",
      contract_signed_date: "2025-01-10",
      contract_completed_date: "2025-12-30",
      contract_status: "已完工",
      signature_asset_id: "asset-sign-1",
      signature_asset_name: "合同主要签署页面.pdf",
      invoice_asset_id: null,
      invoice_asset_name: null,
      invoice_verification_asset_id: null,
      invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
      ])
      .mockResolvedValueOnce([
        {
          id: "perf-1",
          library_company_id: "lib-1",
          auto_number: 1,
          contract_name: "配网工程合同",
          party_a_company: "国网重庆公司",
          contract_category: "施工合同",
          engineering_category: "电力工程",
          contract_amount: "880000.00",
          contract_signed_date: "2025-01-10",
          contract_completed_date: "2025-12-30",
          contract_status: "已完工",
          signature_asset_id: "asset-sign-1",
          signature_asset_name: "合同主要签署页面.pdf",
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
        {
          id: "perf-2",
          library_company_id: "lib-1",
          auto_number: 2,
          contract_name: "输电线路改造合同",
          party_a_company: "重庆某建设单位",
          contract_category: "总承包合同",
          engineering_category: "输电工程",
          contract_amount: "1680000.00",
          contract_signed_date: "2025-02-01",
          contract_completed_date: "2025-11-15",
          contract_status: "履约中",
          signature_asset_id: null,
          signature_asset_name: null,
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
      ]);
    createCompanyContractPerformanceMock.mockResolvedValue({
      id: "perf-2",
      library_company_id: "lib-1",
      auto_number: 2,
      contract_name: "输电线路改造合同",
      party_a_company: "重庆某建设单位",
      contract_category: "总承包合同",
      engineering_category: "输电工程",
      contract_amount: "1680000.00",
      contract_signed_date: "2025-02-01",
      contract_completed_date: "2025-11-15",
      contract_status: "履约中",
      signature_asset_id: null,
      signature_asset_name: null,
      invoice_asset_id: null,
      invoice_asset_name: null,
      invoice_verification_asset_id: null,
      invoice_verification_asset_name: null,
      performance_evaluation_asset_id: null,
      performance_evaluation_asset_name: null,
      created_at: "",
      updated_at: "",
    });
    updateCompanyContractPerformanceMock.mockResolvedValue({
      id: "perf-1",
      library_company_id: "lib-1",
      auto_number: 1,
      contract_name: "配网工程合同-更新",
      party_a_company: "国网重庆公司",
      contract_category: "施工合同",
      engineering_category: "电力工程",
      contract_amount: "990000.00",
      contract_signed_date: "2025-01-10",
      contract_completed_date: "2025-12-30",
      contract_status: "已完工",
      signature_asset_id: null,
      signature_asset_name: null,
      invoice_asset_id: null,
      invoice_asset_name: null,
      invoice_verification_asset_id: null,
      invoice_verification_asset_name: null,
      performance_evaluation_asset_id: null,
      performance_evaluation_asset_name: null,
      created_at: "",
      updated_at: "",
    });
    deleteCompanyContractPerformanceMock.mockResolvedValue({ deleted: true });
    fetchCompanyContractPerformancesMock
      .mockResolvedValueOnce([
        {
          id: "perf-1",
          library_company_id: "lib-1",
          auto_number: 1,
          contract_name: "配网工程合同",
          party_a_company: "国网重庆公司",
          contract_category: "施工合同",
          engineering_category: "电力工程",
          contract_amount: "880000.00",
          contract_signed_date: "2025-01-10",
          contract_completed_date: "2025-12-30",
          contract_status: "已完工",
          signature_asset_id: "asset-sign-1",
          signature_asset_name: "合同主要签署页面.pdf",
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
      ])
      .mockResolvedValueOnce([
        {
          id: "perf-1",
          library_company_id: "lib-1",
          auto_number: 1,
          contract_name: "配网工程合同",
          party_a_company: "国网重庆公司",
          contract_category: "施工合同",
          engineering_category: "电力工程",
          contract_amount: "880000.00",
          contract_signed_date: "2025-01-10",
          contract_completed_date: "2025-12-30",
          contract_status: "已完工",
          signature_asset_id: null,
          signature_asset_name: null,
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
        {
          id: "perf-2",
          library_company_id: "lib-1",
          auto_number: 2,
          contract_name: "输电线路改造合同",
          party_a_company: "重庆某建设单位",
          contract_category: "总承包合同",
          engineering_category: "输电工程",
          contract_amount: "1680000.00",
          contract_signed_date: "2025-02-01",
          contract_completed_date: "2025-11-15",
          contract_status: "履约中",
          signature_asset_id: null,
          signature_asset_name: null,
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
      ])
      .mockResolvedValueOnce([
        {
          id: "perf-1",
          library_company_id: "lib-1",
          auto_number: 1,
          contract_name: "配网工程合同-更新",
          party_a_company: "国网重庆公司",
          contract_category: "施工合同",
          engineering_category: "电力工程",
          contract_amount: "990000.00",
          contract_signed_date: "2025-01-10",
          contract_completed_date: "2025-12-30",
          contract_status: "已完工",
          signature_asset_id: null,
          signature_asset_name: null,
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
        {
          id: "perf-2",
          library_company_id: "lib-1",
          auto_number: 2,
          contract_name: "输电线路改造合同",
          party_a_company: "重庆某建设单位",
          contract_category: "总承包合同",
          engineering_category: "输电工程",
          contract_amount: "1680000.00",
          contract_signed_date: "2025-02-01",
          contract_completed_date: "2025-11-15",
          contract_status: "履约中",
          signature_asset_id: null,
          signature_asset_name: null,
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
      ])
      .mockResolvedValueOnce([
        {
          id: "perf-2",
          library_company_id: "lib-1",
          auto_number: 1,
          contract_name: "输电线路改造合同",
          party_a_company: "重庆某建设单位",
          contract_category: "总承包合同",
          engineering_category: "输电工程",
          contract_amount: "1680000.00",
          contract_signed_date: "2025-02-01",
          contract_completed_date: "2025-11-15",
          contract_status: "履约中",
          signature_asset_id: null,
          signature_asset_name: null,
          invoice_asset_id: null,
          invoice_asset_name: null,
          invoice_verification_asset_id: null,
          invoice_verification_asset_name: null,
          performance_evaluation_asset_id: null,
          performance_evaluation_asset_name: null,
          created_at: "",
          updated_at: "",
        },
      ]);
    render(<CompanyLibraryWorkbench />);
    expect(await screen.findByRole("button", { name: "下载合同业绩表" })).toBeInTheDocument();
    expect(await screen.findByText("配网工程合同")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("合同名称"), { target: { value: "输电线路改造合同" } });
    fireEvent.change(screen.getByLabelText("合同甲方单位"), { target: { value: "重庆某建设单位" } });
    fireEvent.change(screen.getByLabelText("合同类别"), { target: { value: "总承包合同" } });
    fireEvent.change(screen.getByLabelText("工程类别"), { target: { value: "输电工程" } });
    fireEvent.change(screen.getByLabelText("合同金额"), { target: { value: "1680000.00" } });
    fireEvent.change(screen.getByLabelText("合同签订日期"), { target: { value: "2025-02-01" } });
    fireEvent.change(screen.getByLabelText("合同竣工日期"), { target: { value: "2025-11-15" } });
    fireEvent.change(screen.getByLabelText("合同状态"), { target: { value: "履约中" } });
    fireEvent.click(screen.getByRole("button", { name: "新增合同业绩" }));

    await waitFor(() =>
      expect(createCompanyContractPerformanceMock).toHaveBeenCalledWith(
        expect.objectContaining({
          library_company_id: "lib-1",
          contract_name: "输电线路改造合同",
          party_a_company: "重庆某建设单位",
        }),
      ),
    );
    expect(await screen.findByText("输电线路改造合同")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "编辑" })[0]);
    expect(screen.getByDisplayValue("配网工程合同")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "合同主要签署页面.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /下载/u })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("合同名称"), { target: { value: "配网工程合同-更新" } });
    fireEvent.change(screen.getByLabelText("合同金额"), { target: { value: "990000.00" } });
    fireEvent.click(screen.getAllByRole("button", { name: "清空附件" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() =>
      expect(updateCompanyContractPerformanceMock).toHaveBeenCalledWith(
        "perf-1",
        expect.objectContaining({
          contract_name: "配网工程合同-更新",
          contract_amount: "990000.00",
          signature_asset_id: null,
          signature_asset_name: null,
        }),
      ),
    );

    const deleteButtons = screen.getAllByRole("button", { name: "删除" });
    fireEvent.click(deleteButtons[0]);
    await waitFor(() => expect(deleteCompanyContractPerformanceMock).toHaveBeenCalledWith("perf-1"));
  });
});
