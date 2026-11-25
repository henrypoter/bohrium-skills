# 科研知识库问答 v3（qa_tool 1.0.0）

## 用途与完成标准

多文件问答必须逐论断回指具体文件、完整内容 SHA-256、版本/角色和页段行坐标；无依据问题明确 `no_evidence + missing`；矛盾证据分版本并列；索引异常不得静默跳过。`qacheck` 是交付硬闸，但它只验证引文存在性和坐标，不宣称自动证明科学语义蕴含。

## 新命令（纯 Python 标准库）

```bash
python3 scripts/qa_tool.py index library/ --text-dir extracted/ --versions versions.json --output index.json
python3 scripts/qa_tool.py search index.json --query "设置温度" --limit 8
python3 scripts/qa_tool.py search index.json --query "设置温度" --include-history
python3 scripts/qa_tool.py qacheck result.json --index index.json
```

- `index`：清点目录、文件类型、权限、来源和完整哈希；UTF-8/HTML/DOCX 直接提取，PDF/扫描件读取有来源的 UTF-8 文本侧车；生成页段行 chunk、重复组、候选/声明版本与异常。
- `search`：默认只检索 current canonical 文档，返回可直接引用的原文与坐标；`--include-history` 显式召回历史；零命中输出 `no_evidence`，但仍需换词与范围检查。
- `qacheck`：重算 index 指纹，逐论断核对 path/hash/version/role/chunk/exact quote/locator；检查 no_evidence 的 missing/search、冲突双锚点、检索范围和全部索引异常闭环。

原 `scripts/file_tool.py inventory/checkmap/schema` 保留作字节与目录清单补充，不能代替 QA 回链。

## 异常覆盖

文件不可读/解码错误、扫描件无文本、PDF 未提取、权限不足、目录为空、空文件、版本冲突、证据互相矛盾、重复副本、索引被修改。完整处置表见 `SKILL.md`。

## 自测

```bash
python3 bench/qa_bench.py       # 30 个正向/变异检查
python3 bench/bench_run.py      # 原 file_tool 10 个回归检查
```

测试使用临时合成库，覆盖正常零误杀与错哈希/版本/坐标/引文、缺证、无搜索、范围造假、空目录、扫描无文本、不可读、版本冲突、冲突缺双证据等必命中变异，不使用正式案例。

## 边界

本工具不是完整 PDF/OCR 引擎。PDF 页码来自提取文本侧车的 form feed；没有页界时为 null，不猜页码。复杂表格、扫描 OCR 和语义蕴含仍须实际工具与人工/模型复核。不访问私人账户，不虚构缺失工具状态、来源、版本或平台增益。
