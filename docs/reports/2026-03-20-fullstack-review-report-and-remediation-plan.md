# 代码审查报告与整改计划

- **项目：** Tender
- **审查日期：** 2026-03-20
- **审查范围：** 最新拉取变更 `b99dd75..2258934`，重点覆盖 `backend/`、`frontend/`、`ai_gateway/` 中本次新增或重构的标准规范库能力
- **审查结论：** `REQUEST CHANGES`

## 总结

本次更新把“规范规程库”从上传与处理，扩展到了搜索、PDF 查阅、删除与前端查看器重构，功能闭环明显增强；但当前实现仍存在阻断性问题，主要集中在三类：

1. 标准库新接口缺少鉴权与角色边界，包含删除和 PDF 访问等敏感能力。
2. 删除标准时没有同步清理 OpenSearch 索引，搜索结果会残留已删除数据。
3. 搜索结果回填链路对脏索引数据的容错不足，且存在明显的 N+1 / 阻塞式回填开销。

## 主要问题

### HIGH

1. `backend/tender_backend/api/standards.py:117`
   - 本次新增的标准库接口组没有挂任何 `get_current_user` 或 `require_role` 依赖，覆盖上传、搜索、查看、删除、重试处理等全部能力。
   - 对比：`backend/tender_backend/api/search.py:17`、`backend/tender_backend/api/requirements.py:21` 已显式要求 Bearer token。
   - 风险：匿名用户可以上传规范、查询条款、下载源 PDF，甚至调用 `DELETE /api/standards/{standard_id}` 删除整份规范与源文件。
   - 结论：这是上线前必须修复的权限边界问题。

2. `backend/tender_backend/api/standards.py:320`
   - 删除标准时仅删除 PostgreSQL 里的 `standard` / `project_file` 以及本地 PDF 文件。
   - `backend/tender_backend/db/repositories/standard_repo.py:188` 没有任何索引清理逻辑。
   - 代码库中也没有针对 `clause_index` 的 `_delete_by_query` 或等价删除实现。
   - 风险：`/api/standards/search` 仍可能命中已删除规范的旧索引文档，用户点击“查阅”后再得到 404，形成明显的数据一致性缺陷。
   - 测试缺口：`backend/tests/integration/test_standard_viewer_query_api.py:300` 只验证数据库明细 404，没有验证搜索结果是否被清理。

### MEDIUM

1. `backend/tender_backend/api/standards.py:102`
   - `_serialize_search_hit()` 对 `standard_id` 和 `clause_id` 直接执行 `str(hit.get(...) or source.get(...))`。
   - 当 OpenSearch 文档缺字段，且数据库 fallback 也查不到时，接口会返回字符串 `"None"`，而不是过滤掉该命中或返回真正的空值。
   - 风险：前端会把 `"None"` 当真实 ID 使用，最终请求 `/api/standards/None/viewer` 或携带非法 clause id，表现为 422/404，且难以定位。
   - 这和上一条“删除后索引残留”组合时，会放大坏数据外溢。

2. `backend/tender_backend/api/standards.py:191`
   - 新的 `/api/standards/search` 采用逐条 `_repo.get_clause()` 回填缺失字段。
   - `backend/tender_backend/db/repositories/standard_repo.py:46` 每个命中都会发起一次独立 SQL 查询，且该逻辑位于 `async def` 路由中，使用的是同步 psycopg 连接。
   - 风险：旧索引文档较多时，最多 50 个命中会触发 50 次同步数据库访问，放大接口尾延迟，并阻塞 FastAPI 事件循环线程。
   - 结论：短期可以接受作为兼容层，但必须尽快改成批量回填，并在全量重建索引后移除兼容分支。

3. `frontend/src/modules/database/components/StandardSearchCard.tsx:25`
   - 查询失败时只设置 `error`，不会清空旧结果。
   - 风险：用户执行第二次查询如果网络失败，界面仍展示上一次的命中列表，同时顶部出现错误横幅，容易误判这些旧结果就是当前查询结果。
   - 这是非阻断问题，但会直接影响搜索体验与问题排查。

4. `frontend/src/modules/database/DatabaseModule.tsx:252`
   - `openViewer()` 没有 `AbortController` 或请求序号保护。
   - 风险：用户快速连续点击不同规范或不同命中时，较慢返回的旧请求可能覆盖较新的查看器状态，导致“点了 B 却显示 A”的竞态问题。
   - 建议与前端统一异步请求模式一起治理。

## 架构与运维观察

1. `backend/tender_backend/api/standards.py:128`
   - 标准 PDF 目前直接落本地目录 `_UPLOAD_DIR`，并把绝对路径写入 `project_file.storage_key`。
   - 对比：普通项目文件在 `backend/tender_backend/api/files.py:37` 中使用的是对象存储 key 语义。
   - 风险：标准查看器和删除流程现在强依赖单机本地磁盘；在多实例部署、容器迁移、磁盘清理或共享存储缺失时，`/viewer` 与 `/pdf` 会直接退化成 404。
   - 这不是当前最紧急的阻断项，但建议作为第二阶段整改，统一到对象存储或抽象化文件读取接口。

## 测试与验证情况

1. 静态审查覆盖了本次变更的后端 API、仓储、索引写入、迁移、前端数据流、标准查看器与相关测试文件。
2. 执行 `npm --prefix frontend run build` 后，当前工作区构建失败：
   - `src/modules/database/components/StandardPdfPane.tsx(2,50): Cannot find module 'pdfjs-dist'`
   - `src/modules/database/components/StandardPdfPane.tsx(30,14): Parameter 'doc' implicitly has an 'any' type`
   - 其中第一项与本地 `frontend/node_modules` 尚未安装最新依赖直接相关；本次变更已更新 `frontend/package.json` / `frontend/package-lock.json`，但当前工作区未同步安装 `pdfjs-dist`。
3. 执行 Python 测试时，当前 shell 环境缺少项目依赖：
   - 直接运行 `pytest backend/tests/unit/test_standard_clause_index_docs.py ...` 因 `tender_backend` 不在 `PYTHONPATH` 而失败。
   - 直接运行 `pytest backend/tests/integration/test_standard_viewer_query_api.py -q` 因缺少 `psycopg` 而失败。
4. 结论：本报告的主要风险判断基于静态代码证据，前端构建验证部分已得到部分动态证据；后端自动化验证还需要在项目标准 Python 环境中补跑。

## 整改计划（待批准）

### P0：阻断项，批准后优先实施

1. 给 `standards` 路由补齐统一鉴权。
   - 最低要求：全部接口接入 `get_current_user`。
   - 建议细化：上传、删除、重试处理至少限制到 `editor` / `admin`；纯查看接口按业务需要开放到 `reviewer`。

2. 补齐删除标准的索引清理。
   - 在 `IndexManager` 增加按 `standard_id` 删除 `clause_index` 文档的能力。
   - 将数据库删除、索引删除、本地文件删除整理成可观测的删除事务流程。
   - 为“删除后搜索不可命中”新增集成测试。

3. 修复搜索结果坏数据外溢。
   - `_serialize_search_hit()` 不再生成 `"None"` 字符串。
   - 对 fallback 失败的命中执行丢弃或显式标记，而不是继续返回不可用记录。

### P1：高收益稳定性项

1. 把搜索回填改成批量查库。
   - 新增按 `clause_id IN (...)` 批量查询接口，一次取回缺失 viewer 字段。
   - 回填后过滤不存在的标准/条款，避免把已删除数据继续暴露给前端。

2. 为标准库接口补齐鉴权与一致性测试。
   - 未登录访问返回 401。
   - 权限不足删除返回 403。
   - 删除后再搜索不应返回命中。
   - 脏索引文档不应向前端返回 `"None"` id。

3. 整理前端查看器的请求状态管理。
   - `openViewer()` 引入 `AbortController` 或请求版本号。
   - `StandardSearchCard` 在失败时清理旧结果或显式标注“上次结果”。

### P2：架构优化项

1. 统一标准 PDF 与普通文件的存储抽象。
   - 避免把本地绝对路径直接暴露为业务主键语义。
   - 优先考虑复用现有对象存储 key 模式。

2. 完成旧索引的全量重建并下线兼容回填逻辑。
   - 先执行一次标准条款全量 reindex。
   - 确认新索引文档包含 `standard_name`、`page_start`、`page_end` 等 viewer 所需字段后，再删除临时 fallback 分支，降低复杂度。

3. 固化项目测试入口。
   - 在 README 或脚本中明确 Python 测试运行方式（例如虚拟环境、`PYTHONPATH=backend`、数据库准备步骤）。
   - 避免“代码有测试但本地无法直接执行”的隐性门槛。

## 建议执行顺序

1. 先做 P0：权限边界、删除一致性、坏数据过滤。
2. 再做 P1：批量回填与测试补齐，确保标准库链路稳定。
3. 最后做 P2：存储统一和兼容逻辑收缩，降低长期维护成本。

## 批准建议

建议按上述 `P0 -> P1 -> P2` 顺序实施。若你确认，我下一步会先输出更细的执行清单，并直接开始 P0 修复与验证。
