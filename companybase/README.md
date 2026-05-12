# Tender 公司资料基座

本目录用于一次整理、反复导入和迁移复用 tender 系统需要的公司主数据，包括公司资料、资质证书、人员、人员证书、公司资产、业绩、财务、制度能力和 PDF/图片证据附件。

核心原则：

- 结构化数据写入 `templates/companybase_master.xlsx` 或 `templates/csv/*.csv`。
- PDF、图片扫描件放入 `files/` 下的业务目录。
- 所有附件通过 `附件索引` sheet 关联到结构化主数据，后续导入为 `evidence_asset`。
- 所有主数据行必须填写稳定的 `unique_key`，用于开发库、测试库、上线库反复导入时幂等更新。
- 不直接把开发数据库当作唯一资料源；开发库只作为验证导入器和生成质量的环境。

## 快速使用

1. 复制 `templates/companybase_master.xlsx` 为一个工作副本，例如 `imports/companybase_master_2026-05-13.xlsx`。
2. 按 sheet 填写公司、资质、人员、资产、业绩等结构化资料。
3. 将证书、合同、验收证明、人员证书、设备检定证书等附件放入 `files/` 对应目录。
4. 在 `附件索引` sheet 中登记每个附件的 `file_relative_path`、`owner_type`、`owner_unique_key`。
5. 运行 `tools/validate_companybase.py` 做离线校验。
6. 通过后再运行系统导入器或接口导入到开发库/上线库。
7. 每次大批量更新后运行 `tools/backup_companybase.sh` 生成资料包备份。

## 目录说明

```text
companybase/
  README.md
  docs/                         # 录入、字段、附件、导入、备份说明
  templates/
    companybase_master.xlsx      # 主数据 Excel 模板
    csv/                         # 同字段 CSV 示例，可用于脚本导入
  files/                         # PDF/图片附件根目录
    company/                     # 公司主体、营业执照、体系认证等
    qualification/               # 企业资质和许可扫描件
    personnel/                   # 人员证书、身份证明、社保证明等
    assets/                      # 车辆、设备、工器具、安全器具附件
    performance/                 # 业绩合同、验收、评价等
    finance/                     # 财务报表、审计报告、纳税证明等
    methods/                     # 制度、方案、工法、预案、数字化能力材料
  imports/                       # 待导入工作副本
  exports/                       # 导入报告、校验报告、系统导出快照
  backups/                       # 压缩备份包
  tools/                         # 模板生成、校验、备份脚本
```

## 当前系统字段映射

本资料包按现有 tender 系统主数据设计：

- `library_company`：公司库主体。
- `company_profile`：公司基础资料。
- `qualification_certificate`：企业资质、许可证、体系认证等结构化记录。
- `person_profile`：人员基础资料。
- `company_asset`：车辆、施工机械、工器具、安全设施设备。
- `project_performance`：项目业绩。
- `financial_statement`：财务数据。
- `evidence_asset`：所有 PDF、图片证据附件。

## 推荐下一步

先用模板录入 10-20 条核心数据和对应附件，跑一轮校验和开发库导入；确认字段、命名和附件挂靠方式没有问题后，再扩展到全量资料。
