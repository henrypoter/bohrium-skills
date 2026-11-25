#!/usr/bin/env python3
"""logic_audit 回归：3 正向零误杀 + 17 变异必命中；仅标准库。"""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "logic_audit.py")
CHECKS = []

GOOD = """# 引言
本文旨在评估方法 X 是否降低任务延迟。
# 方法
我们在 3 个公开数据集上采用统一训练流程，并对 30 个任务进行配对比较。
# 结果
在 3 个公开数据集和 30 个任务上，方法 X 的平均延迟降低 12%。
# 结论
在本研究的 3 个公开数据集和 30 个任务条件下，结果初步表明方法 X 可降低 12% 的延迟。
"""


def run(args):
    return subprocess.run([sys.executable, TOOL] + args,
                          capture_output=True, text=True, timeout=30)


def scan_tmp(tmp, name, text):
    path = os.path.join(tmp, name + ".md")
    apath = os.path.join(tmp, name + ".audit.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    proc = run(["scan", path, "-o", apath])
    audit = json.load(open(apath, encoding="utf-8")) if os.path.exists(apath) else {}
    return proc, apath, audit


def good_result(audit):
    rq = audit["research_question_candidates"][0]
    cb = audit["conclusion_boundary_candidates"][0]
    return {"case_id": "logic-fixture", "status": "success",
            "artifact_version": "paper-structure-logic-review-1.1.0",
            "input_manifest": audit["input_fingerprint"],
            "diagnosis": [], "anomalies": [], "material_gaps": [], "uncertainty": [],
            "logic_audit": {
                "rule_version": "logic-audit-1.0.0", "audit_report": "logic_audit.json",
                "research_questions": [{
                    "id": rq["id"], "status": "closed", "question_anchor": rq["question_anchor"],
                    "method_anchors": rq["method_anchors_suggested"][:1],
                    "result_anchors": rq["result_anchors_suggested"][:1],
                    "conclusion_anchors": rq["conclusion_anchors_suggested"][:1],
                    "rationale": "问题、统一比较方法、量化结果与限定结论逐环对应", "diagnosis_ids": []}],
                "conclusion_boundaries": [{
                    "id": cb["id"], "conclusion_anchor": cb["conclusion_anchor"],
                    "result_anchors": cb["result_anchors_suggested"][:1],
                    "scope_relation": "within", "rationale": "结论继承 3 数据集/30任务/12%并加本研究限定",
                    "diagnosis_ids": []}],
                "truncation": {"suspected": audit["truncation"]["suspected"],
                                "last_anchor": audit["truncation"]["last_anchor"],
                                "last_text_sha256": audit["truncation"]["last_text_sha256"],
                                "read_scope": "complete", "action": "全文末句完整，无截断限制"}}}


def record(name, ok, detail=""):
    CHECKS.append({"name": name, "pass": bool(ok), "detail": detail if not ok else ""})
    print(("PASS" if ok else "FAIL"), name, ("| " + str(detail)[:180] if not ok else ""))


with tempfile.TemporaryDirectory(prefix="logic_bench_") as tmp:
    proc, apath, audit = scan_tmp(tmp, "good", GOOD)
    record("正向 scan:研究问题/结论候选可定位", proc.returncode == 0 and
           [q["id"] for q in audit.get("research_question_candidates", [])] == ["RQ1"] and
           [c["id"] for c in audit.get("conclusion_boundary_candidates", [])] == ["CB1"])
    record("正向 scan:完整稿零截断/零数值越界误杀",
           audit.get("truncation", {}).get("suspected") is False and
           not audit["conclusion_boundary_candidates"][0]["unseen_numbers_vs_results"] and
           not audit["conclusion_boundary_candidates"][0]["signals"])
    result = good_result(audit)
    rp = os.path.join(tmp, "good.result.json")
    json.dump(result, open(rp, "w", encoding="utf-8"), ensure_ascii=False)
    ver = run(["verify", rp, apath])
    record("正向 verify:闭环且结论在数据范围内零误杀", ver.returncode == 0, ver.stdout)

    # 内容变异：scan 必检出候选信号。
    no_results = GOOD.replace("# 结果\n在 3 个公开数据集和 30 个任务上，方法 X 的平均延迟降低 12%。\n", "")
    _, _, bad_audit = scan_tmp(tmp, "no_results", no_results)
    record("变异 scan:研究问题缺结果环必提示",
           "results" in bad_audit["research_question_candidates"][0]["missing_section_links"])

    numeric = GOOD.replace("可降低 12% 的延迟", "可降低 25% 的延迟")
    _, _, bad_numeric = scan_tmp(tmp, "numeric", numeric)
    record("变异 scan:结论新增结果外数值必命中",
           "25%" in bad_numeric["conclusion_boundary_candidates"][0]["unseen_numbers_vs_results"])

    broad = GOOD.replace("在本研究的 3 个公开数据集和 30 个任务条件下，结果初步表明方法 X 可降低 12% 的延迟",
                         "结果证明方法 X 在所有任务上均可降低 12% 的延迟")
    _, _, bad_broad = scan_tmp(tmp, "broad", broad)
    record("变异 scan:无限定普遍化必提示",
           "unbounded_generalization_needs_scope_check" in bad_broad["conclusion_boundary_candidates"][0]["signals"])

    truncated = GOOD.rstrip()[:-1]
    _, _, bad_trunc = scan_tmp(tmp, "truncated", truncated)
    record("变异 scan:末句截断必命中",
           bad_trunc["truncation"]["suspected"] and
           "unterminated_final_text" in bad_trunc["truncation"]["signals"])

    def verify_mut(name, mutate, code, base_result=None, base_audit=None, audit_path=None):
        res = copy.deepcopy(base_result if base_result is not None else result)
        mutate(res)
        path = os.path.join(tmp, "verify_case_%02d.json" % len(CHECKS))
        json.dump(res, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        proc = run(["verify", path, audit_path or apath])
        record("变异 verify:" + name, proc.returncode == 1 and code in proc.stdout, proc.stdout)

    verify_mut("输入摘要不匹配 P1", lambda r: r["input_manifest"].update({"sha256": "0" * 64}), "P1")
    verify_mut("漏审研究问题 Q1", lambda r: r["logic_audit"].update({"research_questions": []}), "Q1")
    verify_mut("closed 缺方法锚点 Q3", lambda r: r["logic_audit"]["research_questions"][0].update({"method_anchors": []}), "Q3")
    verify_mut("open 无诊断 Q4", lambda r: r["logic_audit"]["research_questions"][0].update({"status": "open", "diagnosis_ids": []}), "Q4")
    verify_mut("结论锚点被替换 B2", lambda r: r["logic_audit"]["conclusion_boundaries"][0].update({"conclusion_anchor": "S1.P1.s1"}), "B2")
    verify_mut("结果锚点不在结果节 B3", lambda r: r["logic_audit"]["conclusion_boundaries"][0].update({"result_anchors": ["S2.P1.s1"]}), "B3")
    verify_mut("broader 无诊断 B5", lambda r: r["logic_audit"]["conclusion_boundaries"][0].update({"scope_relation": "broader", "diagnosis_ids": []}), "B5")
    verify_mut("规则版本错 P2", lambda r: r["logic_audit"].update({"rule_version": "old"}), "P2")
    verify_mut("截断处置为空 T2", lambda r: r["logic_audit"]["truncation"].update({"action": ""}), "T2")

    # 对含结果外 25% 的 scan，若仍写 within，B4 必须拒绝。
    numeric_path = os.path.join(tmp, "numeric.audit.json")
    numeric_result = good_result(bad_numeric)
    verify_mut("新增数值仍判 within B4",
               lambda r: r["logic_audit"]["conclusion_boundaries"][0].update({"scope_relation": "within"}),
               "B4", numeric_result, bad_numeric, numeric_path)

    # 完整扫描被“改写为无截断”必中 T1。
    trunc_result = good_result(bad_trunc)
    trunc_result["logic_audit"]["truncation"] = copy.deepcopy(result["logic_audit"]["truncation"])
    verify_mut("截断状态被静默改写 T1", lambda r: None, "T1", trunc_result, bad_trunc,
               os.path.join(tmp, "truncated.audit.json"))

    # 状态与末文本正确，但截断仍声称 success 且无材料缺口，必中 T2。
    trunc_result2 = good_result(bad_trunc)
    trunc_result2["logic_audit"]["truncation"].update({
        "suspected": True, "last_anchor": bad_trunc["truncation"]["last_anchor"],
        "last_text_sha256": bad_trunc["truncation"]["last_text_sha256"],
        "read_scope": "complete", "action": "忽略末句"})
    verify_mut("截断未 partial/缺异常 T2", lambda r: None, "T2", trunc_result2, bad_trunc,
               os.path.join(tmp, "truncated.audit.json"))

    verify_mut("漏审结论边界 B1", lambda r: r["logic_audit"].update({"conclusion_boundaries": []}), "B1")

passed = sum(1 for c in CHECKS if c["pass"])
report = {"summary": {"total": len(CHECKS), "passed": passed, "failed": len(CHECKS) - passed},
          "checks": CHECKS, "rule_version": "logic-audit-1.0.0",
          "boundary": "自拟短稿；scan 信号为候选，verify 只核验闭环/范围裁决与留痕，不替代语义专家判断"}
out = os.path.join(HERE, "logic_bench_results.json")
json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("total %d/%d; report=%s" % (passed, len(CHECKS), out))
sys.exit(0 if passed == len(CHECKS) else 1)
