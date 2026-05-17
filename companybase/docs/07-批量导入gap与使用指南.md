# Companybase 批量导入 — Gap 与使用指南

> 创建日期：2026-05-18
> 范围：公司主体 / 公司资料 / 人员资料 / 附件索引 / 业绩 / 资产 / 资质 / 财务 / 制度 9 张表的批量导入与备份
> 状态：现状核实 + Bug 清单 + 使用指南（基于代码实际能力，非 docs 宣称能力）

本指南补充 `companybase/docs/01-06` 的差距，**真实能用的功能**以本文为准。`docs/01-06` 中部分流程（CLI 导入器、9 表全导入、delete_flag、SHA256 去重、CSV 报告输出）目前**未实现**，详见第二节 Bug 清单。

## 一、现状摘要

| 项 | 真实状况 |
|---|---|
| 接口入口 | `POST /api/master-data/companybase/{validate,import}`、`GET /api/master-data/companybase/backup`；CLI `companybase/tools/backup_companybase.sh`、`companybase/tools/validate_companybase.py` |
| 文件包根 | `companybase/`（`backend/tender_backend/services/companybase_import_service.py:71`） |
| Xlsx 入口 | 只读 `companybase/templates/companybase_master.xlsx` 这一个 workbook（前端/API 上传也指向同一文件） |
| **实际能进库的 sheet** | 仅 4 张：**公司主体、公司资料、人员资料、附件索引**（`MVP_SHEETS`，service `:26`）。**业绩、资产、资质、财务、制度** sheet 即使填了也**不会进库** — 只产 P1 警告，沉默跳过 |
| 附件 owner_type 支持 | 仅 `library_company / company_profile / person_profile`（`SUPPORTED_OWNER_TYPES`，`:27`）。`project_performance / company_asset / qualification_certificate` 在 `:284-287` 直接 `skipped += 1` 静默丢弃 |
| 文件后缀白名单 | `.pdf .png .jpg .jpeg .bmp .gif .tif .tiff`（`:25`） |
| DB 存储形态 | `evidence_asset.file_path` = **服务器绝对路径**，不是 URL／OSS key |
| 去重键 | 靠 xlsx 里的 `unique_key / attachment_key` 写到 JSON `import` 字段（service `:340`、`:345-350`），**未用 SHA256** |
| restore 接口 | **没有**。`/backup` 只下载 tar.gz，恢复要手动解压再 import |
| 包目录结构 | `companybase/{templates, imports, files/{company,qualification,personnel,assets,performance,finance,methods}, exports, backups, tools}` |

## 二、必修 Bug（按严重度）

| # | 位置 | 问题 | 建议修订 |
|---|---|---|---|
| 1 | `companybase_import_service.py:283-287` + `:27` | 业绩/资产/资质/财务 sheet 附件**永远丢失** — 与 `docs/04` 宣称的 9 步流程严重不符 | 要么扩 `SUPPORTED_OWNER_TYPES` + 新增 4 个 sheet 的导入分支；要么 API/校验阶段就拒收，避免用户以为成功 |
| 2 | `:90-100` | `/backup` 把 tar.gz 写到 `tempfile.gettempdir()` 后**永不删除** — 磁盘泄漏 | 改成 `FileResponse(..., background=BackgroundTask(os.unlink, path))` 或写到 `companybase/exports/` 后由清理任务回收 |
| 3 | `:358-360` `_int()` | `"35.0"`、`" 35 "`、`"-1"`、Excel 数字格式都返回 None；`age / years_experience / sort_order` 被静默丢失 | `int(float(raw.replace(",", "")))`，并把异常归到 issues |
| 4 | `:428-440` `_update_record` | 每次更新都把**所有字段覆盖**，包括把空字符串改成 None — 会把上次填的数据冲掉 | 跳过 `value is None` 或空串的字段；或加一列 `merge_strategy` 控制 |
| 5 | `:87` `conn.commit()` | service 内显式 commit，FastAPI `get_db_conn` 通常自带事务，可能"半提交" | 把 commit 抽到 API 层 + dependency；或在 service 注明"调用方不可有外层事务" |
| 6 | `docs/04` vs 代码 | docs 提到 CLI `backend/tender_backend/tools/import_companybase.py`、`delete_flag=TRUE`、SHA256 去重、`import_success/errors.csv` 报告 — **全部未实现** | 至少把 docs 改成现实，否则用户继续踩坑 |
| 7 | `_find_by_import_key:372-378` | 表名/列名用 f-string 拼，虽然当前是常量但模式不安全 | 用 `psycopg.sql.Identifier` |

## 三、使用指南（基于当前可用功能）

### 3.1 准备包目录

```
companybase/
├── templates/
│   └── companybase_master.xlsx              ← 唯一会被读取的 workbook
└── files/                                   ← 附件根（file_relative_path 的基准）
    ├── company/
    │   └── COMP_001/
    │       ├── 营业执照_2027-12-31.pdf
    │       └── ISO9001_2027-06-30.pdf
    ├── personnel/
    │   └── PROJ_MGR_001/
    │       ├── 身份证.pdf
    │       ├── 一级建造师证_2028-06-30.pdf
    │       └── 简历.pdf
    └── qualification/
        └── QUAL_001/
            └── 安全生产许可证_2027-08-15.pdf
```

### 3.2 填 xlsx 的 4 张"会进库"sheet

**公司主体**

| 列 | 必填 | 说明 |
|---|---|---|
| `company_key` | ✓ | 幂等键，自定义 ASCII id |
| `company_name` | ✓ | 公司名称 |
| `company_type` | | 公司类型 |
| `enabled` | | `TRUE`(默认) / `FALSE` |
| `metadata_json` | | 合法 JSON object 字符串 |

**公司资料**（一对一扩展公司主体）

| 列 | 必填 | 说明 |
|---|---|---|
| `unique_key` | ✓ | 幂等键 |
| `company_key` | ✓ | 指向公司主体 |
| `company_name` | ✓ | |
| `unified_social_credit_code` | | 统一社会信用代码 |
| `registered_capital` | | 字符串字段 |
| `profile_json` | | JSON object |
| 其它 | | `company_code / registered_address / contact_* / website / company_type / business_scope` |

**人员资料**

| 列 | 必填 | 说明 |
|---|---|---|
| `unique_key` | ✓ | 幂等键 |
| `company_key` | ✓ | 关联公司 |
| `full_name` | ✓ | |
| `age / years_experience` | | **必须整数**，小数/带逗号会被丢（Bug #3） |
| `profile_json` | | JSON object |
| 其它 | | `gender / education / title / role_name / specialty / phone / email / resume_text` |

**附件索引**

| 列 | 必填 | 说明 |
|---|---|---|
| `attachment_key` | ✓ | 幂等键 |
| `owner_type` | ✓ | **只能填 `library_company / company_profile / person_profile`** — 其它值会被静默 skip（Bug #1） |
| `owner_unique_key` | ✓ | 指向上面三表里的 `company_key` 或 `unique_key` |
| `company_key` | ✓ | 关联公司 |
| `file_relative_path` | ✓ | **相对 `companybase/` 根**，例如 `files/personnel/PROJ_MGR_001/一级建造师证_2028-06-30.pdf` |
| `issued_on / expires_on` | | 必须 `YYYY-MM-DD` |
| `is_blind_sensitive` | | `TRUE`/`FALSE`，盲标敏感词 |
| `redaction_note` | | 盲标说明 |
| 其它 | | `asset_name / asset_domain / asset_category / asset_type / media_type / issuer_name / sort_order` |

### 3.3 文件命名

代码**不强制命名格式**，只校验：
- 后缀必须在白名单内
- 路径不得逃出 `companybase/`
- 文件必须存在 — 但**仅产 P1 警告，不阻塞校验**；import 阶段静默 skip（容易误以为成功）

**建议命名**（仅工程规范，代码不查）：`{owner_unique_key}_{用途}_{有效期或日期}.pdf`

示例：
- `PROJ_MGR_001_一级建造师证_2028-06-30.pdf`
- `COMP_001_营业执照_2027-12-31.pdf`
- `QUAL_001_安全生产许可证_2027-08-15.pdf`

### 3.4 操作流程

```bash
# 1. dry-run 校验
curl -F "workbook=@companybase/templates/companybase_master.xlsx" \
  http://localhost:8000/api/master-data/companybase/validate

# 2. 看返回的 issues：P0=阻塞，P1=警告（业绩/资产 sheet 必然出 P1）
# 3. 真实导入
curl -F "workbook=@companybase/templates/companybase_master.xlsx" \
  "http://localhost:8000/api/master-data/companybase/import?dry_run=false"

# 4. 备份（⚠ tar.gz 现在不会被自动清理，参见 Bug #2）
curl -OJ http://localhost:8000/api/master-data/companybase/backup
```

### 3.5 当前最大坑

- **业绩 / 资产 / 资质 数据走不了这个接口**。当前唯一可行做法：用 `master_data_performances` / `master_data_assets` / `master_data_qualifications` 等独立 router 单条/批量 API 上传。或等 Bug #1 修完。
- **重复导入会覆盖未填字段**（Bug #4）— 同一行只填要改的列是危险的，必须**整行重发**。
- **附件文件没传到服务器就 import** — 校验只报 P1 警告不阻塞，import 阶段静默 skip，容易以为成功了。**先把 `companybase/files/` 整目录同步到服务器同一路径，再调 import**。
- **数字字段（age / years_experience / sort_order）必须纯整数** — Excel 默认数字格式可能被丢，参见 Bug #3。

## 四、建议动手顺序

1. **Bug #2（backup 磁盘泄漏）** — 10 分钟，纯改 API 文件返回方式
2. **Bug #4（update 不覆盖空字段）** — 20 分钟，单元测好补
3. **Bug #1 决策**：业绩/资产/资质是补全到这个接口里（大改），还是把范围明确收窄到"公司+人员+附件"，业绩等走独立 API？**建议收窄 + 改 docs**，业绩字段比人员复杂，硬塞 xlsx 后期维护成本高
4. **Bug #3、#6、#5、#7**

## 五、参考

- 服务实现：`backend/tender_backend/services/companybase_import_service.py`
- API 层：`backend/tender_backend/api/companybase.py`
- 路由挂载：`backend/tender_backend/api/master_data.py:5,81`
- 数据库表：`library_company / company_profile / person_profile / evidence_asset`
- 现有 docs（与代码部分背离）：`companybase/docs/01-06`
