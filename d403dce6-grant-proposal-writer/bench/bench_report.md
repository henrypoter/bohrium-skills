# 公平对照与校验器夹具报告（bench）

本报告数据由 `bench/bench_run.py` 生成，可一键复跑：`python3 bench/bench_run.py`（退出码 0 = 全部符合预期；结果同时落 `bench/bench_results.json`）。夹具为**自拟材料**（`bench/fixtures/`，非官方评测案例），仅用于路径对照与校验器验证。

## 1. 校验器夹具：正向零误杀、变异必命中

| 夹具 | 构造 | 期望 | 实测 |
|-|-|-|-|
| `good_draft` | 合规七要素草稿（全部论断挂引、缺口↔内容双向、创新点逐条锚定） | check PASS 且 issues=0 | **pass**（正向零误杀） |
| `mut_banned_word` | 创新点插入「填补国内空白」 | FAIL + 禁用词 | pass |
| `mut_uncited_claim` | 立项依据「提升至 78%」摘掉 [S2] | FAIL + 缺引 | pass |
| `mut_orphan_gap` | 新增无内容承接的 缺口G3 | FAIL + 孤儿缺口 | pass |
| `mut_orphan_content` | C2 摘掉「回应缺口Gx」 | FAIL + 孤儿内容 | pass |
| `mut_undefined_gap` | C3 改引未定义的 缺口G9 | FAIL + 未定义 | pass |
| `mut_p_out_of_range` | 前期成果改挂清单外 [P5] | FAIL + 越界 | pass |
| `mut_s_out_of_range` | 论断改挂清单外 [S9] | FAIL + 越界 | pass |
| `mut_inno_no_anchor` | 创新点2 摘掉全部对比证据 | FAIL + 锚定 | pass |
| `mut_prior_no_pref` | 前期论断摘掉 [P1] | FAIL + 未挂P | pass |
| `mut_missing_section` | 整节删除「科学问题」 | FAIL + 章节缺失 | pass |

其中 `mut_undefined_gap` / `mut_s_out_of_range` / `mut_missing_section` 是本轮核对中**先用夹具复现的真实漏检**（v2 全部误判 PASS），修复后均转为必命中；修复点见 `scripts/run_grant.py` v3（缺口定义仅限立项依据段、新增 [S#] 越界校验、新增章节齐全校验）。

## 2. 异常与稳定性场景

| 场景 | 期望 | 实测 |
|-|-|-|
| task.md 缺失（指南不明） | init exit 0，继续工作 | pass（每次 pipeline 均覆盖） |
| case.json 解析失败（材料缺失） | exit 0，降级 partial 并登记 material_gaps | pass |
| 超长输入（70 条材料） | 台账截断 60 条且不崩溃 | pass |
| 重复运行 check | check_state 两次逐字段一致 | pass |
| init 复跑 | 不覆盖已写骨架与 result.json（幂等） | pass（v2 会覆盖 result.json，v3 已修） |
| pack 打包 | status=complete、used_in 三级对应回填、四件产物齐备 | pass |

## 3. 路径开销对照（确定性，仅机械核对环节）

同一自拟案例、同一合规草稿，「机械核对环节」（编号证据、核引文覆盖、数要素对齐、缺口↔内容双向比对、回填来源映射、画路线图）：

| 指标 | baseline（无 Skill，模型上下文内手工核对） | skill（init/check/pack） |
|-|-|-|
| 机械核对动作数 | 18（通读+编号 2、逐行核引 3、数四要素 4、双向比对 5、回填映射 3、画图 1） | **3 次 CLI 调用，0 次模型请求** |
| 机械核对需进入模型上下文的字符 | 1542（材料+草稿全文） | **229**（只读 check 报告），降 85.1% |
| 核对结论可机器复核 | 不可（手工结论无留痕） | 可（check_state.json + check_report.md 落盘，可复跑） |

## 边界（不夸大）

- 本对照度量**机械核对环节**的操作数与上下文开销、以及校验器对已知违规的检出能力；**不**度量 LLM 端到端写作质量——后者由平台固定案例与基础 Agent/Skill Agent 白板对照负责，本报告不声称「写得更好」。
- 引文覆盖为行级启发式（论断线索正则），不构成「引文确实支撑该论断」的语义核验，最终由 `checklists/consistency_checklist.md` 人工复核兜底。
- 夹具为材料学科自拟样例；跨学科泛化以通用线索词兜底，未在多学科真实案例上实测。
