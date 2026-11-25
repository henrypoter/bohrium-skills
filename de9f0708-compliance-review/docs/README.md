# 学术规范与合规检查 Skill v3 使用说明

## 安装、入口与依赖

提交目录即完整 Skill，入口 `SKILL.md`。所有新增脚本只用 Python 3.8+ 标准库，无网络、无第三方包。PDF/OCR 等前置解析只使用 `environment/resources.yaml` 实际提供的能力；本工具不伪造解析状态。

## 快速开始

```bash
# manuscript.txt 必须来自本次实际材料
python3 scripts/review_tool.py index manuscript.txt --out index.json
python3 scripts/review_tool.py citations manuscript.txt --out citations.json
python3 scripts/review_tool.py privacy manuscript.txt --out privacy.json
python3 scripts/review_tool.py license manuscript.txt --out license.json
# 仅在实际指南已转成 guide.json 时执行：
python3 scripts/review_tool.py guidelines guide.json manuscript.txt --out guidelines.json
# Agent 审查其余内容、整合候选并完成 checked_scope 后：
python3 scripts/review_tool.py verify result.json --source manuscript_text=manuscript.txt
python3 scripts/review_tool.py coverage result.json
python3 scripts/review_tool.py schema result.json
python3 bench/bench_run.py
```

校验退出码：0 通过/领域扫描运行成功，1 校验失败或引用断链，2 用法、读取或 JSON 错误。privacy/license/guidelines 发现候选时 `ok=true,status=issues`，这是审查结果而非脚本故障；不能用退出码忽略 findings。

## 命令与产物

| 命令 | 可核验输出 | 适用边界 |
|-|-|-|
| `index` | 页/行/段/句/偏移、section、source/quote SHA-256 | 扫描件、复杂分栏依赖前置抽取质量 |
| `verify` | 所有主/辅证据逐字回源并核对坐标、哈希、重复项 | 不做语义裁决；来源未传入直接失败 |
| `citations` | 数字引用—题录映射、断链定位、待核 claim/source pair | 作者—年份和语义支持需人工；不猜元数据 |
| `privacy` | 邮箱/手机号/校验身份证/labeled 姓名地址病历号/受限数据、具体去标识动作 | 准标识符、无名身份、图像声音基因组需人工 |
| `license` | 第三方素材许可缺失、ND + 改作候选、原文及授权/替换动作 | 不做像素或代码相似取证，不直接判侵权 |
| `guidelines` | 版本化规则 pass/issue、actual/limit、缺失搜索范围和改动目标 | 无真实指南不运行；计数口径须与官方一致才可确认 |
| `coverage` | integrity/citation/privacy/copyright/ethics/submission 六分面覆盖 | 零问题不等于已检查 |
| `schema` | 版本、证据、依据、严重度、缺失检索、fix、gain 硬约束 | 仍需 verify 回原文 |
| `compare` | 同输入、独立裁决质量及真实效率差值 | 无真实基线/完整裁决则 not_measured 或失败 |

## 最小 synthetic 示例

```bash
python3 scripts/review_tool.py privacy bench/fixtures/sample_paper.txt --out /tmp/example-privacy.json
python3 scripts/review_tool.py license bench/fixtures/sample_paper.txt --out /tmp/example-license.json
python3 scripts/review_tool.py verify bench/fixtures/good_result.json \
  --source manuscript_text=bench/fixtures/sample_paper.txt
python3 scripts/review_tool.py schema bench/fixtures/good_result.json
```

样稿含 labeled 患者姓名和一条带 CC BY 的改作图说明。privacy 应标出姓名，license 不误报 CC BY 条目。`good_result.json` 是字段示例，**不是正式测试答案**；身份证号等处必须使用合成数据，不得把真实受限信息放入 bench。

## 指南 JSON

必需元数据：`guide_version/guide_date/source/rules`。规则格式：

- `required_pattern`：id/kind/description/pattern，可选 section。
- `required_section`：id/kind/description/pattern。
- `max_words`：id/kind/description/section/limit；工具口径为 Han 字符 + 英文/数字 token。
- `max_pages`：id/kind/description/limit；以 form-feed 页计数。

不支持未知 kind，避免悄悄漏查。无实际指南时 submission 必须 not_checked/partial，不得拿示例 guide 当真。

## 对照、隐私与维护

基线比较格式见 SKILL.md。两臂需同 case/text hash/权限/预算、全量逐条裁决和真实 runtime。scanner 的 quote 属于受控证据；共享报告优先使用定位、哈希和去标识化替代文本。规则更新须同步版本、REVISION 与正向零误杀 + 变异必命中 bench。
