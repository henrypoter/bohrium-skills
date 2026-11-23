---
name: citation-tracking
description: 引文追踪与关联文献发现：前后向追踪与剪枝、共被引/耦合找平行工作、引用网络识别奠基与桥接节点、路径逐跳标注方向与数据源、身份合并留证据
---

# 引文追踪与关联文献发现

从种子文献出发，沿引用网络做**可复核**的前后向追踪与关联发现：每一跳标注方向与来源，共被引/耦合找平行工作，识别奠基与桥接节点，路径全程留痕。

**不适用**：在线引文数据库（WoS/Scopus/Google Scholar）实时全量查询、引文数的权威排名。本 Skill 处理**给定题录/可及数据源的有限快照**，引用数以快照内为准，不声称全局。

## 调用方式

- 输入：`/input/case.json`（case_id + 种子文献 + 题录/材料）、`/input/task.md`
- 输出：`/app/output/result.json` + 引用边表 / 同族节点表 / 追踪路径表
- 辅助：`scripts/search_tool.py`（`dedup / audit / schema`）
- 模板：`templates/protocol.md`、`templates/worksheets.md`

## 引文追踪特有概念（先建立）

| 概念 | 处理 |
|-|-|
| 后向（backward） | 种子文献引用了谁 → 找理论根基/奠基工作 |
| 前向（forward） | 谁引用了种子文献 → 找最新进展/演化方向 |
| 共被引（co-citation） | 两篇同被第三篇引用 → 找同主题的平行/经典工作 |
| 耦合（coupling） | 两篇共同引用同一批文献 → 找当前相近的平行工作 |
| 奠基/桥接节点 | 高被引（奠基）/ 连接不同主题（桥接） |
| 作者身份合并 | 同人多拼写/缩写归一，留合并证据，不臆断 |

## 工作流

### 0. 定种子与目标
明确：种子文献（可为多篇）、追踪目标（找奠基 / 找最新 / 找平行 / 找桥接）、剪枝规则（时间窗、跳数上限、被引阈值）、数据源清单。先写协议 v1.0。

### 1. 建引用边表（一切的地基）
对快照内每条记录，建 `edges[]`：`{"citing":"A","cited":"B","direction":"backward|forward","source":"哪条数据","hop":1}`。**每条边必须有来源**，凭记忆/推断补的引用关系标 `maybe` 并记 uncertainty，不进正式边表。

### 2. 前后向追踪 + 剪枝
- 后向：从种子取 `cited`，找奠基工作；前向：取 `citing`，找最新进展。
- 逐跳标 `hop`（1/2/…），超过跳数上限或被引低于阈值即剪枝，记剪枝理由。
- `python3 scripts/search_tool.py dedup records.json` 去重节点（同 DOI/标题合并）。

### 3. 共被引 / 耦合找平行工作
对目标文献，算共被引对（同被引用）与耦合对（共同引用），找快照内的平行/相近工作，标 `relation:"co-cited|coupled"` 与共享文献数。

### 4. 奠基与桥接节点识别
- 奠基：快照内被引次数最高的一批（给 `in_snapshot_citations`）。
- 桥接：连接两个主题簇的节点（给连接的两个簇）。只基于快照内数据，不引入外部引文数。

### 5. 作者身份合并
同一作者的不同拼写/缩写归一（`author_canonical`），留合并证据（同 DOI 共现/单位一致）；不确定的不合并，记待人工。

### 6. 计数闭合 + 增益对照
`python3 scripts/search_tool.py audit result.json`：`节点 → 去重 → 边 → 各跳命中` 闭合。增益对照：同种子同快照，基础 Agent vs 本 Skill 报——边表完整率、前/后向覆盖、平行工作发现数、人工核对条数。

## result.json 契约

```json
{"case_id":"","status":"pass|issues|partial|failed","protocol_version":"v1.0",
 "seeds":[{"id":"S1","title":""}],
 "nodes":[{"id":"N1","title":"","in_snapshot_citations":0}],
 "edges":[{"citing":"N1","cited":"N2","direction":"backward","source":"记录R3","hop":1}],
 "parallel":[{"id":"N5","relation":"co-cited","shared_refs":3}],
 "key_nodes":{"foundational":["N2"],"bridging":["N4"]},
 "counts":{"nodes":0,"edges":0,"hop1":0,"hop2":0},
 "gain":{"baseline_edge_coverage":null,"skill_edge_coverage":null},
 "unchecked":[],"sources":[],"uncertainty":[],"change_log":[]}
```

## 异常处置

| 异常 | 动作 |
|-|-|
| 引用关系无来源 | 标 `maybe`，不进正式边表，记 uncertainty |
| 种子文献元数据不全 | 该字段标 unknown，不臆造 DOI/年份 |
| 快照内无前向引用 | 明说"快照内未见前向引用"，不外推 |
| 作者身份无法判定 | 不合并，列候选交人工 |
| 网络过大 | 按剪枝规则截断，声明截断口径 |

## 底线
每条引用边有来源、每跳标方向与跳数、平行工作标明共被引/耦合、计数闭合、不臆造引用关系。不声称全局引文覆盖，不引入快照外引文数。
