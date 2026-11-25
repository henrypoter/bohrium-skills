---
name: academic-compliance-review
description: 学术规范与合规检查。基于实际论文/科研材料审查学术诚信、引用、隐私数据、版权许可、伦理与投稿要求；提供逐字原文、精确定位、可核对依据、严重度和可执行整改。内置隐私标识扫描、第三方素材许可检查、版本化期刊指南机检和公平基线比较。
---

# 学术规范与合规检查：证据先于结论，授权不靠猜测

输出是可复核的 `result.json`，不是“建议注意学术规范”的泛化提醒。发现标识符不等于判定违法，出现“知情同意/许可”关键词也不等于授权成立；必须检查它是否覆盖当前数据、素材和使用方式。本 Skill 不提供法务意见、正式伦理委员会意见、学术不端认定或代投稿。

## 1. 输入、输出和边界

1. 读取实际 `/input/case.json`、`/input/task.md`、材料及 `environment/resources.yaml`；保留原始 `output_contract` 的全部字段和 `case_id`。PDF 必须由实际 PDF 现场解析，领域标签不能替代原文。
2. 解析文本存 `/app/work/manuscript.txt`；最终写 `/app/output/result.json`，可附 `privacy.json`、`license.json`、`guidelines.json`、`issues.md`。示例仅为 synthetic fixture，不是正式案例答案。
3. 只使用任务允许的资料。外部题录、许可文本、作者指南无法获取时标 `not_checked/needs_review`，不得编造 DOI、条款、许可或指南版本。
4. 所有脚本仅 Python 3 标准库。受限材料只在允许环境本地处理，不上传外部服务。

## 2. 先建立可复核坐标

```bash
cd /skills/weekly-skill
python3 scripts/review_tool.py index /app/work/manuscript.txt --out /app/work/index.json
python3 -c 'import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' /path/to/original_input
```

`index.json` 固定文本哈希、页/行/段/句和 Unicode 起止偏移。`manuscript_version` 分开记录原始文件哈希、抽取文本哈希及解析器。任何 issue 必须含 `location + 逐字 quote + quote_sha256 + evidence[] + basis[] + fix`；缺失项须另有 `absence_evidence`，不能用空白 quote 冒充证据。

## 3. 六个合规分面逐项闭环

| 类别 | 检查与成立条件 | 不能直接下结论的情况 |
|-|-|-|
| `integrity` 学术诚信 | 数据/图像复用、重复发表、署名、利益冲突、基金/致谢一致性；引冲突双方及实际制度 | 相似表述不直接等于抄袭或重复发表；交人工核原始记录 |
| `citation` 引用规范 | 存在性、元数据、正文论断与被引主张对应、格式一致 | 未读到被引来源不得声称张冠李戴；不猜 DOI |
| `privacy` 隐私与数据合规 | 直接标识符、受限/未公开数据、授权与伦理适用范围 | 扫描命中是待复核风险，不直接判违法；关键词不等于授权 |
| `copyright` 版权与许可 | 图/表/代码/数据集来源、许可类型、署名、改作与复用条件 | 无许可文本时只判“未建立复用依据”，不断言侵权 |
| `ethics` 伦理审查 | 人/动物研究、知情同意、批件编号、风险获益与设计匹配 | 缺资料为 evidence insufficient；不能替代伦理委员会判断 |
| `submission` 投稿要求 | endpoint 规则版本/日期、章节、声明、字数/页数等映射 | 无目标指南不得套用其他期刊规则 |

`checked_scope` 六项分别填 `checked / partial / not_applicable / not_checked`。`checked` 必须有 `search_scope`，其他状态有具体 `reason`；未涉及不是静默省略。

### 3.1 引用题录与论断映射

```bash
python3 scripts/review_tool.py citations /app/work/manuscript.txt --out /app/work/citations.json
```

自动处理数字方括号引用、区间及参考文献映射，输出本文原句和题录 span；`support` 初始永远为 `not_checked`。作者—年份引用须人工配对；被引来源实际可读后才能判断 supported/contradicted/partial/unclear。

### 3.2 隐私与受限数据机检（本作品重点新增能力）

```bash
python3 scripts/review_tool.py privacy /app/work/manuscript.txt --out /app/work/privacy.json
```

检测邮箱、中国大陆手机号、带出生日期及校验位验证的居民身份证号、 labeled 姓名/地址/病历号、显式受限数据。每条候选带精确原句、规则 ID 和去标识化/限制访问动作；输出 `possible_safeguards` 仅作为人工核对线索，授权状态仍为 `not_established`。公开通讯作者邮箱有上下文抑制，校验失败的身份证号不因“18 位数字”误报。无名身份、准标识符组合、人脸/声音/基因组列入 unchecked，不宣称零风险。

**受限证据处理：** scanner 为复核保留受控 quote/hash；对外问题清单使用定位、哈希和去标识化替换文本，不扩散标识符。只有输入权限允许时才保留受控证据，不上传。

### 3.3 第三方图/表/代码/数据集许可机检

```bash
python3 scripts/review_tool.py license /app/work/manuscript.txt --out /app/work/license.json
```

对明确写有 reproduced/adapted/转载自/改编自等来源的素材，检查同段是否有许可或单独授权；无许可给出来源与许可补全或替换动作。ND 许可与改作并置时给出“需单独授权/替换”候选。文本无法证明图片像素复用或代码相似，相关检查进 unchecked。

### 3.4 目标期刊/会议指南版本化机检

仅把**实际提供或实际获取的指南**转为 `/app/work/guide.json`：

```json
{"guide_version":"实际版本", "guide_date":"实际发布日期/获取日期", "source":"实际URL或文件",
 "rules":[
  {"id":"abstract-limit", "kind":"max_words", "section":"Abstract|摘要", "limit":250, "description":"Abstract ≤250 words"},
  {"id":"ethics", "kind":"required_pattern", "pattern":"Ethics|伦理", "description":"Ethics statement required"},
  {"id":"coi", "kind":"required_section", "pattern":"Conflicts? of Interest|利益冲突", "description":"Conflict statement section"},
  {"id":"pages", "kind":"max_pages", "limit":12, "description":"At most 12 pages"}
 ]}
```

```bash
python3 scripts/review_tool.py guidelines /app/work/guide.json /app/work/manuscript.txt --out /app/work/guidelines.json
```

`required_pattern`、`required_section`、`max_words`、`max_pages` 逐条输出 pass/issue、actual/limit、依据版本日期、定位和修复。`max_words` 口径为 Han 字符 + 英文/数字 token；若目标指南采用其他口径须改写规则实现或标 not_checked，不冒称官方字数。缺失项有完整检索范围哈希。指南不存在就不要创建 guide.json，也不要借用“常见要求”充当条款。

## 4. 严重度、类型和修复

- `type` 严格区分 `fact_error / insufficient_evidence / normative_issue / suggestion`。
- `critical`：直接标识泄露或有证据表明核心复用/伦理条件严重不符；`major`：授权、引用、伦理或许可依据不完整且影响发布；`minor`：局部格式不一致。候选风险常先 needs_review，不因扫描命中自动 critical。
- `fix.action` 使用 `replace/add/remove/clarify/verify/restrict/deidentify/obtain_permission`，`target` 是具体句/节，`instruction` 是实际替换、补授权、限制访问或替换素材动作。空泛“注意/建议检查”会被 schema 拒绝。
- `basis` 对指南必须含 `version/date`；其他规则必须含 `kind/source/locator/statement`。未获得的依据不能用于 confirmed 结论。

## 5. 交付硬闸

```bash
python3 scripts/review_tool.py verify /app/output/result.json \
  --source manuscript_text=/app/work/manuscript.txt [--source ref_1=/app/work/ref_1.txt]
python3 scripts/review_tool.py coverage /app/output/result.json
python3 scripts/review_tool.py schema /app/output/result.json
```

`verify` 要求所有实际来源，逐字检查 quote、起止偏移、页/行/段/句和源/quote SHA-256，检查重复；`coverage` 查六类实际覆盖；`schema` 查 `result_schema_version=2.0.0`、`tool_version=3.0.0`、case/status、证据、类型、严重度、指南版本日期、缺失检索、fix 和 gain。失败先修复；否则如实 partial/failed。

`result.json` 顶层至少含：`result_schema_version`、`tool_version`、`case_id`、`status=pass|issues|partial|failed`、`manuscript_version`、`issues`、`checked_scope`、`gain`、`unchecked`、`sources`、`uncertainty`、`change_log`，以及原始 output_contract 要求的其他字段。完整 synthetic 示例见 `bench/fixtures/good_result.json`。

## 6. 同输入基础 Agent vs 本 Skill

只有平台实际提供/生成对照时才测量：两臂同 case、同文本 SHA-256、同允许资料/网络权限和预算；独立裁决每个 issue 为 `supported/unsupported/unresolved`，记录真实耗时、人工核对时间和轮次。

```bash
python3 scripts/review_tool.py compare /app/work/baseline.json /app/output/result.json \
  --decisions /app/work/decisions.json --out /app/work/gain.json
```

`decisions.json` 含 `case_id/text_sha256/permissions/allowed_sources/budget/baseline/skill`，共享权限、资料范围和预算均为必填，两臂 issue IDs 必须完全裁决。把输出并入 `gain`：包含 decided precision、误报率、unresolved 数、质量差值和效率差值。输入哈希不同或裁决不完整会失败；没有真实基线则 `gain={status:not_measured,reason:...}`，bench 的示例数值不得冒充正式增益。

## 7. 异常处置表（题面点名情形逐条落地）

| 失败情形 | 识别信号 | 具体动作 |
|-|-|-|
| 材料缺页或无法解析 | 文件读取失败、UTF-8 strict 失败、index 为空、页数与材料清单不符 | 换实际可用的第二解析器/`-layout` 重试；记录缺页和失败页；关联分面 partial、未读范围 unchecked；全文不可读则 failed，不补造内容 |
| 引用信息不全 | `citations` 无文献表/悬空条目，题录缺字段或被引全文不可得 | 仅确认实际存在的断链；其余题录真实性/支持关系 needs_review，citation partial；不猜元数据、不自动判引而不证 |
| 依据条款获取不到 | 规则 URL/文件未提供、读取失败、版本无法核对 | 将依赖该依据的检查设 not_checked/needs_review，basis 记录实际缺口；不得引用记忆中条款或给 confirmed 规范结论 |
| 材料涉及受限数据 | 输入权限标记、privacy 命中直接标识/受限数据、存在未公开数据路径 | 停止外发和联网处理；在受控目录保存证据，报告尽量用哈希/定位/替代文本；privacy partial 或 needs_review，执行 deidentify/restrict，必要时交数据负责人/伦理人工复核 |
| 目标期刊指南缺失 | case 无目标 venue，或无实际 guide 版本/日期/原文 | submission 设 not_checked（若只有部分内容则 partial），写明缺指南；不运行伪规则、不套用其他期刊；只审其他五分面 |
| 图片/代码实际内容不可读 | 只有 caption、二进制损坏、渲染失败 | 可审 caption 的来源/许可文字，像素复用/代码相似 unchecked；不得声称“图片无复用” |
| 伦理批件/授权范围不明 | 只有“已获批准/同意”而无编号、日期、主体或适用范围 | 锚定声明原句，设 needs_review，fix=verify/add 要求核对批件和数据/素材使用范围；不直接判无伦理审批 |

## 8. 自测、资源与维护

```bash
python3 bench/bench_run.py
```

清单在 `templates/checklist.md`，使用细节在 `docs/README.md`。工具提供模式识别和可核验约束，不覆盖未命名身份、图像取证、代码相似性或法律判断。修改规则/版本必须同步更新 REVISION 和正向零误杀 + 变异必命中 bench。
