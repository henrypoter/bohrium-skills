# 学术规范与合规检查修订说明（错配版 → v3）

日期：2026-11-25；工具版本：`3.0.0`；结果契约：`2.0.0`。旧目录实为 `method-statistics-review`，本版已按本题完整重写为学术诚信、引用、隐私数据、版权、伦理和投稿合规 Skill。只改本题提交目录，未修改共享核心、提交或 push。

## 1. 实际效果（40）：六分面 + 可回源的证据整改闭环

### 完成度与正确性

- `SKILL.md` 和 `templates/checklist.md` 已完全去掉“方法统计”定位，逐项映射 integrity/citation/privacy/copyright/ethics/submission。
- `index + verify` 对主/辅证据执行逐字 quote、起止偏移、页/行/段/句、source/quote SHA-256 回验；来源未提供会失败，不再用空白归一化冒充逐字一致。
- `schema` 强制事实错误、证据不足、规范问题、建议四型，confirmed/needs_review、严重度、依据、可执行 fix。空泛“注意/建议检查”不能通过；缺失声明必须有 searched scope + source hash 的 absence_evidence。
- privacy/license/guidelines 产生的候选能够直接进入统一 result 契约，并已通过真实 `verify` 集成测试，不停留在提示框架。

### 完整性与可核验性

- `coverage` 强制六合规分面逐项 checked/partial/not_applicable/not_checked 及范围/理由，零 issue 不能冒充已经审查。
- `result.json` 强制结果和工具版本、case_id、原始文件/抽取文本双哈希、解析器、sources、unchecked、uncertainty、change_log。
- 指南依据必须有 version/date；缺指南不得借其他期刊条款。隐私候选不自动等于违法，许可缺失不自动等于侵权，伦理声明关键词不自动证明授权。

## 2. 使用增益（25）：真实同条件对照才生成 gain

新增 `compare`：同 case、同文本 SHA-256，强制记录共享 permissions/allowed_sources/budget，两臂每个 issue 独立裁决 supported/unsupported/unresolved，读取真实耗时、人工核对时间和返工轮次。输出 decided precision、误报率及质量/效率差值；跨输入、漏裁决、缺共享条件记录均失败。无平台真实基线时 result 必须为 `gain.status=not_measured`，不把 synthetic bench 数值写成正式提升。

## 3. 创新增益（15）：三个可执行的合规新增能力

1. **隐私与受限数据：** `privacy` 检测邮箱、手机号、labeled 姓名/地址/病历号和受限数据；身份证号包括出生日期合法性与校验位验证，公开通讯作者邮箱上下文抑制，减少“18 位数字即身份证”的误报。每条给去标识/限权动作和授权待核状态。边界：未命名身份、准标识符组合、图像/声音/基因组交人工。
2. **第三方许可：** `license` 对第三方图/表/代码/数据集查许可缺失，识别 ND + adapted 的改作冲突，给出补授权或替换位置。边界：不是图像/代码取证，不直接作侵权法律结论。
3. **投稿规则：** `guidelines` 将真实指南的 required_pattern/required_section/max_words/max_pages 执行成 pass/issue，保留版本、日期、actual/limit、缺失检索哈希和整改动作。边界：无真实指南不运行；字数算法不同需降级，不冒充官方口径。
4. `citations` 另提供数字引用断链及本文论断—题录配对，但题录匹配绝不自动成为语义支持结论。

## 4. 可靠体验（10）：题面失败情形逐条给信号与动作

`SKILL.md` 异常表覆盖材料缺页/无法解析、引用信息不全、依据条款获取不到、受限数据、目标期刊指南缺失，并扩展图片/代码不可读、伦理批件范围不明。每行有识别信号和重试、降级、unchecked、限制外发或交人工动作；受限数据禁止上传，缺指南不造规则，缺批件不直接判无伦理。

## 5. 生态贡献（10）：重写资源并全量变异自测

- 更新 `SKILL.md`、`docs/README.md`、`templates/checklist.md`、工具、合成稿件和可回验 good_result 示例。
- `scripts/review_tool.py` 共 9 个纯标准库命令：index、verify、citations、privacy、license、guidelines、coverage、schema、compare。
- `bench/bench_run.py` 对每个命令执行正向零误杀 + 变异必命中，另验证隐私身份证校验、CC BY 正向、ND 改作、指南超限/缺失、跨稿件比较和受限证据集成。
- **最终 bench：33/33 PASS。** 运行命令：`python3 bench/bench_run.py`；good_result 另通过 verify/coverage/schema。

## 距离榜首/满分仍需真实证据的部分

- 未运行组织方隐藏三案，不能声称官方准确性、漏报率、效率或排名；真实三案独立基线对照仍是主要缺口。
- 未命名个人身份、准标识符组合、图像复用、代码相似、复杂 PDF/OCR、作者—年份引用和法律/伦理最终判断仍需人工或外部实际证据。
- privacy/license 是可复核候选生成器而非全覆盖合规裁定；真实误报/漏报和指南计数适配需在三案及更多领域样本上测量。
- `GITHUB_URL.txt` 仍指向旧 `9e7302fd-method-statistics-review`，已确认与新作品错配。未虚构新仓库地址；必须由作品负责方改为实际公开 URL 并做未登录验证，否则公开链接附加分无法取得。
