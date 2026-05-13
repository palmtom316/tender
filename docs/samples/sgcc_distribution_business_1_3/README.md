# 国网配网工程商务标第 1-3 章 DOCX 模板

来源样章：用户桌面提供的第 1/2/3 章 DOCX。

处理原则：

- 保留样章章节标题、正文结构和基础表格样式。
- 移除旧公司名和旧截图/证照扫描件。
- 可变内容改为 docxtpl/Jinja 占位符。
- 截图、营业执照等证明材料位置改为“资料位”文字占位，后续由资料库/附件库绑定。

## 主要占位符

- `{{ tender.purchaser_name }}`：采购人/招标人名称。
- `{{ company.company_name }}`：应答人名称。
- `{{ deviation_table.rows[0].tender_item_no }}`：商务偏差表采购文件条目号。
- `{{ deviation_table.rows[0].tender_clause }}`：商务偏差表采购文件条款。
- `{{ deviation_table.rows[0].response_clause }}`：商务偏差表应答文件条款。
- `{{ deviation_table.rows[0].deviation_note }}`：商务偏差说明。
- `{{ asset.business_license_scan }}`：营业执照扫描件资料位。
- `{{ asset.credit_china_report }}` 等：无违法失信承诺函查询截图/报告资料位。

## 文件

1. `1.商务偏差表.docx`
2. `2.关于无违法失信行为的承诺函.docx`
3. `3.企业营业执照（或事业单位法人证书或其他组织登记证书）.docx`
