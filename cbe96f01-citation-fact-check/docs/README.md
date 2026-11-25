# 引用与事实核验（v3.0.0）

把每条引用拆成“稿件论断 claim_quote”和“来源证据 source_quote”，双侧定位页/段并绑定 quote 与来源全文 SHA-256；再核 full/partial/none/unknown、来源版本/撤稿/权限。每份结果保留原 output_contract 和实际运行版本。

## 运行

Python 3 标准库，无安装和网络依赖。输入 `/input/case.json`、`/input/task.md` 与实际材料；快照在 `/app/work`，输出 `/app/output/result.json`。格式与最小 JSON 示例见 `SKILL.md`。

```bash
python3 scripts/review_tool.py locate claims.json --manuscript manuscript.txt --sources source-files.json
python3 scripts/review_tool.py align claims.json
python3 scripts/review_tool.py provenance source-metadata.json --registry registry.json
python3 scripts/review_tool.py verify issues.json --text manuscript.txt
python3 scripts/review_tool.py coverage result.json
python3 scripts/review_tool.py schema result.json
python3 scripts/review_tool.py gate result.json
```

前三个命令分别有 `--allow-partial`、`--allow-unknown`、`--allow-incomplete`，仅用于带 unchecked/uncertainty 的诚实降级，不将未知证据改成确定支持。`summary issues.json` 仅提供问题分布，不能代替 coverage。

## 合成示例与自测

`bench/fixtures/` 仅演示接口，不是组织方案例或预填答案。

```bash
python3 bench/bench_run.py
```

bench 同时含合法 full/partial/none、版本差异披露、显式 occurrence、权限 partial 的零误杀，以及伪引、歧义、错标支持、撤稿、版本和权限等变异；以当次日志实得通过数为准。

## 边界

`locate` 不做 PDF/OCR；`align` 是保守规则预警，不是通用语义蕴含；`provenance` 只核带来的 registry 快照，不实时访问数据库。来源全文/权限/版本不可得时必须 unknown/partial，哈希和 schema 通过也不自动证明科学判定正确。正式增益须来自同输入、同权限、同预算的平台真实对照。
