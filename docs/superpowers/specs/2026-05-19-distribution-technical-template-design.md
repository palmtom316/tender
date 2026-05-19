# 国网配网工程技术标模板包生成设计

- 日期：2026-05-19
- 主题：基于历史标书生成技术标第 0、1、2、3、4、5、6、7、13、14、15、16 章（共 12 个章号，含 5.1/5.2/5.3 三个子章节，manifest 共 15 个 chapter_code 单元）模板包
- 范围：单 DOCX 模板包 + manifest.json，可被 `package_importer` 导入
- 说明：第 8/9/10 章为施工方案/质量/安全/进度核心方案需项目定制不在本任务内；第 11/12 章已舍弃（第 11 章内容已在 TOC 第 10 章覆盖；第 12 章只是评分支撑材料重复）

## 背景

用户提供历史标书 `~/Downloads/电网工程施工-XX配网工程技术文件/`（20 个 docx，约 500MB），目录覆盖技术标 1-16 章。其中第 8、9、10 章属于"施工方案/质量保证/安全/进度"等需要按项目高度定制的内容，不适合统一模板；第 11、12 章在项目 TOC 已被第 10 章和评分支撑覆盖，重复无独立内容；故本任务只对**第 0 章 + 第 1-7 章 + 第 13-16 章（共 12 个章号，不包含第 8、9、10、11、12 章）**生成模板。

## 需求决策摘要

| 维度 | 决策 |
|---|---|
| 章节范围 | 第 0、1-7、13-16 章号（共 12 个章号；含 5.1/5.2/5.3 子章节后 manifest 共 15 个 chapter_code 单元）；第 8/9/10 章不在范围；第 11/12 章已舍弃 |
| 章节命名 | 以项目 TOC 为准，第 6 章反向更新 TOC 为「现场管理机构设置」 |
| 输出格式 | 单 DOCX + manifest.json（`package_importer` 约束） |
| 嵌入资料 | docxtpl 占位符（与 `business_chapter_bindings` 机制一致） |
| 固定文字程度 | 高保留：从历史标书提取完整文本，仅替换动态信息为占位符 |
| 脱敏 | 生成时自动脱敏（规则 + AI 校验），原 docx 不进仓库 |
| 第 16 章 | 用户文件无此章，基于行业通用承诺函格式生成标准模板 |
| 第 0 章 | 技术评分标准→支撑材料索引表，骨架由本任务生成，行数据来源由后续任务负责 |
| 图片处理 | 跳过原 docx 中的扫描件/图片，仅用占位符表示 |
| Pipeline | 脚本主导提取 + 规则脱敏 + DeepSeek AI 二次校验 |

## 1 / 产物结构

```
docs/samples/template_import_ready/
└── sgcc_distribution_technical_ch0_1_7_13_16_package/
    ├── README.md                                    # 使用说明 + 章节清单
    ├── 国网配网工程技术标_第0-7-13-16章.docx          # 单 DOCX 模板包（系统导入用）
    └── manifest.json                                # 章节-资料绑定元数据
```

**DOCX heading 结构**（按 `package_importer` 解析规则切章，按 chapter_code 顺序排列）：

| DOCX 章节顺序 | 完整 heading 文字 | chapter_code |
|---|---|---|
| 1 | 0. 技术评分标准支撑材料索引 | 0 |
| 2 | 1. 技术偏差表 | 1 |
| 3 | 2. 关于施工监理项目人员执业合规的承诺函 | 2 |
| 4 | 3. 工期响应 | 3 |
| 5 | 4. 资质情况 | 4 |
| 6 | 5. 业绩情况 | 5 |
| 7 | 5.1 类似工程业绩情况汇总表 | 5.1 |
| 8 | 5.2 近年完成的类似项目情况及证明材料 | 5.2 |
| 9 | 5.3 正在施工/新承接的类似项目情况及证明材料 | 5.3 |
| 10 | 6. 现场管理机构设置 | 6 |
| 11 | 7. 其他资格条件情况 | 7 |
| 12 | 13. 技术规范书规定的其他应提交的文件 | 13 |
| 13 | 14. 履约评价证明材料 | 14 |
| 14 | 15. 其他 | 15 |
| 15 | 16. 履约承诺函 | 16 |

`chapter_code` 保留 TOC 非连续值（0,1-7,5.1-5.3,13-16），与系统已有章节编码体系兼容。DOCX 内 15 个 heading 顺序连续递增。

**manifest.json 结构**（与 business 包对齐）：

```json
{
  "package_name": "国网配网工程技术标",
  "package_type": "technical",
  "chapter_count": 15,
  "source_docs": ["1.技术偏差表.docx", "...", "16.其他（如有）.docx"],
  "chapters": [
    {
      "chapter_code": "0",
      "chapter_name": "技术评分标准支撑材料索引",
      "item_type": "table",
      "render_mode": "templated",
      "required": true,
      "placeholders": ["scoring_index_rows"],
      "asset_categories": ["scoring_index"]
    },
    {
      "chapter_code": "1",
      "chapter_name": "技术偏差表",
      "item_type": "table",
      "render_mode": "templated",
      "required": true,
      "placeholders": [
        "company.company_name",
        "tender.project_name",
        "deviation_rows"
      ],
      "asset_categories": ["technical_deviation"]
    }
  ]
}
```

## 2 / 章节级设计

每章的 manifest 字段 + 占位符列表如下。

| chapter_code | chapter_name | item_type | render_mode | 主要占位符 | asset_categories |
|---|---|---|---|---|---|
| 0 | 技术评分标准支撑材料索引 | table | templated | `scoring_index_rows` | scoring_index |
| 1 | 技术偏差表 | table | templated | `company.company_name`, `tender.project_name`, `deviation_rows` | technical_deviation |
| 2 | 关于施工监理项目人员执业合规的承诺函 | chapter | templated | `company.company_name`, `tender.tender_no`, `tender.project_name`, `commitment_date` | commitment_letter |
| 3 | 工期响应 | chapter | templated | `tender.duration_days`, `tender.start_date`, `tender.end_date`, `company.company_name` | duration_response |
| 4 | 资质情况 | evidence | attachment | `certificates` (迭代各类资质证书) | qualification |
| 5 | 业绩情况 (父章) | chapter | templated | `performance_summary` | performance |
| 5.1 | 类似工程业绩情况汇总表 | table | templated | `performance_summary_rows` | performance |
| 5.2 | 近年完成的类似项目情况及证明材料 | evidence | attachment | `performances_recent` | performance_completed |
| 5.3 | 正在施工/新承接的类似项目情况及证明材料 | evidence | attachment | `performances_ongoing` | performance_ongoing |
| 6 | 现场管理机构设置 | chapter | templated | `project_manager`, `site_org_chart`, `personnel_table` | site_management |
| 7 | 其他资格条件情况 | chapter | templated | `other_qualifications` | other_qualification |
| 13 | 技术规范书规定的其他应提交的文件 | chapter | templated | `other_technical_documents` | technical_spec_other |
| 14 | 履约评价证明材料 | evidence | attachment | `performance_evaluations` | performance_evaluation |
| 15 | 其他 | chapter | templated | `other_materials` | other |
| 16 | 履约承诺函 | chapter | templated | `company.company_name`, `tender.project_name`, `tender.tender_no`, `commitment_date` | commitment_letter |

### 2.1 第 0 章评分索引表骨架

```
| 评分项编号 | 评分项名称 | 分值 | 支撑材料名称 | 所在章节 | 起始页码 |
|------------|-----------|------|--------------|----------|----------|
| {{ row.no }} | {{ row.name }} | {{ row.score }} | {{ row.material }} | {{ row.chapter }} | {{ row.page | default("待定") }} |
```

行数据来源：从招标文件 `附件7：技术评分细则.xlsx` 解析或人工录入，**不在本任务范围**。

### 2.2 第 16 章履约承诺函模板（基于国网通用格式生成）

```
致：{{ tender.tender_authority_name }}

我方（{{ company.company_name }}）参加贵方组织的 {{ tender.project_name }}（招标编号：{{ tender.tender_no }}）的投标，现郑重承诺：

1. 严格遵守国家电网有限公司各项规章制度，按招标文件、合同条款履约。
2. 不发生转包、违法分包、挂靠等违规行为。
3. 履约期间发生违约的，自愿接受相应处罚，承担相应法律责任。
4. 投标文件中所提供的资质证明、人员、业绩、设备等材料真实有效。

投标人：{{ company.company_name }}（盖章）
法定代表人或授权代表：{{ company.legal_representative }}（签字）
日期：{{ commitment_date }}
```

## 3 / Pipeline 实现

入口脚本：`scripts/generate_sgcc_distribution_technical_template_package.py`

### 3.1 数据流图

```
[输入] ~/Downloads/电网工程施工-XX配网工程技术文件/   ← 用户本地，不进仓库
  20 个 .docx (原标书，含真实信息)

  │ (1) extract
  ▼
[中间产物] backend/data/template_generation/sgcc_distribution_technical/   ← .gitignored
  ├── chapters/{chapter_code}.json    (按章拆分，含原始段落+表格)

  │ (2) redact (规则脱敏)
  ▼
  ├── redacted/{chapter_code}.json
  ├── redaction_report.json (脱敏命中记录)

  │ (3) ai_verify (AI 二次校验)
  ▼
  ├── ai_verified/{chapter_code}.json
  ├── ai_verification_log.json (AI 发现的额外泄露)

  │ (4) assemble (docxtpl 占位符注入)
  ▼
  ├── templated/{chapter_code}.json

  │ (5) package (打包为 DOCX)
  ▼
[最终输出] docs/samples/template_import_ready/sgcc_distribution_technical_ch0_1_7_13_16_package/

  │ (6) verify (验收)
  ▼
  ├── package_importer 导入测试
  ├── 敏感字串全局扫描
  └── docxtpl dummy 渲染测试
```

### 3.2 阶段职责

| 阶段 | 模块 | 输入 | 输出 | 关键依赖 |
|---|---|---|---|---|
| 1. extract | `extract.py` | `*.docx` | `chapters/{code}.json` | `python-docx`：按 heading 切章，剥离图片 |
| 2. redact | `redact_rules.py` | `chapters/*.json` | `redacted/*.json` + report | 12 类 regex 规则（公司/项目/手机/身份证/金额/日期/地址等） |
| 3. ai_verify | `ai_verify.py` | `redacted/*.json` | `ai_verified/*.json` | 调 `ai_gateway` (DeepSeek)，识别规则漏过的真实信息 |
| 4. assemble | `assemble.py` | `ai_verified/*.json` | `templated/*.json` | 把脱敏后的"占位文本"按规则替换为 `{{ docxtpl_var }}` |
| 5. package | `package.py` | `templated/*.json` | DOCX + manifest.json | `python-docx`：创建带 heading 的 DOCX |
| 6. verify | pytest | 最终包 | 测试报告 | 调 `package_importer` + 敏感字串扫描 + 渲染测试 |

### 3.3 错误处理

- 任何阶段出错：保留中间产物，记录错误到 `errors.json`，终止后续阶段
- AI 校验发现真实信息：**默认 fail-loud**，要求人工添加规则后重跑
- DOCX 解析异常段落：跳过，记录到 `extraction_warnings.json`，pipeline 继续
- 大文件 (>50MB)：分段流式读取段落，避免 OOM

## 4 / 脱敏规则

### 4.1 敏感字段类别与占位符

| 类别 | 检测规则 | 替换为 |
|---|---|---|
| 公司名（投标人） | 含「有限公司/股份公司/集团公司」等后缀，非「国家电网」等公开实体；维护已知公司白名单+扫描 | `{{ company.company_name }}` |
| 项目编号/招标编号 | regex：纯数字 17 位、字母+数字组合（B005-300009445-00046）、年度框架协议号 | `{{ tender.tender_no }}` / `{{ tender.project_no }}` |
| 项目名称 | 含"工程"+"年份"+"地名"组合 | `{{ tender.project_name }}` |
| 人员姓名 | 中文姓名 2-4 字，紧邻"项目经理"/"技术负责人"等角色词 | `{{ person.full_name }}` 或 `{{ project_manager.full_name }}` |
| 身份证号 | 18 位身份证（含校验位） | `{{ person.id_card }}` |
| 手机号 | regex：`1[3-9]\d{9}` | `{{ person.phone }}`（或 `13800000000`） |
| 邮箱 | regex `[\w.]+@[\w.]+\.(com|cn|net|org)`，排除 example.com | `{{ person.email }}` |
| 详细地址 | 含省/市/区+具体街道编号 | `{{ tender.project_location }}` |
| 金额 | "￥"/"元"/"万元"+数字（合同额、保证金） | `{{ tender.contract_amount }}` |
| 日期 | 具体年月日 | `{{ commitment_date }}` 或 `{{ tender.bid_date }}` |
| 证书编号 | "证书编号:XXX" 格式 | `{{ certificate.cert_no }}` |
| 车辆牌照 | regex：`[京沪津渝...][A-Z][A-Z0-9]{5}` | `{{ vehicle.plate_no }}` |

### 4.2 已知泄露字串校验

对照仓库历史已清理过的真实数据，确保以下 100% 被命中：
- "重庆蓝海电力工程有限责任公司" → 公司名规则
- "24009710307354592" / "24009710312591751" → 招标编号
- "B005-300009445-00046" → 项目编号
- "国网重庆市电力公司 2026..." → 项目名+招标方关联
- 已知的 12 个真实手机号 → 手机号规则

### 4.3 AI 校验 prompt（第 3 阶段）

```
你是数据脱敏审计员。下面是一段被脱敏过的标书章节，请检查是否仍含有：
1. 中国大陆真实公司名（含「有限公司」等后缀；「国家电网有限公司」属于公开实体不算泄露）
2. 真实人名（除虚构占位"张三/李四/王五"外）
3. 手机号 / 身份证号 / 邮箱
4. 招标编号 / 项目编号（含 17 位数字、字母数字混合编号）
5. 具体金额（万元/亿元）
6. 具体地址（省+市+街道编号）

只列出仍存在的泄露，按 JSON 数组返回：
[{"snippet": "命中的原文片段", "category": "company|person|phone|...", "suggested_placeholder": "{{ company.company_name }}"}]

如果完全干净，返回 []。

待审计文本：
<<<{{ chapter_text }}>>>
```

### 4.4 验证机制（第 6 阶段）

1. **静态扫描**：用项目脱敏正则集扫描最终 DOCX 提取文本，必须 0 命中
2. **白名单扫描**：维护已知真实公司/项目/手机号清单（gitignored），逐条扫描 0 命中
3. **diff 报告**：对比原 docx 文字总量 vs 模板文字总量，记录"脱敏覆盖率"
4. **手动 spot-check**：随机抽 10 段最终模板内容人工审阅

**fail-loud 策略**：任何一个验证失败 → 整个 pipeline 退出，必须修规则后重跑，绝不允许带泄露提交。

## 5 / 测试策略

### 5.1 单元测试（`backend/tests/unit/`）

| 测试文件 | 覆盖 | 关键 case |
|---|---|---|
| `test_technical_template_redact_rules.py` | 12 类脱敏规则各自的 regex | 各类正例+反例；身份证校验位；手机号长度边界 |
| `test_technical_template_extract.py` | DOCX 段落+表格+heading 切章 | 章节 heading 识别多格式；表格行列；空段落 |
| `test_technical_template_assemble.py` | 占位符注入 | 占位符不破坏 docxtpl 语法；中文标点处理；嵌套 |
| `test_technical_template_chapter_bindings.py` | 15 章 chapter binding 定义 | chapter_code 唯一；item_type/render_mode 合法 |
| `test_scoring_index_table.py` | 第 0 章表格骨架 | 6 列表头、迭代行结构、空行处理 |
| `test_commitment_letter_template.py` | 第 16 章生成 | 必要占位符存在；通用文字符合行业格式 |

### 5.2 集成测试（`backend/tests/integration/`）

| 测试文件 | 覆盖 |
|---|---|
| `test_technical_template_package_import.py` | 用 `package_importer` 导入生成的 DOCX，验证 15 章正确识别 |
| `test_technical_template_render_with_dummy_materials.py` | 用 dummy materials 渲染整个模板，验证 docxtpl 输出无错、占位符全填 |

### 5.3 Pipeline 集成测试

| 测试 | 覆盖 |
|---|---|
| `test_pipeline_end_to_end.py` | 用最小 fake docx fixture 跑完 6 阶段 pipeline |
| `test_pipeline_sensitive_leak_detection.py` | 注入已知泄露，确保 pipeline 在 verify 阶段 fail-loud |

### 5.4 测试 fixture

`backend/tests/fixtures/technical_template/`：

- `sample_chapter_1_deviation.docx`：1 个表格的偏差表样本
- `sample_chapter_5_2_performance.docx`：业绩表+少量图片
- `sample_chapter_16_commitment.docx`：行业通用承诺函样本
- `known_leaks.txt`：已知应被脱敏的字串清单（用 placeholder，无真实数据）
- `expected_redact_output_ch1.json`：期望的脱敏后 JSON
- `dummy_materials.json`：渲染测试用的伪造资料库数据

**fixture 数据完全用 placeholder**：「测试公司A」、「示例项目X」、`13800000000`、`zhangsan@example.com`，**绝不混入真实标书内容**。

### 5.5 验收测试（生成后）

| 验收 | 工具 |
|---|---|
| DOCX 可打开 | `unzip -t {模板}.docx` |
| 章节数量正确 | 解析 DOCX heading 应得 15 章 |
| 占位符完整 | grep `{{` 至少 N 次 |
| 敏感字串扫描 | `python scripts/scan_sensitive_strings.py` 全 0 命中 |
| package_importer 导入成功 | 跑集成测试 |
| dummy 渲染成功 | 跑集成测试 |

CI 入口：脚本加 `--ci-mode` 仅跑 lint+unit tests，避免 CI 拉历史标书。

## 6 / 风险、边界与已知妥协

### 6.1 已知风险与缓解

| 风险 | 缓解 |
|---|---|
| 单个 docx 过大（6 章 223MB） | extract 阶段流式读取段落，移除图片后总文本应 <10MB |
| python-docx 对复杂样式兼容不完美 | 输出 warnings；人工 spot-check |
| 公司名脱敏漏报（关联实体边界模糊） | `known_real_entities.yaml`（gitignored）+ AI 二次扫描兜底 |
| docxtpl 占位符在中文标点周围被破坏 | 强制占位符周围加空格；测试覆盖中文标点 |
| AI 校验调用失败/超时 | 降级到 deepseek-flash 重试；3 次失败 fail-loud |
| 第 0 章页码无法静态填入 | 模板里页码列用 `{{ row.page | default("待定") }}`，渲染时动态计算 |
| 第 16 章措辞普通 | 接受妥协；用户可后续手动微调 DOCX |

### 6.2 边界情况

| 边界 | 处理 |
|---|---|
| docx 内表格行数极多 | 模板里只保留 1 行占位 + Jinja `{% for %}` 循环 |
| 历史标书章节标题与 TOC 命名不一致 | `chapter_alias_map.yaml` 映射到标准 TOC 章名 |
| 文件存在但内容空 | 模板里仅生成章标题 + 一行占位说明 |
| 投标人公司名重复多次 | 统一替换为 `{{ company.company_name }}` |
| 同类资料库有多个对象 | Jinja `{% for %}` 循环 + 表格行迭代 |

### 6.3 接受的妥协

1. **图片完全跳过**：6 章 / 5.2 章里的扫描件、人员照片、组织图全部丢弃，模板里只有占位符提示。系统侧的图片资料注入支持不在本任务范围
2. **第 0 章评分项数据来源不在本任务内**：模板只交付表格骨架，行数据由后续从评分细则 xlsx 解析或人工录入
3. **生成结果不可逆**：未来若历史标书更新，需重跑 pipeline 生成新版本，不支持增量更新
4. **不支持多投标主体**：模板假设 1 个投标人主体，联合体投标的多公司表述已在 business 包处理
5. **AI 脱敏不能保证 100% 召回**：最终安全屏障靠已知泄露字串扫描 + 测试 fail-loud

### 6.4 何时需要人工介入

| 场景 | 介入 |
|---|---|
| AI 校验报告非空 | 添加规则到 `redact_rules.py`，重跑 pipeline |
| 验证阶段全局扫描命中 | 同上 |
| package_importer 测试失败 | 调整 heading 样式或 chapter_code 映射 |
| docxtpl 渲染测试失败 | 调整占位符语法或 dummy_materials.json |
| 用户审 DOCX 发现文字不通顺 | 直接编辑 DOCX 提交 |

## 附录 A：与项目 TOC 的同步更新

本任务执行后需同步更新 `docs/samples/国网公司配网工程技术标目录.md`：

| 章号 | 旧名 | 新名 |
|---|---|---|
| 6 | 项目团队情况 | 现场管理机构设置 |

其他章节名保持现有 TOC 不变。

## 附录 B：交付清单

**新增文件**：

- `scripts/generate_sgcc_distribution_technical_template_package.py`（入口）
- `scripts/sgcc_technical_template/extract.py`
- `scripts/sgcc_technical_template/redact_rules.py`
- `scripts/sgcc_technical_template/ai_verify.py`
- `scripts/sgcc_technical_template/assemble.py`
- `scripts/sgcc_technical_template/package.py`
- `scripts/sgcc_technical_template/chapter_bindings.py`
- `docs/samples/template_import_ready/sgcc_distribution_technical_ch0_1_7_13_16_package/`（产物目录）
- `backend/tests/fixtures/technical_template/`（fixture）
- `backend/tests/unit/test_technical_template_*.py`（单测）
- `backend/tests/integration/test_technical_template_*.py`（集成）

**修改文件**：

- `docs/samples/国网公司配网工程技术标目录.md`（第 6 章改名）
- `.gitignore`（确保 `backend/data/template_generation/` 已被排除）
