# 评分点逐项核对表

对照 PROBLEM.md 评分表逐得分点给出「实现状态 + 可复核证据」。「部分」项如实标注未覆盖部分与原因，不做无依据声称。自测入口：`bash ../tests/run_tests.sh`（仓库内 `tests/`，17/17 PASS，exit 0）与 `python3 bench/bench_run.py`（3/3 PASS，exit 0）。

## 一、实际效果（40）

| # | 评分点 | 状态 | 可复核证据 |
|-|-|-|-|
| 1 | 任务完成度：把真实稿件按目标模板改到可交付，而非只改几处看得见的格式 | **已实现** | **一条命令出成稿**：`tpl_fit.py --guide <模板> --source ms.tex --out out/ms.tex --render` 内联解析+修改+渲染+留痕，PDF 复制到成稿同目录（tex 与 docx 两条路径，`tests` 有 one-command/docx 用例）；确定性规则覆盖纸张/字号/栏数/四边距/行距/文献样式/字体 7 类 preamble，幂等、绝不改源稿；+ 渲染 PDF + unified diff；`tests/run_tests.sh` 变异 A：`ms_bad.tex` pre 7 fail → tpl_fit 7 项改动 → post 12 pass 且编译 ok；`bench` c2 同路径复跑 |
| 2 | 结果正确性：格式规格与内容同时正确，不误判、不错改内容 | **已实现** | 校验「正向零误杀、变异必命中」均有夹具：正向 `ms_good.tex`/`ms_inch.tex`（1in=2.54cm 单位换算后 0 fail）→ 全 pass；变异 `ms_bad.tex` → 7 fail 命中；fidelity 段比对改稿前后图/表/公式/脚注/引用/章节计数，内容单元变动即告警；编译门禁只认「PDF 存在且最终 .log 无致命 `! `」 |
| 3 | 结果完整性：模板检查项与原稿内容单元都被覆盖 | **部分** | 已覆盖：纸张/页边距/栏数/字号（含小四→12pt）/行距/图注表注位置/文献样式/页数上限（编译后实测）/包冲突。**未覆盖（诚实列入 `unverified_items` 交人工）**：三线表、标题层级与编号、页眉页脚、字体嵌入、目录与页码刷新、结构必填件（CCS/ORCID/版权声明） |
| 4 | 结果可核验性：他人可按提交材料复现并逐项核对 | **已实现** | spec 每项带 `source_file`+`source_line`；模板 sha256 指纹；`<out>.fit.json` 含 applied/changes/unified diff；`changes.jsonl`（ts/file/rule/before/after/reason）；`init_result.py --finalize` 缺字段退出 1；`bench/bench_run.py` 一键复算 |

## 二、使用增益（25）

| # | 评分点 | 状态 | 可复核证据 |
|-|-|-|-|
| 5 | 质量增益：同输入同模板同权限下优于基础 Agent | **部分** | 确定性对照：机器可判定检查项 0→35、留痕 0→7 条、保真计数 0→6 类（`bench/bench_results.json`）。**未覆盖**：LLM 端到端改稿质量对照需平台 harness 固定案例，本地不声称 |
| 6 | 效率增益：减少逐项核对、重复排版、试错导出与返工 | **已实现** | `bench` 聚合：全功能路径动作数 55→11（-80.0%）；**主路径 lean 55→6（-89.1%，每样例 2 条命令）**，上下文 4003→767 字符（-80.8%）；模板解析内联进成稿命令（不再 parse→check→fit 三步）；幂等改稿消除重复跑插入 |
| 7 | 增益可验证性：通过公平对照证明改善 | **已实现** | `bench/bench_run.py`（baseline 手工流程 vs skill 确定性路径，双路径同样例）+ `bench/bench_report.md` + `bench/bench_results.json`；报告显式声明度量范围与 baseline 模型假设，exit 0 可复核 |

## 三、创新增益（15）

| # | 评分点 | 状态 | 可复核证据 |
|-|-|-|-|
| 8 | 新增能力：基础 Agent/现有工具不具备或难稳定实现 | **已实现** | 从模板/规范反推检查项清单（file+line 证据 + sha256 版本指纹 + `\ProvidesClass` 版本）；包冲突预检（natbib+biblatex 等 4 类）；确定性**幂等**改稿（几何选项语义比较，顺序无关、单位归一，二次运行 applied=0）；转换后保真计数比对 |
| 9 | 方法改进：模板解析/样式映射/内容锚定/转换导出校验实质改进 | **已实现** | checklist-as-code；冲突规定保留全部值显式 flag 不静默二选一；中文字号映射与 cm/mm/in 单位归一换算；编译只扫最终 .log 消除多轮残留假阳性；告警式 readiness（error/warning/info，deliver 恒 true 不 fail-closed） |
| 10 | 创新证据：证明相对已有方案的边界和价值 | **已实现** | `docs/positioning.md`：与基础 Agent 手工、chktex 类语法检查、期刊模板+人工核对、提交前检查服务逐项能力矩阵 + 明确「不做什么」；`bench` 提供与 baseline 的可复跑对照 |

## 四、可靠体验（10）

| # | 评分点 | 状态 | 可复核证据 |
|-|-|-|-|
| 11 | 调用与易用：Agent 正确触发，用户按说明完成一次完整适配 | **已实现** | SKILL.md 合法 frontmatter（name/description），**主路径 4 条命令**（备料+骨架 / 一条命令出成稿 / 可选校验 / 收口），SKILL.md 6125 B（细节按需查阅 §5）；§2 成稿目标值表 + 对照示例；§6 最小调用示例（自拟材料并标注"示例"）；`docs/quality_bar.md` 目标值全表 |
| 12 | 运行稳定：不同模板类型/稿件长度/环境/重复运行持续可用 | **部分** | 已测：tex/cls/sty/docx/dotx/txt/md/pdf 解析；纯标准库无 pip；缺 latexmk/xelatex/pdftotext/soffice 降级；tpl_fit 幂等（二次 applied=0）；result.json 覆盖需 --force。**未覆盖**：长稿件/大模板压力测试、docx 端到端自动改稿（当前为解析比对+渲染目检半自动） |
| 13 | 异常处理：模板缺失或版本不明、字体缺失、样式冲突、转换失败、内容无法保真 | **已实现** | SKILL §3 异常表与评分点 5 场景逐行对应，且**一律不阻断交稿**：模板缺失→undeterminable 不编造规格；版本不明→versions 缺失写 uncertainty；字体缺失→mutation C 实测（编译 fail 但 deliver=true、level=partial、退出码 0）；样式冲突→规范冲突保留双值 + 包冲突预检（mutation B 实测）；转换失败→编译门禁降级 attempted=false/office 预览；内容无法保真→fidelity 计数不一致即告警否则 partial |

## 五、生态贡献（10）

| # | 评分点 | 状态 | 可复核证据 |
|-|-|-|
| 14 | 文档完整性：使用说明/依赖/支持模板范围/示例/限制/维护 | **已实现** | SKILL.md：§1 主路径、§2 成稿目标值、§3 异常、§4 result.json、§5 按需查阅、§6 依赖/限制/示例；`docs/quality_bar.md` 成稿质量基线；`docs/data_formats.md` 接口速查；`SOLUTION.md` 记录实现与自查史 |
| 15 | 资源可复用性：Skill 本体/检查项清单/样式映射脚本/样例输入输出可复用 | **已实现** | 4 个脚本均为独立 CLI（纯标准库）；`docs/data_formats.md` 定义 spec/compliance/fit/changes/result 五种 JSON 格式；题集 `bench/cases/`（规范+三类稿件+bib）+ 期望 `bench/golden/` + 评分脚本 `bench/bench_run.py` |
| 16 | 分享推广价值：可分享的检查清单、案例、实践经验 | **已实现** | `bench/bench_report.md`（对照方法+边界声明范式）；`docs/positioning.md`（能力矩阵与取舍）；`tests/` 正向+三类变异夹具集（校验类"零误杀/必命中"实践样例）；检查清单样例即 `spec.json` schema |

## 未覆盖项（如实声明）

1. **LLM 端到端质量对照**：平台 harness 固定案例才能测，本地只有确定性路径对照，故第 5 条为「部分」。
2. **自动规则未覆盖的检查项**：三线表、标题层级、页眉页脚、字体嵌入、目录刷新——均进 `unverified_items` 交人工，不假装已核。
3. **docx 端到端改稿**：当前为解析比对 + `soffice` 渲染目检的半自动路径，无确定性 docx 样式注入。
4. **长稿件/大模板压力测试**：样例均为小篇幅自拟 fixtures；bench/baseline 的 ops 与 ctx 为文档化模型而非实测计时。
