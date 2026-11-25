---
name: patent-evidence-search
description: 专利与技术文献专用检索：分角色规范号码、简单族/扩展族重算、当前官方法律状态边界、版本化权利要求逐字段引证、绿黄红授权降级及可复跑增益对照
---

# 专利与技术文献检索：号码—族—状态—权利要求—证据闭环

用于从专利号或技术主题出发，在**题包实际提供的授权快照**中定位专利、归并同族、核对法律事件与权利要求版本，并发现同主题技术文献。每条结论必须回到原始响应或原始文本的字段/句子。

**边界**：不是通用文献筛选或系统综述；不做专利撰写、侵权判定、FTO、价值评估。有限观察链接不是完整同族，文本相似或同族不等于权利要求范围相同。历史授权事件不等于“当前有效”。不得绕过登录/付费墙、上传受限材料或展示红色来源原文。

## 调用与产物

1. 读取 `/input/case.json`、`/input/task.md` 及 `environment/resources.yaml`；先保留题目原 `output_contract` 的全部字段与 `case_id`，再增加本 Skill 的审计字段。
2. 在 `/app/work/` 保存实际原始响应、OCR/字段抽取文本和查询日志；在 `/app/output/result.json` 尽早写诚实 partial，随后增量完善。工作表格式见 `templates/worksheets.md`。
3. 工具均只依赖 Python 3 标准库（安装后可用 `/skills/weekly-skill/scripts/search_tool.py`）：

```bash
python3 scripts/search_tool.py normalize records.json  # 号码角色规范化
python3 scripts/search_tool.py family records.json     # 两种族口径及成员重算
python3 scripts/search_tool.py status legal.json       # 事件排序与当前状态可得性
python3 scripts/search_tool.py gain comparison.json    # 有真实 qrels 时的公平对照
python3 scripts/search_tool.py audit result.json       # 交付前硬审计；失败返回 1
```

## 专用流程

### 0. 界定对象与授权，先于下结论

- 将任务拆为 `number_query`、`topic_query`、国家/语种、时间、技术文献范围、所需权利要求版本。公开号、申请号、授权号、优先权号是四种角色，禁止相互填充。
- 逐来源登记 `id/name/version/query_date/path/sha256/access`；查询还要绑定原始响应 `source_id`。`path` 指向实际保留文件，JSON 引文字段使用 `documents[0].title` 这类路径。
- 授权等级：**绿**可按来源许可展示必要字段；**黄**仅展示 `allowed_fields`，其余只报元数据或缺失；**红**只记录来源名、权限失败与人工途径，不读/不展示原文。许可不明按黄或红降级，不猜权限。

### 1. 号码定位与规范化

对每条记录保留原号码和角色，再运行 `normalize`。种类代码（如 A1/B2）保留；申请号带种类代码或无法解析会失败，不能“修”成看似合法的号码。随后用 `field_bindings` 将输出中的号码、标题、优先权等绑定到原字段；`audit` 会重新读取并比对，而非只检查格式。

### 2. 简单族与扩展族分开归并

- **简单族**：规范优先权集合完全相同，或有明确 `simple_family_id`；同族标识内优先权冲突会失败。
- **扩展族**：共享至少一个规范优先权或明确 `extended_family_id`，用传递并查集归并。
- 运行 `family`，把输出的成员组写入 `families.simple/extended`。`audit` 会从记录重新计算并逐组比较，漏成员、错并和不同口径混用均不通过。
- 固定保留 `complete:false`、`claim_scope_equal:false`。未返回的族成员写“未观察/未覆盖”，不能写“不存在”；不能由关键词相同或申请人相同归族。

### 3. 法律事件与当前状态分离

逐事件记录 `status/effective_date/source_id/official` 和逐字证据，运行 `status` 排序。只有本次查询了当前官方登记、存在官方事件且输入明确的 `declared_status`，才可得到 `official_current`；其他情形为 `not_checked/official_events_only/secondary_only/conflict` 且 `current_status:"unknown"`。若官方状态陈旧，用 `official_stale` 并写滞后。转载页只能作二手线索。`audit` 强制“非 official_current 不得给确定当前状态”。

### 4. 权利要求只作有版本的文本事实陈述

每个版本分别写 `version/locator_scope/scope_comparison/evidence`，引文逐字定位到 claim 号和源字段。比较可写 `different_text/not_assessed/unknown`，不得仅据同族、摘要或相似文本写 `equal/equivalent`。不总结成侵权覆盖范围。

对 USPTO 原件先读实际页面，不能按文件名猜内容。WO 或多页 OCR 必须保留页/段边界：每段单独定位，**不得把两个字段或两页拼成一条逐字引文**；跨页未明处标 `unresolved`，必要时保留原页图供人工核查。

### 5. 技术主题与技术文献采用不同检索逻辑

- 专利：号码精确查询 + 关键词/同义词 + IPC/CPC + 申请人 + 引证关系；逐项记录实际使用字段，没执行的组合不得写成已执行。
- 技术文献：标题/摘要主题词、DOI、实际 Crossref/EuropePMC/出版者响应；不能用专利族规则合并论文。
- 每条 `queries[]` 保存原始查询、库、字段、日期、授权、返回数和 `source_id`。每条候选写 `include/exclude/unresolved + relevance_reason + evidence`；同主题论文放 `technical_literature`。空命中与接口失败分开。

### 6. 计数、遗漏与风险闭环

`raw >= deduplicated = len(records)`，且 `include + exclude + unresolved = deduplicated`。遗漏必须指到具体查询、字段、库覆盖或权限；不得用“检索全面”兜底。风险至少标注：字段缺失、状态未核验/过期/冲突、族口径、OCR 边界、库覆盖、授权降级。`pass` 不得仍有未解释 `unresolved`。

### 7. 同输入同权限增益，不预造基准

平台提供对照时，将其真实运行标识和指标写入 `gain.platform_observed`。有本地真实 qrels 时，以 `gain.json` 明确同一 case、相同权限、k、基线/Skill 排名与实际成本，运行 `gain`，保存 `qrels_ref` 和完整输出；P@k、R@k、nDCG@k、成本节省由脚本计算。没有基线或 qrels 就写：

```json
{"mode":"not_measured","reason":"平台对照尚未提供；不预填基准或提升值","metrics":null}
```

## 异常识别与动作

| 情形 | 识别信号 | 必做动作 |
|-|-|-|
| 限流/超时 | 429、超时、响应不完整 | 记录查询和错误；该库标未覆盖；按授权重试一次或降级本地快照；不得写成零命中 |
| 鉴权失败/权限不足 | 401/403、登录墙、许可不明 | 停止抓取；黄级仅保留允许字段，红级去引文；给人工授权路径与未完成项 |
| 检索无命中 | 成功响应且 result 数为 0 | 保留空原始响应；依次检查号码角色/格式、同义词、分类号和字段；每轮留查询；仍为空则报空而非造记录 |
| 法律状态冲突 | 同日官方事件不同或官方/转载不一致 | 当前状态设 `unknown`、`verification:conflict`；列双方来源日期，要求官方人工复核 |
| 状态过期 | 查询日期旧、仅历史事件 | 标 `official_stale` 或 `official_events_only`；不得从“曾授权”推出“现有效” |
| 字段缺失/格式冲突 | 号码、日期、优先权为空或多源不同 | 保留空值与各源字段；绑定失败则 `unresolved`，不跨角色补号、不猜优先权日/申请日 |
| 族关系不明 | 无优先权、优先权冲突、仅观察链接 | 保持单例或报冲突；简单/扩展族分列；完整性和权利要求等同均为 false |
| OCR/跨页不明 | WO 合并文本、乱码、句界跨页 | 回到原页；按段引证；无法唯一定位则缩小引文或标 `unresolved`，不拼句 |
| 元数据冲突 | 同字段不同值 | 保留各来源值和绑定，选值须有官方优先级理由；无法裁决则并列，不静默覆盖 |

## result.json 专用骨架与最终门

完整可运行示例见 `bench/fixtures/good_result.json`（**合成自测夹具，不是正式案例答案**）。核心结构：

```json
{
  "case_id":"...","status":"pass|issues|partial|failed",
  "research_scope":{},"queries":[],"records":[],"technical_literature":[],
  "families":{"simple":[],"extended":[],"complete":false,"claim_scope_equal":false},
  "legal_status":[],"claims":[],
  "counts":{"raw":0,"deduplicated":0,"include":0,"exclude":0,"unresolved":0},
  "coverage":{"scope":"finite_snapshot","global_novelty":false,"miss_attribution":[]},
  "sources":[],"uncertainty":[],"gain":{"mode":"not_measured","reason":"...","metrics":null},
  "change_log":[]
}
```

每条记录还需 `field_bindings`；每条证据需 `{source_id,field,quote,locator}`，重复引文加 `span:[start,end]`。最终运行 `audit /app/output/result.json`：它检查来源哈希、黄红授权、引文逐字唯一回源、字段值、族重算、状态边界、计数和增益证据。**非零时不得宣称完成**；保留实际产物、`partial/issues` 与错误清单，修复后能重跑通过再改状态。
