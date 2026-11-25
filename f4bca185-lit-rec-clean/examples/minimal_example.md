# 最小调用示例（合成脏数据，仅演示接口，非正式案例结果）

本例有三条抽取记录：前两条是不同写法的精确重复抽取，第三条属于不同实验，虽值相同也不能合并。输入为 `examples/minimal_input.csv`，规则为 `examples/rules.json`。

## 调用

在提交根目录执行：

```bash
mkdir -p /app/work/q6-demo-output
cat > /app/work/q6-demo-case.json <<'JSON'
{"case_id":"SYNTHETIC-Q6-DEMO","output_contract":{"required":["case_id","status","records","gain"]}}
JSON
python3 scripts/literature_clean.py clean \
  --input examples/minimal_input.csv --rules examples/rules.json \
  --case /app/work/q6-demo-case.json --out /app/work/q6-demo-output
python3 scripts/literature_clean.py audit \
  --input examples/minimal_input.csv --out /app/work/q6-demo-output
```

## 示意主结果（示例节选，不是正式测试输出）

`status=success`，`input_rows=3`、`output_rows=2`、`duplicate_rows_removed=1`、`review_pending=0`。第一条规范记录的关键字段如下：

```json
{
  "_lineage_id": "L000001",
  "paper_id": "P1",
  "experiment_id": "E1",
  "material": "alpha",
  "potential": "500",
  "concentration": "2000",
  "duplicate_count": 2,
  "_source_rows": "minimal_input.csv#1;minimal_input.csv#2"
}
```

- `0.5 V` 经规则 `R-POTENTIAL-DEMO` 真算为 `500 mV`，公式 `(0.5)*(1000)+(0)`。
- `2 g/L` 经规则 `R-CONC-DEMO` 真算为 `2000 mg/L`。
- `α` 与 `Alpha` 同义归一为 `alpha`；等价单位和同义词使前两条规范化签名一致。
- 前两条合并，但 `E2` 身份不同，保留为第二条。lineage 的第一条含两个 raw records，可逐字段回查。
- audit 输出 `ok:true`。若把第二行改成 `600 mV`，会产生 `DUPLICATE_CONFLICT` 且三行全保留；若写 `500 uV`，产生 `UNKNOWN_UNIT`，不会猜成 500 mV。

## 自查

```bash
python3 bench/bench_run.py
# BENCH PASS (33/33)
```
