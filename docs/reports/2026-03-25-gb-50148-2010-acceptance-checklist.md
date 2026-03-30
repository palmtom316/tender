# GB 50148-2010 单书验收清单

- **日期：** 2026-03-25
- **标准：** `GB 50148-2010`
- **standard_id：** `ff2ddb6c-ba8e-4e42-862f-e75d5824437a`
- **document_id：** `e3003181-042a-44da-ad67-44615d7d25f2`
- **目标：** 当前阶段只对这一份规范做到“接近人工”，不追求先泛化到全部规范。

## 1. 主验收指标

以综合质量验收，其中优先级如下：

1. 条号完整率
2. 层级与归属正确率
3. 表格归属与页锚点
4. 条文说明分离

## 2. 当前最低通过条件

### 条款数量

- 总条款数必须 `>= 370`
- `processing_status` 必须为 `completed`

### 必须命中的关键条号区域

至少覆盖以下关键区域中的代表条号：

- `4.1.2`
- `4.2.4`
- `4.12.1`
- `5.3.6`
- `A.0.2`

### 条文说明分离

- 必须同时存在 `normative` 与 `commentary` 两类条款
- 不允许出现“整书几乎全部落成 commentary”这类明显误判

### 表格归属

- `document_table` 中必须存在 `表 4.2.4 变压器内油样性能`
- `standard_clause` 中必须存在至少一条 `source_type='table'` 的表格派生条款

## 3. 当前允许存在的问题

以下问题在本阶段允许暂存，但必须被记录：

- 少量 `numbering.gap`
- 少量 `numbering.non_monotonic`
- 少量 `numbering.missing_parent`

前提是：

- 关键条号没有缺失
- 表格来源仍可追溯
- 正文与说明未混线

## 4. 当前直接判定不通过的情形

- 总条款数低于 `370`
- 缺失关键条号区域
- `processing_status != completed`
- `条文说明` 与正文混到同一主提取通道
- `表 4.2.4` 丢失或无法形成表格派生条款

## 5. 本阶段说明

这份清单不是通用金标集，只是 `GB 50148-2010` 的单书验收门槛。后续如果该书达标并稳定，再把规则和验收抽象出去做多书金标集。

## 6. 持久化结果检查命令

用于每次 real rerun 后快速确认当前库里的验收差距：

```bash
docker compose --env-file /home/palmtom/projects/tender/infra/.env \
  -f /home/palmtom/projects/tender/infra/docker-compose.yml \
  exec -T postgres sh -lc \
  "psql -U tender -d tender -F $'\t' -A -c \
  \"select count(*) as total,
           count(*) filter (where clause_type='normative') as normative,
           count(*) filter (where clause_type='commentary') as commentary,
           count(*) filter (where page_start is null or page_start <= 0 or page_end is null or page_end <= 0) as incomplete_page_anchor,
           count(*) filter (where source_type='table') as table_clause_count
      from standard_clause
     where standard_id = 'ff2ddb6c-ba8e-4e42-862f-e75d5824437a';\""
```

如需检查关键条号：

```bash
docker compose --env-file /home/palmtom/projects/tender/infra/.env \
  -f /home/palmtom/projects/tender/infra/docker-compose.yml \
  exec -T postgres sh -lc \
  "psql -U tender -d tender -F $'\t' -A -c \
  \"select clause_no, clause_type, source_type, page_start, page_end
      from standard_clause
     where standard_id = 'ff2ddb6c-ba8e-4e42-862f-e75d5824437a'
       and clause_no in ('4.1.2','4.2.4','4.12.1','5.3.6','A.0.2')
     order by clause_no;\""
```

## 7. 2026-03-30 本地环境备注

- 当前本地 PostgreSQL 中，`standard_id = ff2ddb6c-ba8e-4e42-862f-e75d5824437a` 的 `standard_clause` 记录数为 `0`。
- 这说明本地环境暂时不能直接作为“已有真实 rerun 结果”的证据来源，后续需要先完成一次真实重跑，才能把这里的检查命令用于验收收口。

## 8. 2026-03-30 最新本地 real rerun 结果

- 使用当前 worktree 代码对本地 GB50148 实例完成了一次真实重跑：
  - `standard_id = ad9e7b99-6c94-48cf-8bd3-269314090b6e`
  - `document_id = 9491c69c-9ee7-4a5b-902e-16c3b2c82e9a`
- 持久化结果：
  - `total = 390`
  - `normative = 354`
  - `commentary = 36`
  - `table_clause_count = 2`
  - `incomplete_page_anchor = 0`
- 关键条号确认：
  - `3.0.8` 已恢复
  - `4.1.2` 已存在
  - `4.2.4` 已存在
  - `4.12.1` 已存在
  - `5.3.6` 已存在
  - `A.0.2` 已存在
- 结论：
  - 当前结果已超过本清单定义的 `>= 370` 门槛，表格派生条款与页锚点要求也满足。

### 当前已知残留问题

- `commentary` 总量仍低于早前目标形态（当前 `36`，目标形态示例为 `49+`）。
- 仍有少量 synthetic item 未并回宿主条款，例如 `4.8.5` 附近会出现独立 `1/2/3` block，其中部分被 `heading_only_block` 跳过。
- “本规范用词说明” 中的 `1/2/3` 仍会被当作 `normative` 条款持久化，属于噪声条款，虽然当前不影响单书验收过线。

## 9. 2026-03-30 尾巴收口后本地 real rerun 结果

- 基于当前 worktree 再次完成真实重跑：
  - `standard_id = ad9e7b99-6c94-48cf-8bd3-269314090b6e`
  - `document_id = 9491c69c-9ee7-4a5b-902e-16c3b2c82e9a`
- 持久化结果更新为：
  - `total = 400`
  - `normative = 361`
  - `commentary = 39`
  - `missing_anchor_count = 0`
  - `wording_noise = 0`
- 关键条号复核：
  - `3.0.8`
  - `4.1.2`
  - `4.2.4`
  - `4.12.1`
  - `5.3.6`
  - `A.0.2`
- 收口结论：
  - `4.8.5 / 4.8.6 / 4.8.7` 已在真实 rerun 中按独立 scope 顺序处理，不再把 sibling clause 裹进 `4.8.5` 的 synthetic item 流。
  - “本规范用词说明” 主段落在 block 构建阶段被识别为 `non_clause_block`，相关说明性编号项不再落入 `normative` 持久化结果。
  - 总条款量进一步提升到 `400`，并继续满足当前单书验收门槛。
