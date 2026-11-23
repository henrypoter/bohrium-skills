# 最小调用示例（自拟材料，仅演示接口）

自拟 demo-formulas.xml（单条 MathML 公式 v_esc = sqrt(2GM/R)），正文给出
G=6.674e-11 m^3/(kg·s^2)、M=5.972e24 kg、R=6371 km、v_esc≈11.2 km/s。

```xml
<formulas><math id="eq-esc"><mrow><msub><mi>v</mi><mi>esc</mi></msub><mo>=</mo><msqrt><mfrac><mrow><mn>2</mn><mi>G</mi><mi>M</mi></mrow><mi>R</mi></mfrac></msqrt></mrow></math></formulas>
```

## 调用

```bash
python3 scripts/formula_parse.py demo-formulas.xml --json /tmp/parsed.json
# -> LaTeX: v_{esc} = \sqrt{\frac{2 G M}{R}}, 符号: v_esc, G, M, R
cat > /tmp/dim.json <<'EOF'
{"units": {"G": "m^3/(kg*s^2)", "M": "kg", "R": "m", "v_esc": "m/s"}, "checks": [{"name": "v_esc", "lhs": "v_esc", "rhs": "sqrt(2*G*M/R)"}]}
EOF
python3 scripts/verify.py dim /tmp/dim.json

cat > /tmp/num.json <<'EOF'
{"checks": [{"name": "v_esc", "expr": "sqrt(2*G*M/R)",
  "values": {"G": 6.674e-11, "M": 5.972e24, "R": {"value": 6371, "unit": "km"}},
  "expected": {"value": 11.2, "unit": "km/s"}, "rtol": 0.01}]}
EOF
python3 scripts/verify.py num /tmp/num.json

python3 scripts/verify.py equiv 'v_{esc} = \sqrt{\frac{2 G M}{R}}' '\sqrt{2 M G / R} = v_{esc}'
python3 scripts/verify.py selftest   # 应 11/11 passed
```

## 示意输出（示例）

dim：`verdict: consistent`（两端 `L^1 T^-1`）。num：`computed 11185.9, rel_err
0.0013, match: true`，`normalized` 记 `6371 [km] -> 6371000.0`。不一致/不匹配时
dim/num 输出 warning、仍退出码 0（告警不阻断）。equiv：`{"equivalent": true}`。
结论写入 result.json：`status: success`；G/M/R 记 `origin: explicit_in_text`；
未给推导时 derivation_steps 记 `evidence: null` 并写入 limitations。
