# 国网配网工程商务标 1-24 章统一模板包

- 产物类型：单 DOCX 模板包（适配当前系统导入器）
- 合并来源：`docs/samples/sgcc_distribution_business_1_3/` + `docs/samples/sgcc_distribution_business_4_24/`
- 总章节文件数：60（含 1-24 章及其子章节）
- 导入器约束：当前 `package_importer` 仅支持单个 DOCX 文件作为一个模板包。

## 文件

- `国网配网工程商务标1-24章.docx`：统一商务标模板包，系统显示名为“国网配网工程商务标”。
- `manifest.json`：源章节清单。

## 使用建议

1. 将本目录映射进 `TEMPLATE_IMPORT_ROOTS` 允许目录。
2. 通过 `/api/template-packages/import` 或后端导入工具导入本目录。
3. 导入后再在系统内补章节绑定/资料位绑定规则。
