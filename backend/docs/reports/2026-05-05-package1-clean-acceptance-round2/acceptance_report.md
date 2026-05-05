# Tender AI Extraction Acceptance Report

- Generated at: `2026-05-05T15:15:25.738698+00:00`
- Test project: `包1_AI验收_20260505_round2_retry`
- Project ID: `74d53d73-d8eb-4a62-a31c-be042ca1283e`
- Tender document ID: `ac624e82-5e28-4683-957a-60e2fa9a28a8`
- AI extraction run ID: `76d1ac73-f55a-41c2-84ea-937ef4d64260`

## Environment

- Base URL: `http://127.0.0.1:8000/api`
- Gateway URL: `http://127.0.0.1:8100/openapi.json`
- Input ZIP: `/Users/palmtom/Projects/tender/backend/data/tender_documents/09df90e3-9b31-4855-9345-ffe747a94f1e/3cfbf0f886ca0a13/original/包1_完整招标文件_REDACTED.zip`
- Model policy: `v4_flash_then_pro`
- Docker reset: `True`
- Redis flushed: `True`

## Speed

- Upload wall time: `0.00s`
- Parse wall time: `0.00s`
- AI extraction wall time: `0.00s`
- End-to-end wall time: `0.00s`
- Parse chunks: `2387`
- Parsed files: `20`; failed `0`; skipped `8`
- Run status: `partial`
- Total batches: `118`; succeeded `114`; failed `2`; skipped `2`
- Extracted requirements: `757`
- Input tokens: `504893`; output tokens: `148154`
- Batch latency avg/p50/p95/max: `21548.34 / 15172 / 70162 / 156094 ms`

## Batch Mix

- Status counts: `{"succeeded": 114, "skipped": 2, "failed": 2}`
- Model counts: `{"deepseek-v4-flash": 112, "deepseek-v4-pro": 6}`
- Quality policy counts: `{"table_or_critical_extract": 112, "fast_prefilter": 2, "pro_review": 4}`
- Stage counts: `{"primary": 118}`
- Task type counts: `{"extract_tender_requirements": 118}`
- Reasoning effort counts: `{"none": 112, "high": 4, "max": 2}`
- Fast prefilter filtered batches: `0`
- Stage 2 follow-up batches: `0`
- Stage 2 follow-up files: `[]`
- Average tokens per persisted requirement batch: `1458.86`

## Quality

- Requirement count: `757`
- Category counts: `{"business": 41, "project_team": 26, "qualification": 135, "performance": 5, "scoring": 43, "special": 23, "format": 109, "contract": 124, "project_info": 14, "technical": 100, "schedule": 51, "veto": 86}`
- Extraction method counts: `{"ai": 757}`
- Review status counts: `{"pending": 757}`
- Veto count: `197`
- Hard constraint count: `737`
- Requires human confirm count: `313`
- Top source files by requirement count: `{"包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件（服务）.docx": 241, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件11：发包人要求（基建可研设计.设计.施工.监理）.docx": 158, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件（施工）.docx": 151, "包1_完整招标文件_REDACTED.zip/合同文件.zip/合同专用条款文件.zip/合同专用条款其他文件202601081421271.docx": 113, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.docx": 44, "包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx": 23, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件5：推荐中标和排序规则.docx": 7, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/附件2：专用资格要求.xlsx": 4, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件7：技术评分细则.xlsx": 4, "包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件3：报价方式、最高限价及保证金应缴一览表.xlsx": 2}`

## Sample Outputs

### veto

- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件3：报价方式、最高限价及保证金应缴一览表.xlsx` `sheet:报价方式和最高限价` 投标报价折扣比例不得超过最高限价0.98 | 所有分包的投标报价均采用折扣比例方式，投标人所报折扣比例不得超过0.98，否则将被否决。
- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件3：报价方式、最高限价及保证金应缴一览表.xlsx` `sheet:保证金应缴一览表` 投标保证金必须按分标足额缴纳 | 投标人须按照“保证金应缴一览表”中对应分标的保证金金额缴纳投标保证金，金额从0万元至7万元不等，未足额缴纳可能导致否决。
- `包1_完整招标文件_REDACTED.zip/合同文件.zip/合同专用条款文件.zip/合同专用条款其他文件202601081421271.docx` `paragraph:85` 使用劣质材料或欺骗行为的终止权 | 如乙方使用劣质、不合格或不符合要求的材料，或有欺骗行为等严重违约行为，甲方有权终止本合同及基于本合同就具体项目另行签订的合同并追究责任。
- `包1_完整招标文件_REDACTED.zip/合同文件.zip/合同专用条款文件.zip/合同专用条款其他文件202601081421271.docx` `paragraph:118` 资质造假或能力不足导致合同失效 | 10.4 乙方不具备相关项目实施能力的，或资质证明存在造假行为的，甲方有权拒绝与其签订就具体项目的正式服务合同，同时本合同失效。由此造成甲方损失的，由乙方承担。
- `包1_完整招标文件_REDACTED.zip/合同文件.zip/合同专用条款文件.zip/合同专用条款其他文件202601081421271.docx` `paragraph:345` 禁止转包或违法分包 | 承包人必须按照国家和国家电网有限公司相关规定，不得转包或违法分包。在承包人承担的工程及其负责管理的范围内所发生的设备、人身伤亡事故、交通事故、电网事故，其责任和由此发生的一切费用均由承包人负责。

### qualification

- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/附件2：专用资格要求.xlsx` `sheet:专用资格要求` 电网工程施工-XX居供改造 所有包 专用资质要求 | （1）具有有效的安全生产许可证；（2）具有建设行政主管部门核发的电力工程施工总承包三级及以上或输变电工程专业承包三级及以上资质；（3）具有电力监管机构核发的《承装（修、试）电力设施许可证》，许可范围包含三级（10千伏以下）及以上承装、承修、承试。
- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.docx` `paragraph:14` 须取得有效许可证和强制认证证书 | 取得国家法律、法规、规章规定的有效许可证。取得招标文件要求的国家强制认证证书。
- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.docx` `paragraph:16` 不良行为处理期内投标将被否决 | 根据《国家电网有限公司供应商关系管理办法》，投标人存在导致暂停或取消中标资格的不良行为且在处理有效期内，或触发安全及质量重大问题“熔断机制”的，其投标将被否决。即使投标截止日不存在，中标通知书到达前出现上述情况，招标人有权取消其中标资格。
- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.docx` `paragraph:13` 单位负责人不得为同一人或存在控股管理关系 | 法定代表人或单位负责人为同一人或者存在控股、管理关系的不同单位，不得参加同一标包投标或者未划分标包的同一采购项目投标。
- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购招标公告.docx` `paragraph:17` 不得被列为失信被执行人 | 投标人不得被人民法院列为失信被执行人，不得被“信用中国”网站列入严重失信主体名单。即使开标当日未出现，中标通知书到达前出现上述情形，招标人有权取消其中标资格。

### scoring

- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件6：商务评分细则.xlsx` `sheet:FWSW02` 不良行为处理限制 | 至本项目投标截止日，存在《国家电网有限公司供应商关系管理办法》中规定的不良行为，且最近一次受到供应商不良行为处理解除之日距离投标截止日1年以内（含），扣15分；其中存在行贿行为的，扣30分。无不良行为或解除超过1年不扣分。
- `包1_完整招标文件_REDACTED.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件.zip/REDACTED2026年新增第一次服务框架协议（自主执行）公开招标采购文件/附件6：商务评分细则.xlsx` `sheet:FWSW01` 不良行为处理限制 | 至本项目投标截止日，存在《国家电网有限公司供应商关系管理办法》中规定的不良行为，且最近一次受到供应商不良行为处理解除之日距离投标截止日1年以内（含），扣15分；其中存在行贿行为的，扣30分。无不良行为或解除超过1年不扣分。
- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx` `paragraph:22` 报价包含完成所有工作内容的各项费用 | 投标人的报价为在工程项目建设期和保修期内，完成投标文件规定的工作内容的各项费用，包括人工、材料、机械、设备、施工管理费(包括采用工程项目管理系统、编制声像资料等相关费用等)、各种施工措施费、维护照管费、利润、税金等。同时投标人的报价还应考虑办理施工许可证和按规定办理的各种施工手续以及为开展上述工作根据规定(包括地方文件规定)所缴纳的各种税费。
- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx` `paragraph:18` 安全文明施工费不纳入折扣下浮 | 赔偿费用经甲方、监理单位签证后按实计算，安全文明施工费不纳入折扣比例下浮范围。
- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx` `paragraph:21` 考虑物价上涨因素 | 投标人应考虑自项目开工至竣工验收期间物价上涨（包括防汛期间可能发生的砂、碎石、片石等地方建材的季节性特殊涨价）等因素以及由此引起的费用变动。

### technical

- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx` `paragraph:38` 遵守现行管理办法要求 | 严格遵守现行的管理办法，主要适用但并不仅限于下列规定：REDACTED实施方案、重庆市居民住宅小区供配电设施配置指导意见（试行）、REDACTED居民供电设施改造政府专项资金项目管理工作规范（试行）、国家电网有限公司10（20）千伏及以下配电网工程项目管理规定、国家电网有限公司关于开展配网工程施工转型升级三年行动的通知、国家电网有限公司、囯网重庆市电
- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx` `paragraph:32` 安全文明施工措施要求 | 投标人在施工现场必须要有常规的安全文明施工措施及成品保护措施，应满足国家及电力行业对工程建设安全文明施工的有关规定要求。
- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/2026年居配施工技术规范书.docx` `paragraph:36` 数字化管控系统应用要求 | 严格按照公司管理要求，在工程建设各环节应用全过程数字化管控系统，实现全流程线上管控，施工单位要在建档立卡、开工报审、作业计划、现场施工、验收申请等环节全面开展应用。
- `包1_完整招标文件_REDACTED.zip/包1_技术规范书_REDACTED.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)806551.zip/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED)/REDACTED_2026年居民供电设施改造项目施工框架采购(REDACTED).docx` `table:1` 技术规范书响应要求 | 投标人须对2026年居配施工技术规范书（2026年居配施工技术规范书.docx）中的项目需求值或表述进行响应，并在投标文件中提供投标人保证值。
- `包1_完整招标文件_REDACTED.zip/合同文件.zip/合同专用条款文件.zip/合同专用条款其他文件202601081421271.docx` `paragraph:84` 材料和设备质量标准及责任 | 乙方提供的材料和设备必须达到国家及行业有关质量标准，对其质量负完全责任，如有不合格，乙方必须负责更换并承担费用，工期不予顺延。

### commercial

- No samples captured
