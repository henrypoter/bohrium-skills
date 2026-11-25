# 修订说明（v2 → v3.0.0）

v2 主要验证通用 DAG，尚不能证明“正文抽对、逐段译对、凭产物回原文”。v3 将主流程改为可执行网页阅读闭环，并保留 DAG/恢复能力。所有新增运行脚本只使用 Python 标准库。

## 1. 实际效果（40）

### 完成度与正确性

- `webread.py fetch/stamp/extract` 从真实静态 HTTP 字节或真实浏览器最终 DOM 生成版本化语料；不再以通用“下载文件”代替论文正文。
- 正文抽取优先 `article/main/article-body/full-text`，剔除 nav/aside/footer/推荐/引用工具/参考文献列表；保留章节、段落、图注、表注、数据表、公式、上下标、行内引文和脚注。LaTeXML 公式排版表与数据表分开，无 `citation_author` 时可回退提取 `ltx_personname`，嵌套脚注不再内联重复。
- `align` 按稳定 Bxxxx 同集合、同顺序对齐。逐段检查公式/数字/单位/引用标记的出现次数，数据表 Markdown 行列与源 `table.rows` 一致，元数据不得改写；额外公式、DOI、URL 会被拦截。
- 术语由“全文固定一个词”升级为 `source_variants` 同义词、`target_variants` 显式后文形式和 `first_full_then_abbreviation` 首现全称策略，兼顾一致性与缩写规则。
- `audit` 不只看 schema：逐字段比对 result 与 bilingual，核验 artifact 实际 SHA256，并从原始 HTML+meta 重算 corpus/full-text hash，能抓产物被改写、页面版本错配与手造定位。

### 公开真实页面烟测

2026-11-25 对公开 arXiv HTML《Attention Is All You Need》执行了真实 `fetch + extract`（不是本地 mock），HTTP 200，快照 188797 bytes，响应带 Last-Modified/ETag；页面适配后提取 8 位作者。源快照 `sha256=b87e9eb92f31d614da88531928855d0a521ea20b2c9d437ddf8ba89a1c2e311b`；最终工具复测 `corpus_sha256=0ac6354ddcd6f769267dc013e00b1e64e82c4cc8df1b30e66399a2ec890d5fa0`，`extraction_status=pass`、`issues=[]`，128 块（67 段、30 标题、5 图注、4 表注、5 数据表、5 公式块、12 脚注），共 142 个公式。烟测产物在 `/tmp/webread-live-aac59bef`，未作为正式案例答案提交。

### 完整性与可核验性

`result.json` 新增 `schema_version/skill_version/tool_version/run_id/generated_at/input hashes/corpus_sha256/full_text_sha256/extraction_status/machine_verification/artifacts`。每段有：

`url + snapshot_sha256 + fetched_at + dom_path + html_anchor + block_order + char_start/char_end + quote + source_sha256 + target`。

完整状态与降级严格分离：`pass` 不允许分页/懒加载、缺段、警告、未 done 步骤或 unchecked；第一步登录失败也允许用显式 null 保存诚实 failed，而不会被 schema 逼着造哈希。

## 2. 使用增益（25）

新增 `compare BASELINE.json SKILL.json --out gain.json`：只接受相同 case、相同快照 SHA256、相同权限、不同 run-id 的两份真实运行记录，结果和日志路径必须存在且可读。自动计算：

- 质量：正文抽取完整率、翻译覆盖率、引文可核验率、保护 token 保真率、术语一致率；
- 效率：人工动作节省、重复抓取减少、耗时节省；
- 可核验性：两份证据文件 hash、比较输入 hash、原始计数与差值。

默认 `official_platform_comparison=false`，工具不推断语义翻译质量、不生成榜单成绩。没有真实基础 Agent 双跑时 result.gain 必须 not_measured 且 baseline/skill 为 null；bench 的合成双跑仅验证算术和防线，不声称实际用户增益。

## 3. 创新增益（15）

| 能力 | 可执行命令 | 相对基础 Agent 的边界/价值 |
|-|-|-|
| 字节级页面版本锁与跨域/登录前置判定 | `webread.py fetch` | 不再拿最终漂亮的文本掩盖错 URL、旧版本或权限页 |
| 真实浏览器 DOM 与题面快照接轨 | `webread.py stamp` | 不导入浏览器依赖也能让动态 DOM 进入同一审计链；不伪造 HTTP 抓取 |
| 正文结构/公式/表格/脚注分块 | `webread.py extract` | 相比整页复制，保留可翻译块、排噪证据和源结构 |
| 受保护 token + 表格形状 + 术语首现策略 | `webread.py align` | 相比模型自述“已检查”，可重复抓出具体保真/一致性错误 |
| 原 HTML 重算的逐字段审计 | `auto_tool.py audit` | 相比只查必填字段，能证明交付属于该快照且产物未改 |
| 同输入同权限双跑算术对照 | `auto_tool.py compare` | 把质量/效率声明落到运行证据和可重算指标，而非估计提升 |
| 失败上游不放行 + 断点恢复 | `auto_tool.py trace/resume` | 已完成步骤不重跑，异常不会静默传到最终“完成” |

明确边界：脚本没有语义翻译模型，不证明 target 的语义等价；动态渲染依赖平台现有浏览器，纯标准库命令只负责盖章/解析；不支持自动绕过验证码/订阅，也不覆盖 PDF/图片 OCR。

## 4. 可靠体验（10）

`SKILL.md` 和 `templates/flow_spec.md` 的异常表逐项包含**识别信号 + 动作 + 状态/恢复点**，覆盖：登录失效/2FA、懒加载、分页、元素缺失/页面改版、超时、权限不足、付费墙、跨域、动态加载失败、摘要页、限流、过大响应、无版本/哈希篡改、翻译中断、段落错位、公式/数字/单位/表格损坏、字段缺失/类型错误、同步冲突。

可靠性修复包括：正文完整时不因导航“Sign in”误杀；表注先于表格独立成块；作者脚注不再污染姓名；失败/阻塞依赖不能错误放行下游；早期失败可先落盘；429 单独有界恢复，不用无限重试。

## 5. 生态贡献（10）

- 文档：`SKILL.md` 全流程和契约，`docs/README.md` 安装、命令、格式、边界、对照和维护，`environment/resources.yaml` 明确零第三方 Python 依赖。
- 模板：result、translation、compare run、DAG/异常处置流程。
- 最小样例：`bench/fixtures/article.html`，仅合成回归材料，不是正式答案。
- 可复用脚本：网页阅读与交付审计分离，所有命令输出结构化 JSON、非零故障退出。
- 报告：`bench/last_report.json` 保存逐项 PASS/FAIL 与 X/Y，可用单一命令复跑。

## 验收结果与距榜首的已知差距

执行：`python3 bench/bench_run.py --report bench/last_report.json`。最终结果 **64/64，all_green=true**；报告 `passed=64/total=64`，逐项明细见 `bench/last_report.json`。每个 fetch/stamp/extract/align/trace/resume/schema/audit/compare 命令都有正向零误杀与变异必命中用例。

无法宣称“距榜首 X 分”：未提供榜首作品、官方白板或隐藏 3 案例评测结果。剩余可核验差距是：

1. 固定 3 案例 × 3 次上的真实语义忠实度和同白板质量/效率差值，需组织方运行，不能用本地样例替代。
2. 语义机检只覆盖结构与离散保真；漏译之外的反译、指代、语气仍需 Agent/人工逐段复核。
3. 多栏视觉阅读顺序、重大资产重组 DOM、图片内文本与 PDF 不是通用保证；需要目标页面快照抽查，失败必须降级。
4. 需登录/2FA/订阅和复杂动态分页仅在合法人工权限与平台浏览器条件下可接续，本地故障 bench 证明识别/处置，不证明已获隐藏案例权限。
