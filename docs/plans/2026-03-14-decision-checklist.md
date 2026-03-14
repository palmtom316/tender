# AI辅助投标系统一期待拍板清单

## 使用说明

本清单用于跟踪一期实施前仍需业务或管理侧确认的关键决策。

建议状态：

- `pending`：待确认
- `approved`：已确认
- `rejected`：已否决
- `deferred`：延期到后续阶段

建议每项补充：

- 决策人
- 确认日期
- 结论说明

## 决策清单

| ID | 决策项 | 推荐值 | 影响范围 | 最晚决策时间 | 不决风险 | 状态 |
|---|---|---|---|---|---|---|
| D01 | MinerU 文件接入方式 | 后端申请 MinerU 上传链接并直传文件，MinIO 仅留档 | 上传、解析、对象存储、安全策略 | Week 1 | 解析链路无法跑通 | approved |
| D02 | 云模型主备供应商 | 主模型 `DeepSeek`，备选 `Qwen`；AI Gateway 兼容 `ccswitch` 提供的 OpenAI 与 Claude 模型接入 | AI Gateway、章节生成、审校稳定性 | Week 1 | `ai-gateway` 无法落配置，联调阻塞 | approved |
| D03 | API Key 管理归属 | 允许前端录入 API Key，但只允许服务端代理 BYOK；开发环境可用，测试/生产环境默认平台托管，禁止前端直连上游模型 | 安全、部署、运维、调试效率 | Week 1 | 密钥泄露或联调方式混乱 | approved |
| D04 | 用户角色模型 | 一期采用 `项目编辑 / 复核人 / 管理员` 三角色 | 上传、确认、导出、模板管理 | Week 2 | 人工确认与导出权限无法闭环 | approved |
| D05 | 否决项确认责任人 | `项目编辑` 可先确认，导出前必须由 `复核人` 或 `管理员` 二次确认 | 导出门禁、审计追踪 | Week 2 | 门禁规则无法落地 | approved |
| D06 | 导出模板来源 | 一期先使用 1 套默认技术标 `docx` 模板，来源于现有常用 Word 样板，原件需在 Week 2 前补齐 | 导出服务、模板占位符、验收 | Week 2 | Week 9 导出能力延期 | approved |
| D07 | 模板占位符规范 | 同时支持章节名占位符与章节编码占位符，内部以章节编码为稳定主键 | 导出服务、章节命名、模板维护 | Week 2 | 导出模板与章节无法对齐 | approved |
| D08 | 一期样本项目 | 至少确定 2-3 份真实招标文件 + 1 套期望导出样例 | 解析、检索、生成、审校、UAT | Week 1 | 无法做真实验收 | pending |
| D09 | 规范库首批来源 | 由业务侧先手工整理一批高频规范 PDF 入库 | 规范入库、检索、生成证据 | Week 3 | Week 5-6 检索效果不稳定 | approved |
| D10 | 同义词库初始规模 | 一期先做 `100-200` 条高频种子同义词 | OpenSearch、检索命中率 | Week 4 | 词库建设拖慢主链路 | approved |
| D11 | 审校门禁等级 | `P0/P1` 阻断导出，`P2/P3` 仅提示 | 审校页、导出页、验收规则 | Week 6 | 导出门禁反复返工 | approved |
| D12 | 文件保留周期 | 一期默认长期保留，不做自动清理 | 存储、审计、删除策略 | Week 6 | 存储策略与合规不清晰 | approved |
| D13 | 测试/生产环境拓扑 | 开发和测试先单机 Compose，生产再视规模决定是否拆机 | 运维、部署脚本、环境变量 | Week 3 | 环境策略反复变更 | approved |
| D14 | 对外访问域名与 HTTPS | 测试环境先用 `IP + 端口`，域名与 HTTPS 后续补齐 | 前端、接口联调、运维入口 | Week 3 | 外部 API 集成异常 | approved |
| D15 | OpenSearch 安全模式切换时点 | 本地开发关闭安全插件，进入共享测试环境前开启 TLS/Auth | 检索服务、运维、安全 | Week 4 | 共享环境存在安全风险 | approved |
| D16 | 人工修表范围 | 一期只支持整张表 JSON 覆盖，不做单元格级编辑和版本对比 | 解析结果页、表格纠错机制 | Week 4 | UI 与数据模型复杂度失控 | approved |
| D17 | 章节生成范围 | 一期尽量全量生成所有技术标章节正文 | 写作 Agent、模板、验收 | Week 5 | 生成范围失控，工期膨胀 | approved |
| D18 | 企业知识库来源 | 接入少量精选历史标书作为参考知识库，不接全量历史标书库 | 检索 Agent、生成质量 | Week 5 | 数据准备成为主阻塞项 | approved |

## 建议先后顺序

### 第一批，必须本周定

- D01 MinerU 文件接入方式
- D03 API Key 管理归属
- D08 一期样本项目

### 第二批，基础流程定型前要定

- 第二批已完成确认

### 第三批，进入联调前要定

- 第三批已完成确认

## 当前建议的默认结论

如果短期内你不逐项确认，我建议按下面默认值推进：

- D01：后端直传 MinerU 上传链接
- D02：DeepSeek 主、Qwen 备，兼容 ccswitch 的 OpenAI 与 Claude 模型
- D03：前端可录入 API Key，但只允许服务端代理 BYOK；测试/生产环境默认平台托管
- D04：项目编辑 / 复核人 / 管理员
- D05：项目编辑可先确认，导出前需复核人或管理员二次确认
- D06：先用 1 套默认技术标模板，Week 2 前补齐原始样板
- D07：同时支持 `{{SECTION_章节名}}` 和 `{{SECTION_S01}}`，内部以编码为主
- D08：先选 2 份真实项目做 UAT
- D09：业务侧先手工整理首批高频规范 PDF
- D10：先做 100-200 条种子同义词
- D11：P0/P1 阻断导出，P2/P3 提示
- D12：默认长期保留，不做自动清理
- D13：开发和测试先单机 Compose
- D14：测试环境先用 IP + 端口
- D15：本地关安全插件，共享测试前开启 TLS/Auth
- D16：只支持整张表 JSON 覆盖
- D17：尽量全量生成所有技术标章节正文
- D18：接入少量精选历史标书作为参考知识库

## 与现有文档的关系

- 技术选型见 [2026-03-14-technical-stack-design.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-technical-stack-design.md)
- 实施计划见 [2026-03-14-ai-tender-v1-implementation-plan.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-ai-tender-v1-implementation-plan.md)
- MinerU 异步解析设计见 [2026-03-14-mineru-async-parse-design.md](/Users/palmtom/Projects/tender/docs/plans/2026-03-14-mineru-async-parse-design.md)
