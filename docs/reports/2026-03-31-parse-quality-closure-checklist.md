# 2026-03-31 Parse Quality Closure Checklist

- 日期：`2026-03-31`
- 目标：用跨规范结构验收替代旧的“总数追线”口径，当前聚焦 `GB 50147-2010` 与 `GB 50150-2016`

## 1. 当前活跃样本

- `GB 50147-2010`
  - latest `standard_id`: `fbd3cea9-8d4e-44a1-bab7-8c76fbe564db`
  - latest `document_id`: `c7a3a96f-8f2b-4645-8262-f8aeddaec198`
  - latest verified rerun summary: `total=530`, `normative=435`, `commentary=95`, `scopes_processed=55`, `repair_task_count=1`, `issues_before_repair=3`, `issues_after_repair=3`
  - latest verified rerun repair status: repair 侧已发生 `2` 次 transient retry，但第 `3` 次仍返回 `502 Bad Gateway` on `http://127.0.0.1:8100/api/ai/chat`
  - current code status on worktree: `repair retry + continuation-aware scope rebalance + top-level numbering noise suppression` 已落地并完成真实复跑验证
- `GB 50150-2016`
  - latest `standard_id`: `35d2f2f0-da86-4b55-b125-d40f5e9d59d8`
  - latest `document_id`: `5be09b3f-3bd1-471a-8163-efcaf2b36347`
  - latest persisted summary: `total=844`, `normative=844`, `commentary=0`, `missing_anchor_count=0`, `null_clause_no_count=8`, `duplicate_identity_count=16`

## 2. Repro SQL

标准最新行：

```sql
select id, standard_code, standard_name, document_id, processing_status, created_at
from standard
where standard_code in ('GB 50147-2010', 'GB 50150-2016')
order by created_at desc;
```

按 `standard_id` 看持久化结构指标：

```sql
select
  count(*) as total_count,
  count(*) filter (where clause_type = 'normative') as normative_count,
  count(*) filter (where clause_type = 'commentary') as commentary_count,
  count(*) filter (
    where page_start is null or page_start <= 0 or page_end is null or page_end <= 0
  ) as missing_anchor_count,
  count(*) filter (
    where clause_no is null or btrim(clause_no) = ''
  ) as null_clause_no_count
from standard_clause
where standard_id = :standard_id;
```

按 `document_id` 看 OCR `document_section` 形态：

```sql
select
  count(*) as document_section_count,
  count(*) filter (
    where coalesce(section_code, '') ~ '^(?:[A-Z]\.?\d+(?:\.\d+)*|\d+(?:\.\d+)+)$'
  ) as clause_like_section_count,
  count(*) filter (
    where coalesce(section_code, '') ~ '^\d+$'
  ) as numbered_item_section_count,
  count(*) filter (
    where title like '附录%' or coalesce(section_code, '') ~ '^[A-Z](?:\.\d+)*$'
  ) as appendix_section_count
from document_section
where document_id = :document_id;
```

按 `source_label` 查重 scope：

```sql
select source_label, count(*) as clause_count
from standard_clause
where standard_id = :standard_id
group by source_label
order by clause_count desc nulls last, source_label asc nulls last
limit 20;
```

查 `(clause_no, node_type, node_label)` 重复组：

```sql
select
  clause_no,
  node_type,
  coalesce(node_label, '') as node_label,
  count(*) as duplicate_count
from standard_clause
where standard_id = :standard_id
group by clause_no, node_type, coalesce(node_label, '')
having count(*) > 1
order by duplicate_count desc, clause_no nulls last, node_type, node_label;
```

查空条号与可疑归属：

```sql
select
  clause_no,
  node_type,
  node_label,
  source_type,
  source_label,
  left(clause_text, 200) as clause_text_head
from standard_clause
where standard_id = :standard_id
  and (clause_no is null or btrim(clause_no) = '')
order by source_label nulls last, node_type, node_label;
```

代表条号 presence：

```sql
select clause_no, node_type, node_label, source_label
from standard_clause
where standard_id = :standard_id
  and clause_no in ('5.1.4', '8.0.14', '17.0.4', '3.0.7')
order by clause_no, node_type, node_label;
```

## 3. 解释规则

- `total_count` 只作为次级证据，不能单独作为是否继续开 fix 的理由。
- `GB 50147-2010` 当前应以 `2026-03-31` 晚间复跑得到的 `536 / 440 / 96` 为主口径，不再使用旧的 `429 / 429 / 0` 判断 commentary 缺失。
- 对 `GB 50147-2010`，当前最新验证口径应更新为 `530 / 435 / 95 / issues_after_repair=3`；旧的 `536 / 440 / 96 / issues_after_repair=5` 只用于对比本轮收敛幅度。
- `GB 50150-2016` 的 `844` 必须结合 OCR `document_section` 形态解释，不能再拿历史 `214` 当目标。
- 优先关注：
  - `missing_anchor_count`
  - `null_clause_no_count`
  - 错误 `source_label` / scope attachment
  - appendix / table-only false extraction
  - duplicate identity collisions

## 4. 当前重 Scope 审查名单

- `4 同步发电机及调相机 (1/2)`
- `8 电力变压器 (1/3)`
- `10 互感器 (1/2)`
- `12 六氟化硫断路器`
- `17 电力电缆线路`

## 5. 当前解释快照

- `GB 50147-2010`
  - `commentary` 已稳定恢复，不再是 `0`；本轮最新复跑为 `commentary=95`。和上轮 `96` 的 1 条差异仍需后续单独比对，但 commentary 大面积丢失问题已不是主矛盾。
  - 本轮真实复跑后 residual 已从 `5` 降到 `3`，当前只剩：
    - `Clause 4.2.7: numbering starts at 7, expected 1`
    - `Clause 5.2.8: numbering starts at 8, expected 1`
    - `Clause 8.2.6: numbering starts at 6, expected 1`
  - 本轮已确认被消掉的问题：
    - `Clause 2: numbering starts at 2, expected 1`
    - `Clause 4: numbering gap from 2 to 4`
  - 已证实的收敛路径：
    - 顶层章节 host 噪声已由 `validation` 顶层 gap 抑制消掉。
    - mid-clause continuation 修复后，`8.2` 残留从 `8.2.10` 前移为 `8.2.6`，说明 scope continuation 丢失问题只解决了后半段一部分，仍有更早的 sibling extraction 缺口。
  - `repair_task_count=1` 仍然只落在 table repair；本轮 repair 侧已触发 `2` 次 retry，但网关第 `3` 次仍返回 `502`，所以 `repair_error` 仍未清零。
  - `null_clause_no_count=3` 仍集中在 `表 5.2.2 GIS 设备基础及预埋件的允许偏差(mm)`，属于 table-derived 匿名条目。
- `GB 50150-2016`
  - `844` 与 OCR section-heavy 形态一致，暂不按总数开 fix。
  - 当前 `null_clause_no_count=8` 含 appendix / table 作用域残留。
  - 已观测到 `附录G 电力电缆线路交叉互联系统试验方法和要求 (7/18)` 作用域下挂出了 `8.0.14` 系列条目，属于需要继续核实的错误归属样本。

## 6. 使用说明

- 优先复查最新 `standard` 行，不要混用旧 rerun 的 `standard_id`。
- 每次真实复跑后，先回写本文件第 1 节和第 5 节，再决定是否更新 persisted acceptance snapshot。
- 当前 worktree 已完成一轮新的 `GB 50147-2010` 真实复跑，结果见 `/tmp/gb50147-rerun-fix-4.log`。
- 本清单当前依据 2026-04-01 已验证 rerun 与 worktree 代码状态整理；后续若样本再次复跑，必须以新结果重写第 1 节与第 5 节。
