# GPT-Vis-SSR 调研备忘(T6)

> 创建日期:2026-05-18
> 调研对象:`@antv/gpt-vis-ssr` + 周边私有部署方案
> 关联计划:`docs/plans/2026-05-17-chart-rendering-refactor-plan.md` § 4
> 收口计划:`docs/superpowers/plans/2026-05-18-prior-plans-closure.md` Track 3

## 一、上游事实

### 1.1 包定位

- 上游主仓:[antvis/GPT-Vis](https://github.com/antvis/GPT-Vis)(分支 `ai`)
- SSR 子包:[`bindings/gpt-vis-ssr`](https://github.com/antvis/GPT-Vis/tree/ai/bindings/gpt-vis-ssr)
- npm:[`@antv/gpt-vis-ssr`](https://www.npmjs.com/package/@antv/gpt-vis-ssr)
- License:MIT

### 1.2 SSR 包 API 形态(关键)

GPT-Vis-SSR **本身是 Node.js 库,不是 HTTP 服务**。源码只暴露 `render(options)`:

```js
import { render } from "@antv/gpt-vis-ssr";
const vis = await render({ type: "line", data: [...] });
const buffer = vis.toBuffer();
vis.destroy();
```

返回值 `SSRResult = { toBuffer(meta?): Buffer, destroy(): void }`。

**结论:私有 HTTP 部署需要自行包一层 Node HTTP 服务**(或使用社区方案,见 §1.3)。

### 1.3 HTTP 部署选项

| 方案 | 来源 | 状态 |
|---|---|---|
| `akyakya/gpt-vis-ssr` 社区 Docker 镜像 | [Docker Hub](https://hub.docker.com/r/akyakya/gpt-vis-ssr) | 489.6 MB,无 README,5 个月未更新,无健康端点文档,需 `docker inspect` 探针 |
| mcp-server-chart 自带 docker-compose | [antvis/mcp-server-chart](https://github.com/antvis/mcp-server-chart) | 是 MCP 包装层(sse:1123 / streamable:1122),不是裸 SSR;面向 MCP 客户端,不适合直连 HTTP |
| 自构镜像 | tender 自管 Dockerfile + Node + `@antv/gpt-vis-ssr` + Express | 推荐,可控性最高 |

### 1.4 当 GPT-Vis-SSR 作为 HTTP 私有服务被调用时(VIS_REQUEST_SERVER 协议)

mcp-server-chart 文档定义了如下契约(可用于自构镜像参考):

- **Method:** POST
- **Body 示例:**`{ "type": "line", "data": [{ "time": "2025-05", "value": 512 }] }`
- **Response 示例:**
  ```json
  {
    "success": true,
    "resultObj": "<chart image URL>",
    "errorMessage": ""
  }
  ```

注意 `resultObj` 是**图片 URL 字符串**,而非 base64 buffer — 上游 SSR 默认要把渲染结果上传到对象存储或本地静态目录,这与本仓库 `chart_service` 期望直接拿 SVG/PNG buffer 的契约不一致,需 wrapper 改造。

### 1.5 支持图表类型(26 种 / 与 tender 15 种映射)

GPT-Vis 26 类按 README:

- **统计(18)**:line / area / column / bar / pie / scatter / radar / funnel / waterfall / dual-axes / histogram / boxplot / violin / venn / sankey / treemap / word-cloud / liquid
- **关系(6)**:flow-diagram / network-graph / mindmap / indented-tree / organization-chart / fishbone-diagram
- **文本可视化(2)**:table / summary

**映射 tender SUPPORTED_CHART_TYPES:**

| tender chart_type | GPT-Vis 对应 | 适配判断 |
|---|---|---|
| `construction_flow` / `closure_flow` / `data_flow` / `quality_system` / `safety_system` / `emergency_org` | flow-diagram / network-graph | ✅ 可作为 mermaid 替代 |
| `org_chart` | organization-chart | ✅ 一比一对应 |
| **`schedule_gantt`** | **(无 Gantt 类型)** | ❌ **GPT-Vis 不支持 Gantt** — POC 主要场景缺失 |
| **`critical_path`** | flow-diagram(强行映射) | ⚠️ 关键路径在 GPT-Vis 上失语义 |
| `risk_matrix` / `responsibility_matrix` | heatmap(GPT-Vis 无显式 heatmap;表格 + 矩阵需自构) | ⚠️ 已由 vl-convert 改造 1 接管,不必走 GPT-Vis |
| `indicator_table` / `response_matrix` / `interface_table` / `equipment_table` | table | ⚠️ 已由 native + vl-convert 接管 |

**关键事实(写给后续 cutover 决策):**

> **GPT-Vis 不原生支持 Gantt 图。** mermaid sidecar 当前承担 `schedule_gantt` 和 `critical_path` 的主路径,若用 GPT-Vis 替换 mermaid,Gantt 类要么继续走 mermaid(混合方案),要么退化到 native_gantt_svg(已有)。改造 2 计划 v2 § 4.1 "100 对 POC"原本写"flow 50 + gantt 50",**实际 gantt 50 这一半无可对比对象** — POC 范围需收窄到 flow 类。

### 1.6 中文字体 / 离线 / 并发

| 项 | 上游文档 | 经验判断 |
|---|---|---|
| CJK 字体 | **未提及** | 底层 node-canvas + Cairo,需在容器内安装 `fonts-noto-cjk` 类似包;否则中文方块 |
| 离线部署 | **未提及** | npm install + 自构镜像理论可行;但 GPT-Vis 渲染 organization-chart 等关系图依赖前端图标资源(SVG sprite),需打入镜像 |
| 并发 | **未提及** | 每次 render() 创建 node-canvas 实例,内存占用与图复杂度线性正相关;无内置 throttle |
| 失败回退 | **未提及** | wrapper 需自行设超时 + try/catch + 返回 `success=false` |
| 输出格式 | README 只示例 `toBuffer()` | 实测 `@antv/gpt-vis-ssr@0.3.7` 的 `toBuffer()`/`toBuffer("svg")` 均输出 PNG;本仓库 wrapper 返回 SVG shell 内嵌 PNG data URI,不是原生矢量 SVG |

## 二、与 mermaid sidecar 的同形性核查

| 维度 | mermaid-render | GPT-Vis-SSR(估算) |
|---|---|---|
| 运行时 | Node 20 + Chromium + mmdc(headless) | Node 18+ + node-canvas + Cairo |
| 镜像基底 | `node:20-bookworm-slim` | `node:18-bookworm-slim` |
| 内存 | ~500MB-1GB(Chromium) | 估 300-500MB(无 Chromium,但 G2/canvas 内存非负) |
| 启动时延 | 冷启 ~3s | 估 < 1s(无浏览器) |
| 并发限流 | 当前无 | 无,需自加 |
| 中文字体 | `fonts-noto-cjk` 已打入 | 需自打入 |

**资源持平结论:** 比 mermaid 稍轻(无 Chromium),但**仍是 Node + 浏览器栈级方案**,确实"换牌子"层面没改变架构边界 — 评审意见准确。

## 三、能力边界总结

✅ **GPT-Vis-SSR 强项**(适合纳入改造 2 POC):
- 关系类图(flow-diagram / network-graph / organization-chart / mindmap / fishbone-diagram)
- 现代视觉风格(优于 mermaid 默认主题)
- 同进程渲染,无 Chromium 启动开销

❌ **GPT-Vis-SSR 弱项 / 不可替代场景**:
- **Gantt 图无原生支持**(schedule_gantt / critical_path 主路径)
- **risk_matrix / responsibility_matrix 不在 26 类内**(本仓库已由 vl-convert 改造 1 覆盖,不必再争)
- HTTP 服务需自构(社区 Docker 文档不全)
- 中文字体 + 离线 + 并发 三项均需 wrapper 兜底

## 四、POC 范围(修订自 § 4.1 v2 原本"flow 50 + gantt 50")

**修订后的 POC 范围:**

| 图类 | 数量 | 来源 |
|---|---:|---|
| construction_flow | 15 | 历史 chart_assets,跨第 8/9/10 章 |
| closure_flow + data_flow | 10 | 同上 |
| quality_system + safety_system + emergency_org | 15 | 同上 |
| org_chart | 10 | 同上 |
| **flow 小计** | **50** | |
| schedule_gantt | **0** | **GPT-Vis 不支持,本 POC 不覆盖 gantt** |
| critical_path | **0** | **同上** |
| **gantt 小计** | **0**(改造 2 POC 不再追求 gantt 替换;后续若做 cutover 也只能涵盖 flow) | |

**结论:** 改造 2 实际仅是 **mermaid flow 图替换** POC;Gantt 主路径保持 mermaid(或退到 native_gantt_svg)。这一约束需在 T9(POC 报告)和 T10(后续 cutover 决策)中明确写入。

## 五、自构 wrapper 镜像建议

若 POC 进入实施,推荐自构镜像 `tender-gpt-vis-ssr`:

```dockerfile
FROM node:20-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    libcairo2 libpango-1.0-0 libjpeg62-turbo libgif7 librsvg2-2 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server.js package.json package-lock.json ./
RUN npm ci --omit=dev
EXPOSE 7102
HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD curl -fsS http://127.0.0.1:7102/health || exit 1
CMD ["node", "server.js"]
```

`server.js` 用 Express 暴露:
- `POST /render` — body `{type, data, theme?}` → `{success, svg, errorMessage}`;其中 `svg` 是 SVG shell + embedded PNG,用于兼容后端 SVG 字符串 contract
- `GET /health` — 200
- 内部 `Semaphore(max=4)` 做并发限流

**关键决策点(T7 落实时确认):**
- 端口 `7102`(避开 mermaid-render 占用)
- 输出 SVG 字符串而非图片 URL(与本仓库 `_render_vega_svg` 同形)
- 失败 fallback 由 wrapper 内 try/catch 返回 `success=false`,Python 端再退到 mermaid

## 六、对 T7~T9 的具体影响

| 任务 | 收口计划原表述 | 调整建议 |
|---|---|---|
| T7 部署 | "选官方镜像或自构" | **必须自构**;社区 `akyakya/gpt-vis-ssr` 无文档不可控 |
| T7 端口 | 7102 占位 | 保留 7102 |
| T17 contract test | 6 类(基本 SVG / A4 / 中文 / 4xx / 超时 / 离线 / 并发) | 不变,但**输入 schema 必须用 wrapper 定义的 `{type, data, theme?}`** |
| T8 多引擎分发 | flow + gantt 都改 | **改为仅 flow**;gantt 主路径保持 mermaid + native_gantt 不动 |
| T9 100 对图对比 | flow 50 + gantt 50 | **改为 flow 50;gantt 0**;同时把"SVG shell 内嵌 PNG"列入可读性与 DOCX 注入风险项 |

## 七、不在本 POC 范围

- 把 `risk_matrix` / `responsibility_matrix` 换回 GPT-Vis(已由 vl-convert 接管)
- `indicator_table` 走 GPT-Vis(已由 vl-convert POC adopt)
- 把 mermaid 完全下线(T10 DEFERRED,等 POC 结论)
- 引入 GPT-Vis 26 类统计图(tender 不主要用)

## 八、参考资料

- [GPT-Vis 主仓](https://github.com/antvis/GPT-Vis)
- [gpt-vis-ssr 子包源码](https://github.com/antvis/GPT-Vis/tree/ai/bindings/gpt-vis-ssr)
- [npm @antv/gpt-vis-ssr](https://www.npmjs.com/package/@antv/gpt-vis-ssr)
- [mcp-server-chart](https://github.com/antvis/mcp-server-chart)
- [akyakya/gpt-vis-ssr Docker Hub](https://hub.docker.com/r/akyakya/gpt-vis-ssr)
- [Vega-Lite vs Vega SSR 对比](https://g2.antv.vision/en/manual/extra-topics/ssr/)

---

## 修订记录

| 版本 | 日期 | 内容 |
| --- | --- | --- |
| v1.0 | 2026-05-18 | 初版调研;明确 GPT-Vis-SSR 是 Node 库非 HTTP 服务,需自构 wrapper;Gantt 不支持,POC 范围从 flow 50 + gantt 50 收窄到 flow 50。 |
| v1.1 | 2026-05-18 | T7/T17 实测补充:`@antv/gpt-vis-ssr@0.3.7` npm 真实版本;直接 require 需忽略 CSS;默认 theme 必须为 `default`;输出为 PNG buffer,wrapper 以 SVG shell 内嵌 PNG 满足后端 contract;live contract 7 项通过。 |
