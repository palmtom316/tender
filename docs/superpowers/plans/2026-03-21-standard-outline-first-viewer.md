# Standard Outline-First Viewer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将规范查看器改为“目录树优先、AI 条款挂载其下”，使右侧树结构与 PDF 目录更一致，同时保留真实 AI 条款定位能力。

**Architecture:** 后端基于 `document_section` 生成目录骨架，在 viewer 组装阶段把 `standard_clause` 节点按“精确匹配合并 + 最长前缀挂载”合成为单棵展示树；前端继续消费单棵树，仅补充目录节点的选择与展示兼容。无目录数据时回退到现有 AI 条款树。

**Tech Stack:** FastAPI、psycopg、pytest、React 18、TypeScript、Vite。

---

## File Map

- Modify: `backend/tender_backend/db/repositories/standard_repo.py` — 目录树构建、AI 节点合成、viewer tree 回退
- Modify: `backend/tender_backend/api/standards.py` — viewer 接口改用目录优先树
- Modify: `frontend/src/lib/api.ts` — 扩展节点类型定义
- Modify: `frontend/src/modules/database/components/StandardClauseTree.tsx` — 目录节点显示兼容
- Modify: `frontend/src/modules/database/components/StandardViewerModal.tsx` — 目录节点详情与跳页兼容
- Modify: `backend/tests/integration/test_standard_repo.py` — viewer tree 合成覆盖
- Modify: `backend/tests/integration/test_standard_viewer_query_api.py` — viewer 接口集成覆盖

## Chunk 1: Backend Merge Logic

### Task 1: 先写失败测试约束合成规则

**Files:**
- Modify: `backend/tests/integration/test_standard_repo.py`
- Modify: `backend/tests/integration/test_standard_viewer_query_api.py`

- [ ] 写仓储层测试，覆盖：
  - 目录节点存在时，viewer tree 先返回目录节点
  - `clause_no` 精确命中目录编号时合并而不重复
  - `4.3.2` 这类条款在缺少同名目录时挂到 `4.3`
  - 没有目录时回退到原始 AI 树
- [ ] 运行 focused pytest，确认先失败
- [ ] 再开始实现

### Task 2: 实现目录优先合成树

**Files:**
- Modify: `backend/tender_backend/db/repositories/standard_repo.py`
- Modify: `backend/tender_backend/api/standards.py`

- [ ] 增加 `document_section` 读取与目录过滤 helper
- [ ] 增加目录节点树构建逻辑
- [ ] 增加 AI 条款节点与目录节点的合成逻辑
- [ ] viewer 接口切换到新 helper
- [ ] 运行 backend tests，确认通过

## Chunk 2: Frontend Compatibility

### Task 3: 兼容目录节点显示和选择

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/modules/database/components/StandardClauseTree.tsx`
- Modify: `frontend/src/modules/database/components/StandardViewerModal.tsx`

- [ ] 补充 `outline` 节点类型字段定义
- [ ] 树组件兼容目录节点标题、页码、默认选中逻辑
- [ ] 详情区兼容目录节点无正文时的展示
- [ ] 保持搜索命中 `clause_id` 定位不变
- [ ] 运行 frontend build，确认类型和渲染通过
