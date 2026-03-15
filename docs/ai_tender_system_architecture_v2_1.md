# AI辅助投标系统 架构设计 2.1（工程实施版）

版本：System Architecture 2.1  
范围：技术标编制系统  
部署：局域网 Docker / Docker Compose  
模型：BYOK 国产商业模型 API（Qwen / DeepSeek / GLM）

约束条件：
- 不使用 Embedding
- 不使用 Rerank
- 检索基于 OpenSearch BM25 + 同义词 + 结构化过滤
- Agent 实现为 Workflow Engine
- 一期只做技术标，不做经济标
- 复杂审计、审批、经营管理不纳入一期

---

# 一、目标与实施原则

## 1.1 建设目标

系统需要实现以下能力：

1. 招标文件、规范、优秀标书、历史标书的结构化入库
2. 否决项、项目事实、章节要求的抽取与人工确认
3. 基于章节 / 条款 / 标题路径的精准检索
4. 基于证据包的章节级 AI 生成
5. 规则审校 + 模型审校 + 人工确认
6. 基于 Word 模板的 docx / pdf 导出

## 1.2 工程原则

1. **结构化优先于生成**
2. **规则优先于模型兜底**
3. **Workflow 优先于自由 Agent**
4. **人工确认优先于自动放行**
5. **追踪、回放、评估从一期就要具备**

---

# 二、总体工程架构

```text
浏览器
  ↓
Nginx / API Gateway
  ↓
Backend API（FastAPI）
  ↓
Workflow Engine / Tool Registry / AI Gateway
  ↓
---------------------------------------------------
| Parse Service | Extract Service | Search Service |
| Write Service | Review Service  | Export Service |
---------------------------------------------------
  ↓
-----------------------------------------------
| PostgreSQL | OpenSearch | MinIO | Redis      |
-----------------------------------------------
  ↓
外部模型 API（Qwen / DeepSeek / GLM）
```

---

# 三、Docker Compose 架构

## 3.1 服务清单

建议一期 Docker Compose 直接部署以下服务：

- `nginx`
- `frontend`
- `backend`
- `worker-workflow`
- `worker-io`
- `worker-gpu`（如 MinerU 需要 GPU）
- `postgres`
- `redis`
- `opensearch`
- `minio`
- `ai-gateway`

## 3.2 Compose 示例

```yaml
version: "3.9"

services:
  nginx:
    image: nginx:1.27
    ports:
      - "80:80"
    volumes:
      - ./deploy/nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - frontend
      - backend

  frontend:
    build: ./frontend
    restart: unless-stopped

  backend:
    build: ./backend
    env_file:
      - .env
    depends_on:
      - postgres
      - redis
      - opensearch
      - minio
    restart: unless-stopped

  worker-workflow:
    build: ./backend
    command: celery -A app.workers.celery_app worker -Q workflow_tasks -l info
    env_file:
      - .env
    depends_on:
      - redis
      - postgres
    restart: unless-stopped

  worker-io:
    build: ./backend
    command: celery -A app.workers.celery_app worker -Q io_tasks -l info
    env_file:
      - .env
    depends_on:
      - redis
      - postgres
      - opensearch
    restart: unless-stopped

  worker-gpu:
    build: ./backend
    command: celery -A app.workers.celery_app worker -Q gpu_tasks -l info
    env_file:
      - .env
    depends_on:
      - redis
      - minio
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: tender
      POSTGRES_USER: tender
      POSTGRES_PASSWORD: tender
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  redis:
    image: redis:7
    volumes:
      - redis_data:/data
    restart: unless-stopped

  opensearch:
    image: opensearchproject/opensearch:2
    environment:
      discovery.type: single-node
      plugins.security.disabled: "true"
      OPENSEARCH_JAVA_OPTS: "-Xms4g -Xmx4g"
    ulimits:
      memlock:
        soft: -1
        hard: -1
    volumes:
      - opensearch_data:/usr/share/opensearch/data
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio123
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  opensearch_data:
  minio_data:
```

## 3.3 主机配置要求

至少处理：

- `vm.max_map_count >= 262144`
- 关闭 swap 或尽量避免
- OpenSearch 使用 SSD / NVMe
- MinIO / PostgreSQL 数据卷持久化
- `.env` 中隔离所有模型 Key

---

# 四、后端代码结构（工程版）

```text
backend/
  app/
    api/
      project.py
      document.py
      workflow.py
      section.py
      review.py
      export.py
    core/
      config.py
      logging.py
      db.py
      opensearch.py
      redis.py
      storage.py
      security.py
    ai/
      gateway.py
      providers/
        qwen.py
        deepseek.py
        glm.py
      prompts/
        extract_project_facts.jinja2
        extract_requirements.jinja2
        generate_outline.jinja2
        generate_section.jinja2
        review_section.jinja2
    workflows/
      base.py
      registry.py
      states.py
      tender_ingestion.py
      standard_ingestion.py
      generate_section.py
      review_section.py
      export_bid.py
    tools/
      base.py
      registry.py
      parse_document.py
      extract_outline.py
      extract_project_facts.py
      extract_requirements.py
      search_sections.py
      search_clauses.py
      search_company_docs.py
      assemble_evidence_pack.py
      check_fact_consistency.py
      check_requirement_coverage.py
      check_clause_usage.py
      render_docx.py
      convert_pdf.py
    services/
      parse_service.py
      extract_service.py
      search_service.py
      write_service.py
      review_service.py
      export_service.py
      workflow_service.py
    repositories/
      project_repo.py
      file_repo.py
      document_repo.py
      requirement_repo.py
      fact_repo.py
      draft_repo.py
      review_repo.py
      workflow_repo.py
      trace_repo.py
    models/
      project.py
      document.py
      requirement.py
      fact.py
      draft.py
      workflow_run.py
      task_trace.py
    schemas/
      project.py
      document.py
      tool.py
      workflow.py
      review.py
    workers/
      celery_app.py
      tasks_parse.py
      tasks_workflow.py
      tasks_export.py
  tests/
    unit/
    integration/
    evals/
```

---

# 五、Workflow 状态机设计

## 5.1 状态定义

- `pending`
- `running`
- `suspended`
- `completed`
- `failed`
- `cancelled`

## 5.2 状态流转

```text
pending -> running
running -> suspended
suspended -> running
running -> completed
running -> failed
pending/running/suspended -> cancelled
```

## 5.3 挂起场景

一期至少支持以下 suspend 点：

1. 否决项人工核验
2. 提纲人工修改
3. 表格人工纠错
4. 导出前人工确认

## 5.4 workflow_run 表建议

```sql
CREATE TABLE workflow_run (
  id BIGSERIAL PRIMARY KEY,
  workflow_name VARCHAR(100) NOT NULL,
  project_id BIGINT NOT NULL,
  state VARCHAR(32) NOT NULL,
  current_step VARCHAR(100),
  context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_id VARCHAR(100) NOT NULL,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);
```

---

# 六、完整数据库 DDL（核心 25 张表）

> 以下是工程实施建议版。可在开发中按命名规范微调。

## 6.1 基础业务表

### project

```sql
CREATE TABLE project (
  id BIGSERIAL PRIMARY KEY,
  project_name TEXT NOT NULL,
  owner_name TEXT,
  tender_no TEXT,
  project_type VARCHAR(64),
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  tender_deadline TIMESTAMP,
  created_by VARCHAR(100),
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### project_file

```sql
CREATE TABLE project_file (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  file_name TEXT NOT NULL,
  file_type VARCHAR(64) NOT NULL,
  storage_path TEXT NOT NULL,
  mime_type VARCHAR(128),
  version_no INT NOT NULL DEFAULT 1,
  uploaded_by VARCHAR(100),
  uploaded_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### document

```sql
CREATE TABLE document (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT,
  source_file_id BIGINT NOT NULL,
  doc_type VARCHAR(64) NOT NULL,
  parse_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  parsed_markdown_path TEXT,
  parsed_json_path TEXT,
  parsed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

## 6.2 文档结构化表

### document_outline_node

```sql
CREATE TABLE document_outline_node (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL,
  parent_id BIGINT,
  node_type VARCHAR(32) NOT NULL,
  node_no VARCHAR(64),
  title TEXT,
  level INT NOT NULL,
  page_start INT,
  page_end INT,
  sort_order INT NOT NULL DEFAULT 0
);
```

### document_section

```sql
CREATE TABLE document_section (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL,
  outline_node_id BIGINT,
  section_title TEXT,
  title_path TEXT,
  content TEXT,
  content_summary TEXT,
  page_start INT,
  page_end INT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb
);
```

### document_table

```sql
CREATE TABLE document_table (
  id BIGSERIAL PRIMARY KEY,
  document_id BIGINT NOT NULL,
  page_no INT,
  table_title TEXT,
  table_json JSONB NOT NULL,
  table_markdown TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### document_table_override

```sql
CREATE TABLE document_table_override (
  id BIGSERIAL PRIMARY KEY,
  table_id BIGINT NOT NULL,
  corrected_json JSONB NOT NULL,
  corrected_markdown TEXT,
  corrected_by VARCHAR(100),
  corrected_at TIMESTAMP NOT NULL DEFAULT now()
);
```

## 6.3 规范条款表

### standard

```sql
CREATE TABLE standard (
  id BIGSERIAL PRIMARY KEY,
  standard_code VARCHAR(100) NOT NULL,
  standard_name TEXT NOT NULL,
  version_year VARCHAR(20),
  status VARCHAR(32) NOT NULL DEFAULT 'effective',
  specialty VARCHAR(64),
  document_id BIGINT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### standard_clause

```sql
CREATE TABLE standard_clause (
  id BIGSERIAL PRIMARY KEY,
  standard_id BIGINT NOT NULL,
  parent_id BIGINT,
  clause_no VARCHAR(100),
  clause_title TEXT,
  clause_text TEXT NOT NULL,
  summary TEXT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  page_start INT,
  page_end INT,
  sort_order INT NOT NULL DEFAULT 0
);
```

## 6.4 项目要求 / 事实表

### project_requirement

```sql
CREATE TABLE project_requirement (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  requirement_text TEXT NOT NULL,
  requirement_category VARCHAR(32) NOT NULL,
  source_document_id BIGINT,
  source_section_id BIGINT,
  source_page INT,
  human_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  confirmed_by VARCHAR(100),
  confirmed_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### project_fact

```sql
CREATE TABLE project_fact (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  fact_key VARCHAR(100) NOT NULL,
  fact_value TEXT NOT NULL,
  source_document_id BIGINT,
  source_page INT,
  confidence NUMERIC(5,4),
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### human_confirmation

```sql
CREATE TABLE human_confirmation (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  confirm_type VARCHAR(64) NOT NULL,
  target_id BIGINT,
  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  confirmed_by VARCHAR(100),
  confirmed_at TIMESTAMP,
  note TEXT
);
```

## 6.5 模板 / 草稿 / 审校表

### section_template

```sql
CREATE TABLE section_template (
  id BIGSERIAL PRIMARY KEY,
  template_name TEXT NOT NULL,
  project_type VARCHAR(64),
  section_name TEXT NOT NULL,
  template_text TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### project_outline_node

```sql
CREATE TABLE project_outline_node (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  parent_id BIGINT,
  section_name TEXT NOT NULL,
  level INT NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  required BOOLEAN NOT NULL DEFAULT TRUE,
  human_confirmed BOOLEAN NOT NULL DEFAULT FALSE
);
```

### chapter_draft

```sql
CREATE TABLE chapter_draft (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  outline_node_id BIGINT,
  section_name TEXT NOT NULL,
  draft_text TEXT NOT NULL,
  draft_markdown TEXT,
  prompt_version VARCHAR(50),
  model_name VARCHAR(100),
  human_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### review_issue

```sql
CREATE TABLE review_issue (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  draft_id BIGINT,
  section_name TEXT,
  issue_type VARCHAR(64),
  severity VARCHAR(32) NOT NULL,
  issue_text TEXT NOT NULL,
  suggestion_text TEXT,
  source_ref JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

## 6.6 Workflow / Trace / Export 表

### workflow_run

```sql
CREATE TABLE workflow_run (
  id BIGSERIAL PRIMARY KEY,
  workflow_name VARCHAR(100) NOT NULL,
  project_id BIGINT NOT NULL,
  state VARCHAR(32) NOT NULL,
  current_step VARCHAR(100),
  context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  trace_id VARCHAR(100) NOT NULL,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  updated_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### workflow_step_log

```sql
CREATE TABLE workflow_step_log (
  id BIGSERIAL PRIMARY KEY,
  workflow_run_id BIGINT NOT NULL,
  step_name VARCHAR(100) NOT NULL,
  state VARCHAR(32) NOT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT now(),
  finished_at TIMESTAMP,
  message TEXT
);
```

### task_trace

```sql
CREATE TABLE task_trace (
  id BIGSERIAL PRIMARY KEY,
  workflow_run_id BIGINT,
  workflow_name VARCHAR(100),
  step_name VARCHAR(100),
  prompt_version VARCHAR(50),
  model_name VARCHAR(100),
  temperature NUMERIC(4,2),
  input_snapshot JSONB,
  tool_calls JSONB,
  tool_results JSONB,
  output_snapshot JSONB,
  error_type VARCHAR(64),
  root_cause VARCHAR(128),
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### export_record

```sql
CREATE TABLE export_record (
  id BIGSERIAL PRIMARY KEY,
  project_id BIGINT NOT NULL,
  template_name TEXT,
  docx_path TEXT,
  pdf_path TEXT,
  created_by VARCHAR(100),
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

## 6.7 词典与配置表

### synonym_dictionary

```sql
CREATE TABLE synonym_dictionary (
  id BIGSERIAL PRIMARY KEY,
  term TEXT NOT NULL,
  synonym TEXT NOT NULL,
  source TEXT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### prompt_template

```sql
CREATE TABLE prompt_template (
  id BIGSERIAL PRIMARY KEY,
  prompt_name VARCHAR(100) NOT NULL,
  version VARCHAR(50) NOT NULL,
  template_text TEXT NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### model_profile

```sql
CREATE TABLE model_profile (
  id BIGSERIAL PRIMARY KEY,
  profile_name VARCHAR(100) NOT NULL,
  provider VARCHAR(50) NOT NULL,
  model_name VARCHAR(100) NOT NULL,
  temperature NUMERIC(4,2) NOT NULL DEFAULT 0,
  top_p NUMERIC(4,2),
  max_tokens INT,
  enabled BOOLEAN NOT NULL DEFAULT TRUE
);
```

### tool_definition

```sql
CREATE TABLE tool_definition (
  id BIGSERIAL PRIMARY KEY,
  tool_name VARCHAR(100) NOT NULL,
  description TEXT,
  input_schema JSONB NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

### skill_definition

```sql
CREATE TABLE skill_definition (
  id BIGSERIAL PRIMARY KEY,
  skill_name VARCHAR(100) NOT NULL,
  description TEXT,
  workflow_json JSONB NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
```

---

# 七、OpenSearch 索引 mapping（一期生产建议）

## 7.1 section_index

```json
{
  "settings": {
    "analysis": {
      "filter": {
        "construction_synonym": {
          "type": "synonym",
          "synonyms_path": "analysis/synonyms.txt"
        }
      },
      "analyzer": {
        "cn_with_synonym": {
          "tokenizer": "standard",
          "filter": ["lowercase", "construction_synonym"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "section_id": {"type": "keyword"},
      "document_id": {"type": "keyword"},
      "project_type": {"type": "keyword"},
      "doc_type": {"type": "keyword"},
      "section_name": {
        "type": "text",
        "analyzer": "cn_with_synonym"
      },
      "title_path": {
        "type": "text",
        "analyzer": "cn_with_synonym"
      },
      "content": {
        "type": "text",
        "analyzer": "cn_with_synonym"
      },
      "tags": {"type": "keyword"},
      "page_start": {"type": "integer"},
      "page_end": {"type": "integer"}
    }
  }
}
```

## 7.2 clause_index

```json
{
  "settings": {
    "analysis": {
      "filter": {
        "construction_synonym": {
          "type": "synonym",
          "synonyms_path": "analysis/synonyms.txt"
        }
      },
      "analyzer": {
        "cn_with_synonym": {
          "tokenizer": "standard",
          "filter": ["lowercase", "construction_synonym"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "clause_id": {"type": "keyword"},
      "standard_code": {"type": "keyword"},
      "standard_name": {
        "type": "text",
        "analyzer": "cn_with_synonym"
      },
      "clause_no": {"type": "keyword"},
      "clause_title": {
        "type": "text",
        "analyzer": "cn_with_synonym"
      },
      "clause_text": {
        "type": "text",
        "analyzer": "cn_with_synonym"
      },
      "tags": {"type": "keyword"},
      "page_start": {"type": "integer"},
      "page_end": {"type": "integer"}
    }
  }
}
```

## 7.3 requirement_index

```json
{
  "mappings": {
    "properties": {
      "requirement_id": {"type": "keyword"},
      "project_id": {"type": "keyword"},
      "requirement_category": {"type": "keyword"},
      "requirement_text": {"type": "text"},
      "source_page": {"type": "integer"},
      "human_confirmed": {"type": "boolean"}
    }
  }
}
```

---

# 八、同义词词典结构（一期建议）

## 8.1 同义词文件示例

```text
基坑开挖,土方开挖
三通一平,场地准备
脚手架,外架
模板工程,支模
混凝土浇筑,混凝土施工
防水防潮处理,防渗漏处理
安全文明施工,文明施工,安全管理
施工进度计划,工期安排
质量保证措施,质量管理措施
临时用电,施工用电
```

## 8.2 维护机制

同义词维护建议：

1. 初始人工导入
2. 检索日志回溯
3. 人工审核新增
4. 重建分析器并滚动更新索引

---

# 九、Tool / Skill / Workflow 实际模板

## 9.1 Tool 基类

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel, ValidationError

class ToolResult(BaseModel):
    ok: bool
    data: dict | None = None
    error: str | None = None

class Tool(ABC):
    name: str
    description: str
    input_model = None

    @abstractmethod
    def _invoke(self, validated_input):
        pass

    def invoke(self, **kwargs) -> ToolResult:
        try:
            validated = self.input_model(**kwargs)
        except ValidationError as e:
            return ToolResult(
                ok=False,
                error=f"参数校验失败：{e.errors()}"
            )
        try:
            data = self._invoke(validated)
            return ToolResult(ok=True, data=data)
        except Exception as e:
            return ToolResult(ok=False, error=str(e))
```

## 9.2 Tool Registry

```python
class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        self._tools[tool.name] = tool

    def get(self, name):
        return self._tools[name]

    def schemas(self, allowed_tools):
        return [self._tools[name].to_openai_schema() for name in allowed_tools]
```

## 9.3 Workflow 基类

```python
class WorkflowContext:
    def __init__(self, project_id, trace_id, section_name=None, data=None):
        self.project_id = project_id
        self.trace_id = trace_id
        self.section_name = section_name
        self.data = data or {}
        self.logs = []
        self.state = "pending"

class BaseWorkflow:
    name = "base"

    def __init__(self, steps):
        self.steps = steps

    def execute(self, ctx):
        for step in self.steps:
            ctx.state = step.name
            ctx = step.run(ctx)
            if getattr(ctx, "suspended", False):
                return ctx
        ctx.state = "completed"
        return ctx
```

## 9.4 AIGateway

```python
class AIGateway:
    def __init__(self, provider_adapter):
        self.provider_adapter = provider_adapter

    def chat_completions(self, payload: dict):
        return self.provider_adapter.chat_completions(payload)
```

## 9.5 generate_section skill 示例

```yaml
name: generate_section
steps:
  - load_project_facts
  - load_section_requirements
  - search_clauses
  - search_sections
  - assemble_evidence_pack
  - llm_generate_outline
  - human_confirm_outline
  - llm_generate_section
  - save_draft
```

---

# 十、Evals 与 Trace 体系

## 10.1 自动评测指标

1. 事实一致性（Factual Consistency）
2. 合规覆盖率（Compliance Coverage）
3. 结构完整度（Structure Integrity）
4. 检索命中率（Retrieval Hit Rate）
5. 否决项漏检率（Disqualify Miss Rate）

## 10.2 测试集建议

### 抽取测试集
- 招标文件事实抽取
- 否决项抽取
- 资格要求分类

### 检索测试集
- 条款命中
- 样章命中
- 要求命中

### 生成测试集
- 固定 evidence pack 生成章节

### 审校测试集
- 人工构造错误草稿
- 检查能否识别冲突与漏项

---

# 十一、实施排期（工程版）

## Week 1
- 项目脚手架
- Docker Compose
- PostgreSQL / Redis / MinIO / OpenSearch 起服务

## Week 2
- 项目、文件、文档基础表
- 文件上传与对象存储

## Week 3
- MinerU 接入
- 文档解析结果入库
- 文档结构化基础表

## Week 4
- 目录树 / 表格清洗规则
- 项目事实抽取
- 招标要求 / 否决项抽取
- 表格人工纠错

## Week 5
- 规范条款树构建
- OpenSearch 索引初始化
- 同义词词典接入

## Week 6
- Tool 基类
- Tool Registry
- Search Service
- Clause / Section 检索

## Week 7
- Workflow Engine
- tender_ingestion / standard_ingestion
- workflow_run / task_trace 落库

## Week 8
- generate_section workflow
- evidence pack 组装
- 提纲挂起 / 恢复

## Week 9
- review workflow
- human confirmation
- Word 模板导出
- PDF 转换

## Week 10
- Eval 集
- trace 回放
- 联调测试
- 文档完善

---

# 十二、最终定稿结论

系统架构 2.1 的最终路线：

```text
MinerU
+ Structured Docs
+ PostgreSQL
+ OpenSearch(BM25 + 同义词 + Metadata Filter)
+ Workflow Engine
+ Tool Registry
+ AI Gateway
+ 国产商业模型
+ Human-in-the-loop
+ Trace / Eval
```

本系统的本质不是“自由发挥的智能体”，而是：

> **一个以结构化文档为基础、以确定性工作流为核心、以大模型作为节点能力的人机协同技术标生产系统。**
