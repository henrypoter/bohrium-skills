# REVISION v4 — 科研成果转化写作专用重构

日期：2026-11-25。仅修改本题 submission，未改共享核心，未提交或 push。

## 纠偏

旧版是 `results-discussion-writer`，把本题误缩成 Results & Discussion 起草，无法覆盖公众科普、项目材料、双语或结构化成果转化。本版 SKILL 改为 `research-translation-writer`，以题面“读得懂/留得住/说得准/接得住”建立专用闭环，旧 rd_check 不再是工作流入口。

## 按评分维度的实际改动

### 实际效果（40）

新增纯标准库 `scripts/transfer_check.py`：

- `evidence`：重开实际来源，quote 逐字回查（仅规范空白），核对行号/JSON 字段，数字 surface 回 quote；未人工裁决的数据冲突直接 fail。
- `audit`：required 保留、来源绑定、数字+单位、图表、术语别名、缩写展开、公众白话解释、论断强度、体裁小节、篇幅、逐段 before/after/reason/evidence、涉密/未发表处置全部成为可执行硬约束。
- `result`：case_id、output_contract 全字段、交付文件、complete 闭环和 gain 协议机检。

### 使用增益（25）

`result.gain` 强制同输入、同约束、同权限、同预算；完成的 A/B 必须有相同输入 SHA-256、数值 metrics 和证据路径。平台未提供 baseline 时只允许 `pending_platform`，禁止把自拟 fixture 当真实基础 Agent 成绩。机检报告提供行号和证据 id，直接降低通读与返工定位成本。

### 创新增益（15）

实现“受众画像→required 取舍→术语锁定→证据强度边界→多文体映射→逐段复核”链条。相对基础 Agent 的边界：不是依赖模型自觉声明来源，而是重开文件逐字核验；不是只润色语言，而是阻断证据删除、数字漂移、论断升级和无记录覆盖。详见 `docs/positioning.md`。

### 可靠体验（10）

SKILL 异常表逐条覆盖题面点名的缺引用、数据自相矛盾、体裁与篇幅冲突、涉密、未发表；另分材料缺失/无法判断/运行失败，给识别信号、动作和状态。增加 200 段稳定性回归与 partial 先行纪律。

### 生态贡献（10）

新增/重写 project、brief、多文体、result、段落记录模板；重写最小示例、终审清单、数据格式、能力边界、评分覆盖和 bench 报告。全部脚本无第三方依赖。

## Bench 证据

`python3 bench/bench_run.py --write`：**20/20 全绿**。evidence 1 正向+3 变异，audit 1 正向+9 变异，result 1 正向+3 变异，另 1 个长稿稳定性断言；结果写入 `bench/bench_results.json`。修复过程中发现“句。[S1]”被切成独立标签句的正向误报，已兼容两种来源标注位置并复跑。

## 距榜首仍缺的证据/能力

1. 组织方固定 3 案例上真实基础 Agent vs Skill 的语言质量、人工编辑条目和返工轮次；本地 fixture 不替代该证据。
2. 扫描 PDF/OCR 读图、复杂图表像素取数、DOI 真实性和领域结论正确性仍需专用工具或专家。
3. 数值等价换算目前要求人工确认并补底账；更多学科表述可能出现未知误报/漏报。
4. 未提供可匿名访问的 GitHub 公开链接，附加分无法由本次本地迭代保证。
