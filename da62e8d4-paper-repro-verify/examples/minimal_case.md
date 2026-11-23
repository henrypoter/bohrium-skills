# 最小调用示例（**示例**：材料为作者自拟短文，非平台正式案例，输出为示意）

## 1. 自拟短材料（模拟"论文片段 + 两个候选方法"）

> 论文片段（虚构）："我们用复合梯形法计算 I=∫₀¹ sin(x)dx，取 n=100 个子区间，
> 得 I≈0.4597（Table 1，float64，4 位有效数字）。随机种子固定为 42。"

候选方法（案例包内 `methods.py` 形式提供的两份实现，此处内联演示）：
- 方法 A：复合梯形法，`n=100`。
- 方法 B：复合辛普森法，`n=100`。

## 2. 调用步骤（命令为示意路径，实际按 /app/work 组织）

```bash
SKILL=/skills/weekly-skill
# 0) 先写诚实骨架（status=partial）
python3 $SKILL/scripts/reprokit.py init --case-id demo-001 \
  --fields reproduction_checklist,environment,parameter_table,metric_card,runs,statistics,sensitivity,comparison,attribution,verdict_summary \
  --out /app/output/result.json
python3 $SKILL/scripts/reprokit.py env --out /app/work/env.json
# 1) 参数表（n=100 论文明示→paper；积分上下限文中未给→self/uncertainty）
python3 $SKILL/scripts/reprokit.py params --table /app/work/params.json --md /app/work/params.md
# 2) 口径卡：对照前强制校验定义/划分/聚合/精度（不一致会阻断 compare）
python3 $SKILL/scripts/reprokit.py card --spec /app/work/card.json --out /app/work/card_out.json
# 3) 运行两个候选方法（精确解析解 1-cos(1)=0.4596976941…；论文值 0.4597 系自拟声明值）
python3 - <<'PY'
import math, json
def trap(f,a,b,n):
    h=(b-a)/n; return h*(0.5*f(a)+sum(f(a+i*h) for i in range(1,n))+0.5*f(b))
def simp(f,a,b,n):
    h=(b-a)/n; return h/3*(f(a)+f(b)+4*sum(f(a+(2*i-1)*h) for i in range(n//2))+2*sum(f(a+2*i*h) for i in range(1,n//2)))
print("A", trap(math.sin,0,1,100))   # 0.4596938633（已实跑核对）
print("B", simp(math.sin,0,1,100))   # 0.4596976942（已实跑核对）
PY
# 4) 多种子统计协议（含随机性时 ≥5 种子；本数值积分为确定性，仅演示接口）
python3 $SKILL/scripts/reprokit.py stats --runs /app/work/runs.json --out /app/work/stats.json
# 5) 缺失/自设参数敏感性扫描（方法文件须提供 evaluate(**params)->dict）
python3 $SKILL/scripts/reprokit.py sensitivity --method /app/work/methods.py \
  --grid /app/work/grid.json --out /app/work/sensitivity.json
# 6) 二维对照（数值等级×证据等级；本示例为独立重实现→T3）
python3 $SKILL/scripts/reprokit.py compare --spec /app/work/spec.json --out /app/work/compare.json
# 7) 8 类归因单校验（cause 命中枚举 + evidence 必填）
python3 $SKILL/scripts/reprokit.py attribution --table /app/work/attribution.json --out /app/work/attribution_out.json
```

## 3. 示意输出（**示例**，摘自各 JSON）

```json
{"card_out": {"ok": true, "checked_metrics": 1, "mismatches": [], "missing_fields": []}}
{"compare.rows[0]": {"metric": "I_sin_0_1", "method": "A", "paper": 0.4597, "repro": 0.45969386,
  "rel_err": 1.34e-05, "numerical_grade": "复现一致", "evidence_grade": "T3",
  "verdict": "复现一致 × T3", "cause_candidates": ["随机性/种子", "统计波动"]}}
{"stats.rows[0]": {"metric": "I", "n": 5, "mean": 0.45974, "ci95": [0.45960, 0.45988],
  "paper": 0.4597, "paper_in_ci": true}}
{"sensitivity.sensitivity_ranking": [{"parameter": "n_grid", "level": "不敏感",
  "max_rel_range": 3.28e-05, "dominates_conclusion": false}]}
{"attribution_out": {"ok": true, "by_cause": {"随机性/种子": 1}}}
```

随后回写 result.json：comparison 填二维结论（注明 Table 1 定位）、
attribution 记"残差为截断/舍入量级（随机性/种子+统计波动）"、
verdict_summary="部分复现（数值容差内 × T3；论文未报告积分上下限推导细节→uncertainty）"。
若论文值缺失（paper=null），数值等级自动"无法验证（材料不足）"，须登记 missing_materials。
