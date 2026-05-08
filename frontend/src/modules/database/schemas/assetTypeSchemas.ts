import type { CompanyAssetType } from "../../../lib/api";

export type AssetExtraFieldType = "text" | "select" | "date";

export type AssetExtraField = {
  key: string;
  label: string;
  type: AssetExtraFieldType;
  options?: Array<{ value: string; label: string }>;
};

export type AssetTypeSchema = {
  key: CompanyAssetType;
  label: string;
  unitDefault: string;
  columns: Array<{ key: string; label: string }>;
  extras: AssetExtraField[];
};

export const ASSET_TYPE_SCHEMAS: Record<CompanyAssetType, AssetTypeSchema> = {
  vehicle: {
    key: "vehicle",
    label: "车辆",
    unitDefault: "辆",
    columns: [
      { key: "serial_no", label: "车牌/编号" },
      { key: "vehicle_type", label: "车辆类型" },
      { key: "technical_condition", label: "技术状况" },
    ],
    extras: [
      {
        key: "vehicle_type",
        label: "车辆类型",
        type: "select",
        options: [
          { value: "aerial_bucket", label: "斗臂车" },
          { value: "truck", label: "货车" },
          { value: "engineering", label: "工程车" },
          { value: "other", label: "其他" },
        ],
      },
      { key: "technical_grade", label: "技术等级", type: "text" },
    ],
  },
  machine: {
    key: "machine",
    label: "施工机械",
    unitDefault: "台",
    columns: [
      { key: "serial_no", label: "出厂编号" },
      { key: "machine_category", label: "机械类别" },
      { key: "capacity", label: "容量" },
    ],
    extras: [
      { key: "machine_category", label: "机械类别", type: "text" },
      { key: "capacity", label: "容量", type: "text" },
      {
        key: "is_special_equipment",
        label: "特种设备",
        type: "select",
        options: [
          { value: "yes", label: "是" },
          { value: "no", label: "否" },
        ],
      },
    ],
  },
  tool: {
    key: "tool",
    label: "施工工器具",
    unitDefault: "件",
    columns: [
      { key: "serial_no", label: "出厂编号" },
      { key: "tool_category", label: "工器具类别" },
      { key: "voltage_level", label: "电压等级" },
    ],
    extras: [
      { key: "tool_category", label: "工器具类别", type: "text" },
      { key: "voltage_level", label: "电压等级", type: "text" },
      { key: "last_inspection_at", label: "最近试验日期", type: "date" },
    ],
  },
  safety: {
    key: "safety",
    label: "安全设施设备及器具",
    unitDefault: "件",
    columns: [
      { key: "safety_category", label: "安全类别" },
      { key: "protection_standard", label: "防护标准" },
      { key: "applicable_work", label: "适用工种" },
    ],
    extras: [
      { key: "safety_category", label: "安全类别", type: "text" },
      { key: "protection_standard", label: "防护标准", type: "text" },
      { key: "applicable_work", label: "适用工种", type: "text" },
    ],
  },
};
