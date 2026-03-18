
# AI辅助投标系统 PRD v1.1（修订版）
## 技术标智能编制系统

版本：v1.1（专家评审修订版）
范围：仅技术标，不包含经济标，不包含复杂审计系统

---

# 一、系统定位

本系统用于 **建设工程技术标编制辅助**，目标：

1. 降低废标风险
2. 自动提取招标文件要求
3. 辅助生成施工组织设计
4. 自动检查响应性与一致性
5. 快速导出标准化技术标

核心原则：

- AI 负责辅助
- 人工负责最终确认
- 系统确保不遗漏关键约束

---

# 二、核心业务风险控制

## 2.1 否决项（废标项）防线

AI 可以提取，但 **必须人工确认**。

流程：

```
招标文件解析
↓
AI识别否决项
↓
人工逐条确认
↓
系统允许导出
```

### 数据库新增字段

表：`project_requirement`

新增：

```
requirement_category
ENUM(
 'disqualify',
 'qualification',
 'personnel',
 'performance',
 'technical'
)
```

新增：

```
human_confirmed BOOLEAN
confirmed_by
confirmed_at
```

---

## 2.2 资格与业绩要求

系统必须识别评分表中的：

- 企业资质
- 项目经理资格
- 企业类似业绩
- 人员资格
- 技术方案要求

这些字段将写入：

```
project_requirement
```

AI 若无法自动填充，将生成：

```
待确认项
```

---

# 三、技术架构

## 架构原则

- AI 只做理解和生成
- 数据库存真源
- 检索使用 BM25 + 同义词
- Agent 使用 Workflow 形式

---

## 系统架构

```
Frontend
↓
API Gateway
↓
Workflow Engine (Agent Orchestrator)
↓
Tool Registry / Skill Registry
↓
Services
    parse-service
    extract-service
    search-service
    review-service
    export-service
↓
Infrastructure
    PostgreSQL
    OpenSearch
    MinIO
    Redis
↓
AI Gateway
↓
国产模型 API
```

---

# 四、Agent / Workflow 设计

系统使用 **固定工作流 Agent**

## 4.1 项目解析 Agent

任务：

- 解析招标文件
- 提取项目事实
- 提取否决项

调用工具：

```
parse_document
extract_project_facts
extract_outline
save_project_constraints
```

---

## 4.2 规范入库 Agent

任务：

- 解析规范 PDF
- 构建条款树

工具：

```
parse_document
build_clause_tree
tag_clauses
index_standard
```

---

## 4.3 检索 Agent

为章节准备证据：

```
search_tender_requirements
search_sections
search_clauses
search_company_docs
```

---

## 4.4 写作 Agent

任务：

- 生成章节提纲
- 生成正文

---

## 4.5 审校 Agent

检查：

- 项目事实一致性
- 招标要求覆盖
- 规范引用

---

## 4.6 导出 Agent

输出：

- docx
- pdf

---

# 五、检索系统

采用：

```
OpenSearch BM25
+ 行业同义词词典
```

示例：

```
基坑开挖,土方开挖
三通一平,场地准备
脚手架,外架
```

---

# 六、文档解析

解析工具：

```
MinerU
```

解析内容：

- 标题树
- 条款
- 表格
- 页码

---

## 表格纠错机制

新增 UI：

```
解析表格
↓
人工修正
↓
覆盖保存
```

新增表：

```
document_table_override
```

---

# 七、Word导出策略

导出方式：

```
Word模板 + 占位符替换
```

不做：

- 动态样式生成
- 复杂编号控制

示例模板：

```
{{SECTION_安全文明施工}}
{{SECTION_施工进度计划}}
```

技术实现：

```
docxtpl
```

---

# 八、AI模型策略

推荐模型策略（统一口径）：

主模型：

```
DeepSeek
```

备模型：

```
Qwen
```

可选扩展：

```
GLM（或其他 OpenAI-compatible / Claude-compatible providers；BYOK）
```

任务分工（主备一致，按任务 profile 固定；失败/超时自动 fallback）：

|任务|主模型|备模型|
|---|---|---|
结构化抽取|DeepSeek|Qwen|
长文档理解|DeepSeek|Qwen|
章节生成|DeepSeek|Qwen|
审校|DeepSeek|Qwen|

---

## AI参数限制

抽取任务：

```
temperature = 0
top_p = 0.1
```

生成任务：

```
temperature = 0.3
```

---

# 九、页面设计

一期页面：

1. 项目列表
2. 招标文件上传
3. 解析结果页
4. 否决项人工核验页
5. 章节编辑页
6. 审校结果页
7. 导出页

---

# 十、实施排期（10周）

### Week1

基础架构

### Week2

文档上传与存储

### Week3

MinerU解析

### Week4

解析规则与表格清洗

### Week5

规范库构建

### Week6

检索系统

### Week7

章节生成

### Week8

审校系统

### Week9

导出模块（模板替换）

### Week10

系统联调

---

# 十一、一期交付能力

系统将具备：

- 招标文件解析
- 否决项识别
- 技术标章节生成
- 规范引用
- 一致性检查
- Word/PDF导出

---

# 十二、总结

本系统的设计原则：

1. AI辅助，不替代人工
2. 关键风险人工确认
3. 检索优先结构化
4. 排版依赖模板
5. 工作流确定性执行


---

# 十三、技术设计包（Engineering Design Pack）

本章节用于指导开发团队直接进入实现阶段，包括：
- 数据库 DDL
- Docker Compose 架构
- 后端服务目录结构
- OpenSearch 索引设计
- AI Gateway 与 Tool/Skill Schema

---

## 13.1 数据库 DDL（核心表）

### project

```
CREATE TABLE project (
  id SERIAL PRIMARY KEY,
  project_name TEXT,
  owner_name TEXT,
  created_at TIMESTAMP,
  status TEXT
);
```

### project_requirement

```
CREATE TABLE project_requirement (
  id SERIAL PRIMARY KEY,
  project_id INT,
  requirement_text TEXT,
  requirement_category TEXT,
  human_confirmed BOOLEAN DEFAULT FALSE,
  confirmed_by TEXT,
  confirmed_at TIMESTAMP
);
```

### section

```
CREATE TABLE section (
  id SERIAL PRIMARY KEY,
  project_id INT,
  section_name TEXT,
  section_content TEXT,
  created_at TIMESTAMP
);
```

### chapter_draft

```
CREATE TABLE chapter_draft (
  id SERIAL PRIMARY KEY,
  project_id INT,
  section_name TEXT,
  draft_text TEXT,
  human_confirmed BOOLEAN DEFAULT FALSE
);
```

### review_issue

```
CREATE TABLE review_issue (
  id SERIAL PRIMARY KEY,
  project_id INT,
  section_name TEXT,
  issue_text TEXT,
  severity TEXT
);
```

---

## 13.2 Docker Compose 架构

```
services:

  backend:
    build: ./backend
    ports:
      - "8000:8000"

  postgres:
    image: postgres:15

  redis:
    image: redis:7

  opensearch:
    image: opensearchproject/opensearch:2

  minio:
    image: minio/minio

  ai-gateway:
    build: ./ai_gateway
```

---

## 13.3 后端目录结构

推荐 FastAPI 项目结构：

```
backend/
 ├── api/
 ├── services/
 │   ├── parse_service
 │   ├── search_service
 │   ├── review_service
 │   ├── export_service
 ├── agents/
 ├── tools/
 ├── skills/
 ├── models/
 ├── db/
 └── main.py
```

---

## 13.4 OpenSearch 索引设计

### section_index

字段：

```
section_name
content
project_type
tags
```

### clause_index

字段：

```
clause_id
standard_name
clause_text
tags
```

### 同义词词典

```
基坑开挖,土方开挖
三通一平,场地准备
脚手架,外架
模板工程,支模
```

---

## 13.5 AI Gateway

AI Gateway 负责：

- 模型路由
- API Key 管理
- function calling
- retry / timeout
- prompt 管理

接口示例：

```
POST /ai/chat

{
 "task_type": "generate_section",
 "model": "qwen",
 "messages": []
}
```

---

## 13.6 Tool Schema 示例

```
{
 "name": "search_clauses",
 "description": "检索规范条款",
 "parameters": {
   "query": "string"
 }
}
```

---

## 13.7 Skill 示例

```
generate_section:

steps:
 - get_project_facts
 - search_clauses
 - search_sections
 - call_llm
 - save_draft
```

---

## 13.8 Agent Orchestrator

工作流执行顺序：

```
解析招标文件
↓
提取项目事实
↓
检索证据
↓
生成章节
↓
审校
↓
导出
```


---

# 十四、完整数据库设计（核心结构示例）

以下为一期推荐数据库结构（约 20+ 表的核心子集）。

## 14.1 project

```
CREATE TABLE project (
 id SERIAL PRIMARY KEY,
 project_name TEXT,
 owner_name TEXT,
 tender_deadline TIMESTAMP,
 status TEXT,
 created_at TIMESTAMP DEFAULT now()
);
```

## 14.2 project_file

```
CREATE TABLE project_file (
 id SERIAL PRIMARY KEY,
 project_id INT,
 file_name TEXT,
 file_type TEXT,
 storage_path TEXT,
 uploaded_at TIMESTAMP
);
```

## 14.3 document

```
CREATE TABLE document (
 id SERIAL PRIMARY KEY,
 project_id INT,
 source_file_id INT,
 doc_type TEXT,
 parsed BOOLEAN DEFAULT FALSE
);
```

## 14.4 document_section

```
CREATE TABLE document_section (
 id SERIAL PRIMARY KEY,
 document_id INT,
 section_title TEXT,
 content TEXT,
 page_no INT
);
```

## 14.5 document_table

```
CREATE TABLE document_table (
 id SERIAL PRIMARY KEY,
 document_id INT,
 table_json JSONB
);
```

## 14.6 document_table_override

```
CREATE TABLE document_table_override (
 id SERIAL PRIMARY KEY,
 table_id INT,
 corrected_json JSONB,
 corrected_by TEXT,
 corrected_at TIMESTAMP
);
```

## 14.7 project_requirement

```
CREATE TABLE project_requirement (
 id SERIAL PRIMARY KEY,
 project_id INT,
 requirement_text TEXT,
 requirement_category TEXT,
 human_confirmed BOOLEAN DEFAULT FALSE,
 confirmed_by TEXT,
 confirmed_at TIMESTAMP
);
```

## 14.8 project_fact

```
CREATE TABLE project_fact (
 id SERIAL PRIMARY KEY,
 project_id INT,
 fact_key TEXT,
 fact_value TEXT
);
```

## 14.9 section_template

```
CREATE TABLE section_template (
 id SERIAL PRIMARY KEY,
 template_name TEXT,
 section_name TEXT,
 template_text TEXT
);
```

## 14.10 chapter_draft

```
CREATE TABLE chapter_draft (
 id SERIAL PRIMARY KEY,
 project_id INT,
 section_name TEXT,
 draft_text TEXT,
 human_confirmed BOOLEAN DEFAULT FALSE,
 created_at TIMESTAMP
);
```

## 14.11 review_issue

```
CREATE TABLE review_issue (
 id SERIAL PRIMARY KEY,
 project_id INT,
 section_name TEXT,
 issue_text TEXT,
 severity TEXT
);
```

## 14.12 export_record

```
CREATE TABLE export_record (
 id SERIAL PRIMARY KEY,
 project_id INT,
 export_file TEXT,
 created_at TIMESTAMP
);
```

---

# 十五、OpenSearch 工程行业同义词库（示例）

为解决 BM25 词汇鸿沟问题，配置工程行业同义词词典。

## 示例词条

```
基坑开挖,土方开挖
三通一平,场地准备
脚手架,外架
模板工程,支模
混凝土浇筑,混凝土施工
钢筋绑扎,钢筋安装
安全文明施工,安全管理
施工进度计划,工期安排
质量保证措施,质量管理措施
临时用电,施工用电
```

## OpenSearch Synonym Filter 示例

```
analysis:
  filter:
    construction_synonym:
      type: synonym
      synonyms_path: synonyms.txt
```

## 一期建议

构建约：

```
1000+ 工程行业同义词
```

来源包括：

- 建筑工程术语词典
- 施工规范目录
- 招标文件常用术语
- 企业历史标书

---

# 十六、同义词库维护机制

新增维护表：

```
synonym_dictionary
```

示例：

```
CREATE TABLE synonym_dictionary (
 id SERIAL PRIMARY KEY,
 term TEXT,
 synonym TEXT,
 source TEXT
);
```

维护方式：

1. 初始人工导入
2. 检索日志分析新增
3. AI辅助发现潜在同义词
4. 定期人工审核

---

# 十七、最终系统能力总结

系统上线后将具备：

- 招标文件结构化解析
- 否决项识别与人工确认
- 技术标章节AI生成
- 规范条款引用
- 一致性与响应性检查
- Word模板导出
- 工程行业同义词增强检索
- 表格人工纠错机制
