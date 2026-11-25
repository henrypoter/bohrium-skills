#!/usr/bin/env python3
# fixture_test.py: 正向零误杀 / 变异必命中 / 异常场景 回归（仅标准库）。
# 用法: python3 fixture_test.py ；退出码 0=全过, 1=有失败。夹具在 fixtures/，均为自拟样例。
import json, os, subprocess, sys, tempfile, time, importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.dirname(ROOT)
FIX = os.path.join(ROOT, "fixtures")
SKELETON = os.path.join(SUB, "scripts", "skeleton.py")
CHECK = os.path.join(SUB, "scripts", "result_check.py")
OUT = tempfile.mkdtemp(prefix="w3q5_fixture_")
failures = []
n_checks = [0]

def check(name, cond, detail=""):
    n_checks[0] += 1
    print(("%s %s" % ("PASS" if cond else "FAIL", name)) + (" | " + str(detail)[:110] if detail else ""))
    if not cond:
        failures.append(name)

def skel(name):
    out = os.path.join(OUT, name + ".json")
    r = subprocess.run([sys.executable, SKELETON, os.path.join(FIX, name + ".md"), "-o", out],
                       capture_output=True, text=True, timeout=90)
    check("skeleton[%s] exit 0" % name, r.returncode == 0, r.stderr.strip())
    return json.load(open(out, encoding="utf-8")) if r.returncode == 0 else {}

spec = importlib.util.spec_from_file_location("skeleton_mod", SKELETON)
sk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sk)

# ---------- 断句单元（英文缩写/引用锚点不偏移） ----------
s1 = sk.split_sents("As Fig. 1 shows, the scheduler sorts tasks by arrival time. The scheduler has two stages.")
s2 = sk.split_sents("We compare with Zhang et al. (2023). Their method differs.")
check("split_sents Fig. 不碎句", len(s1) == 2 and s1[0].startswith("As Fig."), s1)
check("split_sents et al. (2023). 不碎句", len(s2) == 2 and s2[0].startswith("We compare"), s2)

# ---------- 正向夹具：零误杀（shingle 近逐字跨节复述=0 且 边界候选=0；echo 与仲裁级候选不视为误杀） ----------
for name in ("pos_zh", "pos_en"):
    d = skel(name)
    cross_shingle = [c for c in d.get("redundancy_candidates", [])
                     if c["channel"] == "shingle" and c["position"] == "cross"]
    check("正向[%s] 零近逐字跨节误杀" % name, len(cross_shingle) == 0, cross_shingle)
    check("正向[%s] 零边界误报" % name, len(d.get("boundary_candidates", [])) == 0, d.get("boundary_candidates"))
    check("正向[%s] 无截断误报" % name, d.get("truncation_suspect") is False)
    check("正向[%s] 无体裁/空稿误报" % name,
          not any(w and w[0] in ("empty_input", "no_academic_structure") for w in d.get("warnings", [])))

# ---------- 变异夹具：必命中 ----------
d = skel("var_zh")
pairs = {tuple(sorted(c["pair"])) for c in d.get("redundancy_candidates", [])}
check("变异[var_zh] 跨节复述必命中", ("S2.P1.s1", "S3.P1.s2") in pairs, sorted(pairs)[:4])
check("变异[var_zh] 强因果结论必命中", any(b["para"] == "S5.P1" for b in d.get("boundary_candidates", [])),
      d.get("boundary_candidates"))

d = skel("var_en")
pairs = {tuple(sorted(c["pair"])) for c in d.get("redundancy_candidates", [])}
check("变异[var_en] 跨节复述必命中(锚点含Fig修正)", ("S2.P1.s1", "S3.P1.s2") in pairs, sorted(pairs)[:4])
check("变异[var_en] 强因果结论必命中", any(b["para"] == "S5.P1" for b in d.get("boundary_candidates", [])))

d = skel("var_nohead_zh")
pairs = {tuple(sorted(c["pair"])) for c in d.get("redundancy_candidates", [])}
check("变异[无标题] 段间复述必命中", ("S1.P1.s1", "S1.P2.s2") in pairs, sorted(pairs)[:4])
check("变异[无标题] 结尾段强因果必命中(回退通道)",
      any(b["para"] == "S1.P3" for b in d.get("boundary_candidates", [])), d.get("boundary_candidates"))

# ---------- 异常场景 ----------
d = skel("empty")
check("异常[空稿] 不崩溃+empty_input 告警",
      d.get("total_chars") == 0 and ["empty_input"] in d.get("warnings", []), d.get("warnings"))
d = skel("non_academic")
check("异常[非学术体裁] 不崩溃+no_academic_structure 告警",
      ["no_academic_structure"] in d.get("warnings", [])
      and d.get("boundary_candidates") == [], d.get("warnings"))
d = skel("pos_zh")
trunc = open(os.path.join(FIX, "pos_zh.md"), encoding="utf-8").read().rstrip()[:-6]
tp = os.path.join(OUT, "trunc.md")
open(tp, "w", encoding="utf-8").write(trunc)
r = subprocess.run([sys.executable, SKELETON, tp, "-o", os.path.join(OUT, "trunc.json")],
                   capture_output=True, text=True, timeout=90)
check("异常[截断稿] 检测截断", r.returncode == 0 and
      json.load(open(os.path.join(OUT, "trunc.json"))).get("truncation_suspect") is True)

# 超长稿：约 4 万字符（确定性生成），断言限时内完成
words = ("scheduler latency cluster workload policy throughput node queue cache energy "
         "gradient robustness baseline ablation scaling fairness jitter").split()
lines = []
for sec in range(30):
    lines.append("# %d Topic %d" % (sec + 1, sec)); lines.append("")
    for p in range(8):
        sents = []
        for q in range(4):
            sents.append("Section %d paragraph %d sentence %d measures %s and %s under condition %d."
                         % (sec, p, q, words[(sec * 3 + p + q) % len(words)],
                            words[(sec + p * 2 + q) % len(words)], (sec + q) % 7))
        lines.append(" ".join(sents)); lines.append("")
tp = os.path.join(OUT, "long.md")
open(tp, "w", encoding="utf-8").write("\n".join(lines))
t0 = time.time()
r = subprocess.run([sys.executable, SKELETON, tp, "-o", os.path.join(OUT, "long.json")],
                   capture_output=True, text=True, timeout=90)
wall = time.time() - t0
check("异常[超长稿~40k字符] 限时完成", r.returncode == 0 and wall < 20, "wall=%.1fs rc=%d" % (wall, r.returncode))
check("异常[超长稿] 产出结构化结果",
      r.returncode == 0 and json.load(open(os.path.join(OUT, "long.json"))).get("n_sections") == 30)

# ---------- result_check 契约回归 ----------
def run_check(r):
    p = os.path.join(OUT, "rc_case.json")
    json.dump(r, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    res = subprocess.run([sys.executable, CHECK, p], capture_output=True, text=True)
    return res.returncode, res.stdout

dims = ["research_question", "section_structure", "argument_chain",
        "paragraph_relation", "redundancy", "conclusion_boundary"]
base_result = {"case_id": "selftest", "status": "success", "summary": "逐维核查无发现",
               "deliverables": [{"path": os.path.join(FIX, "pos_zh.md"), "kind": "骨架"}],
               "diagnosis": [], "edit_plan": [], "change_log": [], "sources": ["pos_zh.md"],
               "fact_source_map": [], "uncertainty": [], "human_confirmation": [],
               "material_gaps": [], "anomalies": [], "dimensions_checked": dims,
               "artifact_version": "paper-structure-logic-review-1.1.0",
               "input_manifest": {"algorithm": "sha256", "sha256": "0000000000000000000000000000000000000000000000000000000000000000", "bytes": 0},
               "logic_audit": {"rule_version": "logic-audit-1.0.0"},
               "dimension_plan": {d: {"status": "no_finding", "diagnosis_ids": [], "edit_ids": []} for d in dims},
               "budget": {"model_requests_used": 3, "seconds_used": 120, "note": "selftest"}}
rc, out = run_check(base_result)
check("契约[诊断无命中] 0 硬伤 0 告警", rc == 0 and "0 条提示" in out, out.strip()[:90])
mut = json.loads(json.dumps(base_result))
mut.pop("dimensions_checked")
rc, out = run_check(mut)
check("契约[空诊断未声明] 提示无法区分无命中/未核查", rc == 0 and "未核查" in out)
mut = json.loads(json.dumps(base_result))
mut["diagnosis"] = [{"dimension": "redundancy", "location": "S1.P1", "evidence": "同句重复",
                     "type": "rep", "severity": "mid", "action": "delete"}]
mut["status"] = "partial"; mut["material_gaps"] = ["缺参考文献"]
rc, out = run_check(mut)
check("契约[缺判据] 记 ADVICE 不阻断", rc == 0 and "criterion" in out)
bad = os.path.join(OUT, "bad.json")
open(bad, "w").write("{not json")
res = subprocess.run([sys.executable, CHECK, bad], capture_output=True, text=True)
check("契约[不可解析] FAIL exit 1", res.returncode == 1)
res = subprocess.run([sys.executable, CHECK, "--selftest"], capture_output=True, text=True)
check("契约[--selftest 双夹具] exit 0", res.returncode == 0, res.stdout.strip()[:80])

print("----")
if failures:
    print("FAILURES: %d" % len(failures))
    for f in failures:
        print(" - " + f)
    sys.exit(1)
print("ALL %d CHECKS PASS" % n_checks[0])
