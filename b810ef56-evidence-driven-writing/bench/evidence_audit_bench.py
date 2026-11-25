#!/usr/bin/env python3
"""evidence_audit 自测：17 项强度/异常 + 2 项输入摘要（仅标准库）。"""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "evidence_audit.py")
CHECKS = []


def evidence(eid="E1", level="B"):
    return {"id": eid, "authors": "Example", "year": "2024", "title": "自拟文献",
            "venue": "示例刊", "doi": None, "type": "原始研究",
            "availability": "full_text", "locator": "结果第2段",
            "quote": "在本实验条件下观察到方法 X 的初步效果",
            "supports": "仅支持本条件下的观察", "data": "n=30",
            "conditions": "本实验条件", "limitations": "单中心",
            "evidence_level": level,
            "evidence_level_reason": "单篇设计明确但仅单中心的原始研究，定 B" if level == "B" else "小样本且未独立重复，定 C",
            "strength_basis": {"design": "单中心对照实验", "sample_size": "n=30",
                               "replication": "未见独立重复", "consensus": "未知",
                               "basis_unknown": []}, "caveat": None}


def claim(level="B"):
    return {"id": "C1", "text": "方法 X 在本实验条件下显示初步效果",
            "verdict": "supported", "strength_annotation": {
                "level": level, "rationale": "等级与直接全文证据一致",
                "uncertainty": "外部人群仍需重复验证"},
            "bindings": [{"evidence_id": "E1", "scope": "full",
                          "position": "support", "note": "直接支持限定条件下的观察"}]}


def run_case(name, lib, mat, manuscript, expect, code=None):
    with tempfile.TemporaryDirectory(prefix="evidence_audit_") as tmp:
        lp, mp, sp, rp = [os.path.join(tmp, n) for n in
                          ("lib.json", "matrix.json", "manuscript.md", "report.json")]
        for p, obj in ((lp, lib), (mp, mat)):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False)
        with open(sp, "w", encoding="utf-8") as f:
            f.write(manuscript)
        proc = subprocess.run([sys.executable, TOOL, "audit", lp, mp, sp, "-o", rp],
                              capture_output=True, text=True, timeout=30)
        report = json.load(open(rp, encoding="utf-8")) if os.path.exists(rp) else {}
    hit = code is None or any(code in e for e in report.get("errors", []))
    ok = proc.returncode == expect and hit
    CHECKS.append(ok)
    print(("PASS" if ok else "FAIL"), name,
          "" if ok else "| rc=%s errors=%s" % (proc.returncode, report.get("errors")))


base_lib = {"evidence": [evidence(), evidence("E2", "C")]}
base_mat = {"claims": [claim()]}
base_ms = "方法 X 在本实验条件下显示初步效果[C1:E1]。"
run_case("正向:全文 B 级+强度理由零误杀", base_lib, base_mat, base_ms, 0)

abstract_lib = copy.deepcopy(base_lib)
abstract_lib["evidence"] = abstract_lib["evidence"][:1]
for ev in abstract_lib["evidence"]:
    ev.update({"availability": "abstract_only", "evidence_level": "C",
               "evidence_level_reason": "仅摘要且小样本，封顶 C",
               "locator": "摘要第2句", "caveat": "仅摘要可得，方法与全文局限未核验"})
abstract_mat = {"claims": [claim("C")]}
run_case("正向:仅摘要封顶 C 且显式标缺口零误杀", abstract_lib, abstract_mat, base_ms, 0)

conflict_lib = copy.deepcopy(base_lib)
conflict_mat = copy.deepcopy(base_mat)
c = conflict_mat["claims"][0]
c.update({"text": "方法 X 的效果证据尚不一致", "verdict": "conflicted",
          "strength_annotation": {"level": "C", "rationale": "正负证据且样本有限",
                                   "uncertainty": "差异来源未解决"},
          "conflict_analysis": {"summary": "一项正向、一项未重复出效果",
                                 "differences": "样本与噪声条件不同",
                                 "uncertainty": "不能排除人群差异", "action": "核对全文并等待独立重复"},
          "bindings": [
              {"evidence_id": "E1", "scope": "partial", "position": "support", "note": "正向初步结果"},
              {"evidence_id": "E2", "scope": "partial", "position": "oppose", "note": "相反/阴性结果"}]})
conflict_ms = "两项结果不一致：一项观察到效果，另一项为阴性[C1]。"
run_case("正向:冲突双向+原因+正文并陈零误杀", conflict_lib, conflict_mat, conflict_ms, 0)

# 以下均是单点变异；若多条出错也至少必须命中目标规则码。
lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
del lib["evidence"][0]["availability"]
run_case("变异 S1:缺可得性", lib, mat, base_ms, 1, "S1")

lib, mat = copy.deepcopy(abstract_lib), copy.deepcopy(abstract_mat)
lib["evidence"][0]["evidence_level"] = "B"
run_case("变异 S2:仅摘要标 B", lib, mat, base_ms, 1, "S2")

lib, mat = copy.deepcopy(abstract_lib), copy.deepcopy(abstract_mat)
lib["evidence"][0]["locator"] = "结果第2段"
run_case("变异 S3:摘要定位伪装全文", lib, mat, base_ms, 1, "S3")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
lib["evidence"][0]["evidence_level_reason"] = ""
run_case("变异 S4:强度无理由", lib, mat, base_ms, 1, "S4")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
lib["evidence"][0]["strength_basis"]["sample_size"] = None
run_case("变异 S5:未知样本未显式登记", lib, mat, base_ms, 1, "S5")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
lib["evidence"][0]["evidence_level"] = "A"
lib["evidence"][0]["strength_basis"]["replication"] = "无独立重复"
mat["claims"][0]["strength_annotation"]["level"] = "A"
run_case("变异 S8:单篇原始研究无重复却标 A", lib, mat, base_ms, 1, "S8")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
del mat["claims"][0]["strength_annotation"]
run_case("变异 S6:论断缺强度标注", lib, mat, base_ms, 1, "S6")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
mat["claims"][0]["strength_annotation"]["level"] = "A"
run_case("变异 S7:论断强于绑定证据", lib, mat, base_ms, 1, "S7")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
del mat["claims"][0]["bindings"][0]["position"]
run_case("变异 C1:证据方向缺失", lib, mat, base_ms, 1, "C1")

lib, mat = copy.deepcopy(conflict_lib), copy.deepcopy(conflict_mat)
mat["claims"][0]["bindings"][1]["position"] = "support"
run_case("变异 C2:伪冲突无反向证据", lib, mat, base_ms, 1, "C2")

lib, mat = copy.deepcopy(conflict_lib), copy.deepcopy(conflict_mat)
mat["claims"][0]["conflict_analysis"]["differences"] = ""
run_case("变异 C3:冲突无差异分析", lib, mat, base_ms, 1, "C3")

lib, mat = copy.deepcopy(conflict_lib), copy.deepcopy(conflict_mat)
mat["claims"][0]["strength_annotation"]["level"] = "B"
run_case("变异 S7:未解冲突仍标 B", lib, mat, base_ms, 1, "S7")

run_case("变异 C5:正文隐藏冲突", conflict_lib, conflict_mat, "方法 X 的效果仍待研究[C1]。", 1, "C5")

lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
mat["claims"][0]["bindings"].append({"evidence_id": "E2", "scope": "partial",
                                      "position": "oppose", "note": "相反结果"})
run_case("变异 C4:有反向证据却判 supported", lib, mat, base_ms, 1, "C4")

# fingerprint 也有正向与输入变异回归，防止版本字段可用错误摘要填充。
with tempfile.TemporaryDirectory(prefix="evidence_fingerprint_") as tmp:
    fp = os.path.join(tmp, "material.txt")
    with open(fp, "wb") as f:
        f.write(b"abc")
    proc = subprocess.run([sys.executable, TOOL, "fingerprint", fp], capture_output=True, text=True)
    first = json.loads(proc.stdout)
    ok = (proc.returncode == 0 and first["files"][0]["sha256"] == hashlib.sha256(b"abc").hexdigest()
          and first["files"][0]["bytes"] == 3)
    CHECKS.append(ok)
    print(("PASS" if ok else "FAIL"), "正向 fingerprint:真实 SHA-256/bytes")
    with open(fp, "wb") as f:
        f.write(b"abcd")
    proc = subprocess.run([sys.executable, TOOL, "fingerprint", fp], capture_output=True, text=True)
    second = json.loads(proc.stdout)
    ok = proc.returncode == 0 and second["files"][0]["sha256"] != first["files"][0]["sha256"]
    CHECKS.append(ok)
    print(("PASS" if ok else "FAIL"), "变异 fingerprint:内容变化必改变摘要")

passed = sum(CHECKS)
report = {"summary": {"total": len(CHECKS), "passed": passed, "failed": len(CHECKS) - passed},
          "audit_groups": {"positive": 3, "mutants": 14, "fingerprint_assertions": 2},
          "checks_pass": CHECKS, "rule_version": "evidence-audit-1.0.0",
          "boundary": "自拟数据；只验证规则一致性，不自动判定研究设计或科学冲突"}
report_path = os.path.join(HERE, "evidence_audit_bench_results.json")
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print("total %d/%d; report=%s" % (passed, len(CHECKS), report_path))
sys.exit(0 if passed == len(CHECKS) else 1)
