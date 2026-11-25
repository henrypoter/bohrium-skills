---
name: web-reading-translation
description: 网页科研论文全文阅读与逐段中文翻译。用于出版社、arXiv、机构仓储或动态网页：识别干净正文，保留章节/公式/上下标/表格/图注/脚注，锁定术语译法，生成带 URL、抓取时间、DOM 锚点、逐字引文和 SHA256 的可回源双语产物；识别登录、付费墙、懒加载、分页、改版、超时与段落错位。
---

# 网页文献阅读与翻译 v3.0.0

## 何时使用、交付什么

用户给网页论文并要求阅读、提取、翻译、双语对照或逐条回源时使用。交付**干净正文 + 同序逐段译文 + 术语表 + 可复算来源定位 + 过程/失败轨迹**，而不是摘要、大纲或整页无锚点译文。

适用：公开静态 HTML、用户合法登录后用现有浏览器保存的渲染 DOM、题目直接提供的 HTML 快照。公式优先取 `<math alttext>` / LaTeX annotation，表格保留原始 HTML 和同形 Markdown，参考文献列表不混入正文，正文中的 `[1]` 引用标记保留。

不适用：绕过付费墙/验证码/访问控制，自动完成二次认证，未获授权的跨域传输，语义译文的全自动机判，或把工具通过声称为出版级人工审校。图片内文字/OCR、音视频和 PDF 不是本 Skill 的网页正文能力，标 `not_checked`。

## 输入、输出与依赖

- 先读真实 `/input/case.json`、`/input/task.md` 和题目列出的材料；不要根据文件名或领域标签猜正文。
- 工作文件放 `/app/work`，最终产物放 `/app/output`。尽早写 `result.json`，失败时保全已得产物。
- 脚本仅 Python 3 标准库，无 pip、Node、API key、外部翻译服务依赖。动态页面只使用平台已经提供的浏览器能力；本工具不自行绕过浏览器权限。
- 必须交付：`result.json`、`source.html`、`fetch.json`、`corpus.json`、`translation.json`、`bilingual.json`。后四者不存在时，`result.json` 必须标 `partial/failed` 并写具体缺口。
- 版本：`schema_version=2.0.0`、`skill_version=3.0.0`、`tool_version=3.0.0`。

下文 `$SKILL` 在评测环境为 `/skills/weekly-skill`，本地开发时为提交目录。

## 一次完整调用

### 1. 建任务与版本日志

从 case 找目标 URL、输入约束、权限及用户要求的输出字段，计算 case/task 的 SHA256。建 W1 抓取、W2 抽取、W3 翻译、W4 校验、W5 交付 DAG；每步有 `id/step/depends_on/input/output/state`，执行后立即写 `run_log`，不要结束才补。

### 2A. 静态网页：原字节抓取

```bash
mkdir -p /app/work/case /app/output
python3 $SKILL/scripts/webread.py fetch '真实 URL' \
  --out /app/work/case/source.html --meta /app/work/case/fetch.json \
  --timeout 20 --max-bytes 8000000
```

成功才得到 HTTP 状态、最终 URL、抓取时间、响应头、字节数和 SHA256。跨域重定向、401/402/403/407/429、超时、过大响应均非零退出并给结构化 `failure`；不要把失败响应当正文。429 按 Retry-After/指数退避有界重试；认证/权限/跨域停止交人工。

### 2B. 动态网页或题目快照：真实 DOM 盖章

用平台现有 Chromium/Playwright 正常访问，等待正文网络空闲，滚动图片/公式/表格进入视口，展开全部章节和分页，再保存最终渲染 DOM。若仍是登录页、订阅墙或骨架屏，停止；不要保存后谎称成功。浏览器轨迹记实际版本、滚动/等待/分页动作。

```bash
python3 $SKILL/scripts/webread.py stamp /app/work/case/source.html \
  --url '浏览器最终 URL' --out /app/work/case/fetch.json \
  --capture-method browser_rendered \
  --capture-notes '实际等待、滚动、分页与可见范围'
```

题目直接提供 HTML 时用 `--capture-method provided_snapshot`。`stamp` 不会伪称 HTTP 抓取，空文件拒绝盖章。没有真实 DOM 就无法用这一步补足权限。

### 3. 抽正文并先审覆盖，不立即翻译

```bash
python3 $SKILL/scripts/webread.py extract /app/work/case/source.html \
  --meta /app/work/case/fetch.json --out /app/work/case/corpus.json
```

逐块检查：
- `extraction_status=pass`、`complete=true` 才能进入完整翻译；`issues` 的分页/懒加载必须处理或降级，`failed` 不得以摘要代替全文。
- `coverage` 至少对照任务要求检查段落、标题、图注、表注、表格、公式、脚注；抽查首/中/末段的 `quote` 与原页面，确认无导航、相关推荐、引用工具、参考文献列表。
- 每块含稳定 `Bxxxx`、章节路径、`dom_path`、已有元素 `html_anchor` 或工具块锚点、全文字符区间、`quote=text`、`text_sha256`。`source` 含 URL、版本、抓取时间、快照哈希和正文根节点。
- 公式以 `\(...\)` 或 MathML 标记保留，上下标为 `_{}`/`^{}`；数据表输出 `table.rows/html` 及同形 Markdown；公式排版表标 `formula`，不要求翻译成 Markdown。
- `excluded` 是排噪审计，不应把其中参考文献重新塞回正文。若用户另行要求翻译参考文献，另建独立范围，不能悄悄混入。

### 4. 逐段翻译，术语先行

复制 `templates/translation_template.json`，将 `corpus_sha256` 和 `metadata` 从语料原样填入。作者、刊名、年份、DOI 与原题名字段不得改写；源未报告的元数据保留 `null`，不得猜。

1. 先通读全部块，建 `glossary`。每个概念写 `source`、`target`，同义词写 `source_variants`，合理缩写/后文形式写 `target_variants`。
2. 常规条目不写策略或写 `at_least_once_per_source_paragraph`。若需“首现全称+缩写、后文可缩写”，写 `occurrence_policy=first_full_then_abbreviation` 及 `first_target`；首现机检只允许全称形式。
3. 按 `corpus.blocks` 原顺序为**每个** Bxxxx 填一条 `{"id":"Bxxxx","target":"..."}`；不重排、不合并 ID、不漏标题/图注/表注/脚注。长句可在 target 内部断句，但不改变段落 ID。
4. 原样复制公式、数字、SI/其他单位、上下标标记、DOI/URL、行内引文标记。不计算或单位换算后冒充实录；表格 target 使用相同行列的 Markdown。不要在译文中新增原段不存在的公式、引用、DOI 或结论。
5. 每完成一批就保存，服务/模型中断后按缺失 ID 续译。`semantic_review` 单独记录人工或 Agent 的逐段语义复核；它不能改写工具固定的 `semantic_fidelity=not_checked_by_tool`。

### 5. 逐段机检并生成可回源双语产物

```bash
python3 $SKILL/scripts/webread.py align /app/work/case/corpus.json \
  /app/work/case/translation.json --out /app/work/case/bilingual.json
```

非零退出必须修正或降级。机检硬约束：错版哈希、缺/重/乱序 ID、空 target、公式/数字/单位/引用标记数量变化、凭空 DOI/URL/公式、表格变形、术语漂移、首现缩写违规、作者/刊名/年/DOI 改写。输出每段同时有原文、译文、位置与哈希。

工具不证明语义忠实。Agent 必须再做首/中/末段和任务重点段的语义抽查：查漏译、反译、补写、指代错误、公式上下文错接；记录抽查 ID、修改前后及剩余不确定性。

### 6. 写 result.json，回到原始 HTML 重算审计

按 `templates/result_template.json` 与下方契约组装最终 JSON，把 `bilingual.paragraphs` 原样嵌入；不要手工缩引文或改锚点。将最终文件复制到 `/app/output`，登记实际字节 SHA256。

```bash
python3 $SKILL/scripts/auto_tool.py schema /app/output/result.json
python3 $SKILL/scripts/auto_tool.py trace /app/output/result.json
python3 $SKILL/scripts/auto_tool.py audit /app/output/result.json \
  /app/work/case/bilingual.json --snapshot /app/work/case/source.html \
  --meta /app/work/case/fetch.json
python3 $SKILL/scripts/auto_tool.py resume /app/output/result.json
```

`audit` 会逐段比对 `order/kind/section/location/quote/source_sha256/target/formulas/table`，核对产物实际文件哈希，并从原 HTML 重新抽取重算 `corpus_sha256/full_text_sha256`。只验证 JSON 自洽而漏掉 `--snapshot --meta` 不算完整审计。

`pass` 仅当正文无已知抽取缺口、全部块对齐、无 errors/warnings/missing、工作流全 done、unchecked 为空、快照可重算、产物哈希一致。其余必须 `issues/partial/failed`，缺口写 `unchecked=[{"item":"...","reason":"...","status":"not_checked"}]`；早期失败可显式 `null`，不能编哈希。

### 7. 同输入基础 Agent vs 本 Skill 增益

仅在有两次**真实运行**时比较：同 case、同 `snapshot_sha256`、同权限，结果与日志均存在。按 `docs/README.md` 的 run-record 格式写 baseline/skill 记录，再运行：

```bash
python3 $SKILL/scripts/auto_tool.py compare /app/work/baseline-run.json \
  /app/work/skill-run.json --out /app/work/case/gain.json
```

将输出原样放到 `result.gain`。质量算正文抽取完整率、翻译覆盖率、引文可核验率、保护 token 保真率、术语一致率；效率算人工动作、重复抓取、耗时及差值。命令拒绝跨页面/跨权限/同 run-id/不可能计数。它不产生平台白板、不推断语义分，`official_platform_comparison` 默认 false。

没有基础 Agent 真实产物和日志时，必须：`gain={"status":"not_measured","reason":"平台未提供可比运行记录","baseline":null,"skill":null}`。平台生成白板时优先保留平台实测，不拿 bench 数字冒充实测。

## result.json 2.0.0 最小结构

```json
{
  "case_id":"实际ID", "status":"pass|issues|partial|failed",
  "schema_version":"2.0.0", "skill_version":"3.0.0", "tool_version":"3.0.0",
  "run_id":"唯一运行ID", "generated_at":"ISO-8601",
  "input":{"case_path":"/input/case.json","task_path":"/input/task.md","case_sha256":"64hex","task_sha256":"64hex"},
  "source":{"url":"...","fetched_at":"...","snapshot_path":"...","snapshot_sha256":"64hex","page_version":"...","root_dom_path":"..."},
  "corpus_sha256":"64hex", "full_text_sha256":"64hex", "extraction_status":"pass|issues|failed",
  "paragraphs":"bilingual.paragraphs 原样数组",
  "machine_verification":"bilingual.verification 原样对象",
  "workflow":[], "state":{"completed_steps":[],"failed_step":null,"resume_point":null},
  "data_passing":[], "failures":[], "run_log":[],
  "gain":{"status":"not_measured","reason":"...","baseline":null,"skill":null},
  "artifacts":[{"path":"...","sha256":"64hex","media_type":"application/json","role":"..."}],
  "unchecked":[], "sources":[], "uncertainty":[], "change_log":[]
}
```

失败记录统一：`step/kind/signal/action/state/retry/idempotency_key`。轨迹记录统一：`step/started_at/ended_at/result/command`。跨站交接必须有 `from/to/field_mapping/permission_scope=green|yellow|red`；red 禁止外传。

## 异常处置总表

以下均为执行规则，不是提醒。详细状态转换见 `templates/flow_spec.md`。

| 失败情形 | 识别信号 | 具体动作与降级 |
|-|-|-|
| 登录失效/二次认证 | 401；密码框/会话过期且正文不足 | 停在中断点，保存已得产物；人工正常登录后从 W1/W2 续跑；不代填验证码 |
| 付费墙/权限不足 | 402/403/407；订阅提示且正文不全 | 标 `blocked/partial`，注明所需合法订阅/权限；不输出正文已完成，不绕过 |
| 跨域/跨站权限 | 最终域改变；red 数据要外传 | `fetch` 停止；人工确认目标与新权限；red 不传，yellow 脱敏后传 |
| 动态渲染失败 | 只剩 script/骨架，正文块为 0 | 标 `dynamic_render_failed`；改用真实浏览器 DOM+stamp，仍失败交人工 |
| 懒加载未解析 | data-src 占位资源仍有缺 | 滚动并等待后重存；未解决 `complete=false`，相关图表标 not_checked |
| 分页 | rel/class next | 逐页抓取、编号、抽取与审覆盖；未合并齐全前 partial，不把第一页称全文 |
| 页面改版/元素缺失 | 根主节点无块，选择器失效 | 保存 DOM path/错误；检查 root/excluded；新增适配并跑零误杀 bench，仍缺交人工 |
| 超时/网络/限流 | timeout、URLError、429/5xx | 幂等 GET 有界退避；超过上限 failed+resume_point，不无限重试 |
| 翻译中断 | 部分 ID 无 target、空 target | 保存现有 translation；按 ID 续译；missing_blocks 未清前 partial |
| 段落错位 | 重/乱/额外 ID、corpus 哈希变化 | 禁止按序号强配；回到原 corpus ID 修复后重跑 align+audit |
| 公式/表格损坏 | token 计数变化、表格行列不同 | 从 quote/formulas/table 原样恢复；不得猜后补齐 |
| 字段缺失/类型错误 | 元数据缺、run totals 非整数 | 源未报告填 null+not_checked；改为真实类型，不填假值 |
| 同步冲突 | 同一记录源/目标均变化 | 两边及哈希都保留，记 `kind=sync_conflict,state=blocked` 交人工；不自动覆盖 |

## 自查与复跑

```bash
python3 $SKILL/bench/bench_run.py
python3 $SKILL/bench/bench_run.py --report /app/work/bench-report.json
```

每个命令均有正向零误杀和变异必命中用例。可复跑不是口头承诺：固定同一 HTML 与 meta，重新执行 `extract` 得同一 corpus 哈希；固定 translation 重跑 `align`；对 result 重跑 `audit`。页面变化或时间变化产生新快照版本，不复用旧哈希。
