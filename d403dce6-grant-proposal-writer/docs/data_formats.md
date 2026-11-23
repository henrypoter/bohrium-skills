# 数据格式规范（可复用）

本 Skill 的中间态与产物均为纯 JSON / CSV / Markdown / Mermaid 文本，**无私有二进制格式**，
可被其它工具直接读取、复用与再加工。路径约定：`/app/work/`（中间态）、`/app/output/`（交付物）。

## 1. `evidence_ledger.json`（证据台账，init 产出）

```json
[{"id": "S1", "source": "case.json.references[0]", "type": "文献", "excerpt": "材料原文片段（≤400字符）"},
 {"id": "P1", "source": "case.json.applicant_preliminary[0]", "type": "申请人前期基础", "excerpt": "…"}]
```

| 字段 | 说明 |
|-|-|
| `id` | 文献/领域材料编号 `S1…Sn`，申请人前期基础编号 `P1…Pm`；正文引用写作 `[S1]`/`[P1]` |
| `source` | 材料在 case.json 中的 JSON 路径，可逐条回溯 |
| `type` | `文献` / `领域材料` / `申请人前期基础`（按 JSON 路径关键词 + 文献特征正则分类） |
| `excerpt` | 材料原文片段（截取 ≤400 字符），不改写、不虚构 |

超长输入截断为前 60 条。台账是 [S#]/[P#] 越界校验与 `used_in` 回填的清单依据。

## 2. 正文标号约定（skeleton.md / draft.md）

| 标号 | 含义 |
|-|-|
| `[S#]` / `[P#]` | 论断来源：文献/领域材料 / 申请人前期基础 |
| `[✓]` / `[→]` | 已完成 / 拟开展 |
| `【待补充：…】` | 材料缺口，check 自动登记到 result.json `material_gaps` |
| `缺口G#` | 立项依据段尾的缺口编号（只在此处定义） |
| `C#（对应G#，回应缺口Gx）` | 研究内容条目，回挂目标与缺口 |
| `R#（对应C#）` / `指标#（对应G#）` / `创新点#（对应C#，对比[S#]）` | 路线/指标/创新点回挂 |

## 3. `matrix.csv`（要素映射表，模型填写）

```csv
goal_id,content_id,route_step,metric
G1,C1,R1 缺陷表征与建模,模型误差≤15%
```

四列齐全且 `content_id` 非空的行由 check 生成 `route_map.mmd`（Mermaid flowchart，按行串联 G→C→R→指标）。

## 4. `check_state.json` / `check_report.md`（check 产出）

```json
{"passed": true, "coverage": 1.0, "gaps": ["1","2"], "contents": ["1","2","3"],
 "n_priors": 1, "n_sources": 2, "missing_sections": [],
 "counts": {"研究目标": 3, "研究内容": 3, "技术路线": 3, "考核指标": 3}, "issues": 0}
```

`check_report.md` 为人读版，分节：引文覆盖 / 创新点禁用词与锚定 / 缺口↔内容 / 证据编号越界 /
要素数量与章节齐全 / 待补充 / 已完成与拟开展统计；问题行以 `- [标签]` 前缀列出（缺引/禁用词/锚定/孤儿缺口/孤儿内容/未定义/越界/未挂P/缺失/不齐）。

## 5. `result.json`（output_contract，init 写 partial，pack 写终版）

| 字段 | 说明 |
|-|-|
| `case_id` | 来自 case.json（`case_id` 或 `id`，缺省 `unknown`） |
| `status` | `partial`（骨架/部分完成）/ `complete`（章节稿已交付） |
| `deliverables` | `proposal_sections` / `route_map` / `consistency_report` 路径 |
| `source_mapping[]` | `{evidence_id, source, type, used_in:[章节名…]}`；`used_in` 由 pack 扫描终稿回填，构成「段落—要素—证据」三级对应 |
| `checks` | check 摘要：`passed/coverage/n_priors/counts/issues_count`；未运行 check 时为 `{passed: null, note: …}` |
| `version_boundary` | `change_records`（修改留痕）/ `manual_confirmation` / `material_gaps`（材料缺口）/ `conflicts`（材料间冲突）/ `anomalies` |
| `sources` | 输入文件清单 |
| `uncertainty` | 不确定性与降置信声明 |
| `meta` | `skill/ts/task_excerpt` |

完整示例见 `examples/result.example.json`（标注为示例，非正式案例结果）。

## 6. 安装与维护

- **安装**：无需安装。平台将本包挂载为 `/skills/weekly-skill/`；唯一依赖 Python ≥3.8 标准库
  （argparse/csv/json/re/sys/time/pathlib），离线可用，无 pip、无网络。
- **自验**：修改 `scripts/run_grant.py` 后必须重跑 `python3 bench/bench_run.py`
  （正向零误杀 + 变异必命中 + 异常场景，exit 0 即通过）。
- **维护**：新增校验规则须同时在 `bench/bench_run.py` 增加对应变异夹具（先复现再修），
  并同步 `checklists/consistency_checklist.md` 与本文件；schema 变更保持向后兼容读取，新增字段不影响旧消费方。

## 复用约定

- 消费方只需实现 §1（台账）与 §2（标号）两个最小约定，即可复算任一论断是否可追溯到材料。
- `matrix.csv` 四列可被任意表格工具编辑；`route_map.mmd` 可被 Mermaid 生态渲染。
- 台账 `excerpt` 始终为材料原文，允许第三方对照 case.json 逐字核验。
