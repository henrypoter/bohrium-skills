#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""transfer_check 三命令回归：正向零误杀 + 独立变异必命中。
用法：python3 bench/bench_run.py [--write]。全部夹具运行时生成，非正式案例。
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TOOL = ROOT / "scripts" / "transfer_check.py"
TMP = Path(tempfile.mkdtemp(prefix="transfer-bench-"))
CHECKS = []


def dump(name, obj):
    p = TMP / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    return str(p)


def run(*args):
    p = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)
    try:
        data = json.loads(p.stdout)
    except Exception:
        data = {"raw": p.stdout[-300:], "stderr": p.stderr[-300:]}
    return p.returncode, data


def add(name, condition, detail=""):
    CHECKS.append({"name": name, "pass": bool(condition), "detail": detail})


def kinds(data, kind):
    return [x for x in data.get("items", []) if x.get("kind") == kind]


SOURCE = """示例材料（自拟，非正式案例）

在 120 名参与者中，准确率为 88.1%（95% CI 82.0–92.0），较对照组高 7.1 个百分点；该结果为单中心初步观察，不能推断因果。
研究采用五折交叉验证，并使用受试者工作特征曲线（receiver operating characteristic，ROC）衡量区分能力。
"""
P1 = "在 120 名参与者中，该模型初步达到 88.1% 的准确率（95% CI（confidence interval，估计值的不确定范围）82.0–92.0），较对照组高 7.1 个百分点（图1）；这是单中心观察，不能推断因果。[S1]"
P2 = "研究采用五折交叉验证。受试者工作特征曲线（receiver operating characteristic，ROC）衡量区分能力，可理解为“衡量模型区分能力的曲线”，结果仍需外部验证。[S2]"
DRAFT = "# 核心发现\n\n%s\n\n# 方法与边界\n\n%s\n" % (P1, P2)
PROJECT = {
    "case_id": "fixture-001",
    "items": [
        {"id": "S1", "kind": "number", "fact_key": "accuracy", "source": "source.md", "line": 3,
         "quote": "在 120 名参与者中，准确率为 88.1%（95% CI 82.0–92.0），较对照组高 7.1 个百分点；该结果为单中心初步观察，不能推断因果。",
         "surfaces": ["120", "88.1%", "95% CI 82.0–92.0", "7.1 个百分点"], "required": True,
         "strength": "preliminary", "figure": "图1"},
        {"id": "S2", "kind": "method", "fact_key": "validation", "source": "source.md", "line": 4,
         "quote": "研究采用五折交叉验证，并使用受试者工作特征曲线（receiver operating characteristic，ROC）衡量区分能力。",
         "surfaces": [], "required": True, "strength": "observed"}
    ],
    "terms": [
        {"canonical": "置信区间", "abbreviation": "CI", "expanded": "confidence interval",
         "plain": "估计值的不确定范围", "aliases": ["可信区间"]},
        {"canonical": "受试者工作特征曲线", "abbreviation": "ROC", "expanded": "receiver operating characteristic",
         "plain": "衡量模型区分能力的曲线", "aliases": ["ROC曲线"]}
    ],
    "changes": [
        {"segment_id": "p1", "action": "revise", "before_quote": "在 120 名参与者中，准确率为 88.1%",
         "draft_segment": P1, "reason": "面向公众保留样本、指标、区间、比较基准并降调", "evidence_ids": ["S1"]},
        {"segment_id": "p2", "action": "revise", "before_quote": "研究采用五折交叉验证",
         "draft_segment": P2, "reason": "展开缩写并补白话解释", "evidence_ids": ["S2"]}
    ]
}
BRIEF = {"audience": "public", "genre": "科普文章", "required_sections": ["核心发现", "方法与边界"],
         "min_chars": 20, "max_chars": 1000, "target_channel": "internal", "confidential": False,
         "unpublished": False, "allowed_abbreviations": []}


def fixtures():
    (TMP / "source.md").write_text(SOURCE, encoding="utf-8")
    (TMP / "draft.md").write_text(DRAFT, encoding="utf-8")
    project = dump("project.json", PROJECT)
    brief = dump("brief.json", BRIEF)
    case = dump("case.json", {"case_id": "fixture-001", "output_contract": {"bilingual_title": "string"}})
    fingerprint = hashlib.sha256((SOURCE + DRAFT).encode("utf-8")).hexdigest()
    result = {
        "case_id": "fixture-001", "status": "complete", "bilingual_title": "示例 / Example",
        "main_output": str(TMP / "draft.md"), "artifacts": [{"path": str(TMP / "draft.md"), "kind": "md"}],
        "sources": PROJECT["items"], "uncertainty": ["单中心初步结果"], "changes": PROJECT["changes"],
        "validation": {"fail": 0, "evidence_fail": 0},
        "gain": {"comparison_status": "local_fixture",
                 "protocol": {"same_input": True, "same_constraints": True, "same_permissions": True, "same_budget": True},
                 "baseline": {"input_sha256": fingerprint, "metrics": {"fact_errors": 3, "manual_edit_items": 8, "rework_rounds": 2}},
                 "skill": {"input_sha256": fingerprint, "metrics": {"fact_errors": 0, "manual_edit_items": 1, "rework_rounds": 1}},
                 "evidence": ["bench/bench_results.json"]}
    }
    return project, brief, case, dump("result.json", result), fingerprint


def main():
    started = time.time()
    project, brief, case, result, fingerprint = fixtures()
    # evidence：正向与逐字、定位、冲突三类独立变异。
    rc, good = run("evidence", project)
    add("evidence 正向：原文逐字+行号+schema 零误杀", rc == 0 and good.get("summary", {}).get("warn") == 0)
    p = copy.deepcopy(PROJECT); p["items"][0]["quote"] = p["items"][0]["quote"].replace("88.1", "88.2")
    rc, d = run("evidence", dump("m_quote.json", p))
    add("evidence 变异：引文改字必命中 verbatim", rc == 1 and kinds(d, "verbatim"))
    p = copy.deepcopy(PROJECT); p["items"][0]["line"] = 4
    rc, d = run("evidence", dump("m_line.json", p))
    add("evidence 变异：错误行号必命中 locator", rc == 1 and kinds(d, "locator"))
    p = copy.deepcopy(PROJECT)
    other = copy.deepcopy(p["items"][0]); other["id"] = "S3"; other["conflict_group"] = "acc"
    other["quote"] = other["quote"].replace("88.1", "79.0"); other["surfaces"] = ["120", "79.0%", "95% CI 82.0–92.0", "7.1 个百分点"]
    p["items"][0]["conflict_group"] = "acc"; p["items"].append(other)
    rc, d = run("evidence", dump("m_conflict.json", p))
    add("evidence 变异：未裁决数据冲突必命中 conflict", rc == 1 and kinds(d, "conflict"))

    def audit_mut(name, mutate, kind, project_too=False, brief_too=False):
        dr, pr, br = DRAFT, copy.deepcopy(PROJECT), copy.deepcopy(BRIEF)
        if project_too:
            mutate(pr)
        elif brief_too:
            mutate(br)
        else:
            dr = mutate(dr)
        dp = TMP / (name + ".md"); dp.write_text(dr, encoding="utf-8")
        pp = dump(name + ".json", pr) if project_too else project
        bp = dump(name + "_brief.json", br) if brief_too else brief
        rc, d = run("audit", dp, pp, bp)
        add(name, rc == 1 and kinds(d, kind), str(kinds(d, kind))[:180])

    rc, good_audit = run("audit", TMP / "draft.md", project, brief)
    add("audit 正向：保留/数字/术语/边界/改动全覆盖", rc == 0 and good_audit.get("summary", {}).get("warn") == 0)
    audit_mut("audit 变异：数字漂移必命中 number", lambda s: s.replace("88.1%", "88.2%"), "number")
    audit_mut("audit 变异：删必需证据必命中 retention", lambda s: s.replace("[S2]", ""), "retention")
    audit_mut("audit 变异：初步观察写成因果定论必命中", lambda s: s.replace("初步达到", "证明可导致").replace("不能推断因果", "具有因果效应"), "claim_strength")
    audit_mut("audit 变异：术语别名必命中 terminology", lambda s: s.replace("受试者工作特征曲线（", "ROC曲线；受试者工作特征曲线（"), "terminology")
    audit_mut("audit 变异：缩写未展开必命中 abbreviation", lambda s: s.replace("receiver operating characteristic，", ""), "abbreviation")
    audit_mut("audit 变异：体裁缺节必命中 genre", lambda s: s.replace("# 方法与边界", "# 其他"), "genre")
    audit_mut("audit 变异：无逐段记录必命中 change_coverage", lambda s: s + "\n新增一段没有记录的事实。\n", "change_coverage")
    audit_mut("audit 变异：改动前引文回不到原文", lambda s: s, "change_anchor", project_too=True) if False else None
    p = copy.deepcopy(PROJECT); p["changes"][0]["before_quote"] = "材料不存在的原句"
    rc, d = run("audit", TMP / "draft.md", dump("m_change.json", p), brief)
    add("audit 变异：before_quote 不回原文必命中", rc == 1 and kinds(d, "change_anchor"))
    b = copy.deepcopy(BRIEF); b.update({"confidential": True, "target_channel": "public"})
    rc, d = run("audit", TMP / "draft.md", project, dump("m_secret.json", b))
    add("audit 变异：涉密公开发布缺审批必命中 disclosure", rc == 1 and kinds(d, "disclosure"))
    b = copy.deepcopy(BRIEF); b["max_chars"] = 20
    rc, d = run("audit", TMP / "draft.md", project, dump("m_length.json", b))
    add("audit 变异：超篇幅必命中 length", rc == 1 and kinds(d, "length"))

    # result：output_contract、产物与 A/B 同输入约束。
    rc, good_result = run("result", result, case)
    add("result 正向：契约/文件/gain 零误杀", rc == 0 and good_result.get("summary", {}).get("warn") == 0)
    r = copy.deepcopy(json.loads(Path(result).read_text(encoding="utf-8"))); r.pop("bilingual_title")
    rc, d = run("result", dump("m_result_contract.json", r), case)
    add("result 变异：output_contract 缺字段必命中", rc == 1 and kinds(d, "contract"))
    r = copy.deepcopy(json.loads(Path(result).read_text(encoding="utf-8"))); r["gain"]["baseline"]["input_sha256"] = "different"
    rc, d = run("result", dump("m_result_gain.json", r), case)
    add("result 变异：A/B 输入不同必命中 gain", rc == 1 and kinds(d, "gain"))
    r = copy.deepcopy(json.loads(Path(result).read_text(encoding="utf-8"))); r["status"] = "complete"; r["validation"]["fail"] = 1
    rc, d = run("result", dump("m_result_closure.json", r), case)
    add("result 变异：带 fail 冒充 complete 必命中 closure", rc == 1 and kinds(d, "closure"))

    # 长稿稳定性：重复已覆盖段落，放大篇幅上限，判定保持零误杀。
    big = DRAFT + ("\n" + P1 + "\n") * 200
    (TMP / "big.md").write_text(big, encoding="utf-8")
    b = copy.deepcopy(BRIEF); b["max_chars"] = 1000000
    t0 = time.time(); rc, d = run("audit", TMP / "big.md", project, dump("big_brief.json", b)); dt = time.time() - t0
    add("长稿 200 段：判定稳定且 <10s", rc == 0 and dt < 10, "%.3fs" % dt)

    passed = sum(x["pass"] for x in CHECKS)
    out = {"all_pass": passed == len(CHECKS), "passed": passed, "total": len(CHECKS),
           "checks": CHECKS, "seconds": round(time.time() - started, 3),
           "deterministic_gain_fixture": {
               "scope": "仅自拟夹具，不是平台基础 Agent 成绩",
               "same_input_sha256": fingerprint,
               "baseline": {"fact_errors": 3, "manual_edit_items": 8, "rework_rounds": 2},
               "skill": {"fact_errors": 0, "manual_edit_items": 1, "rework_rounds": 1}}}
    blob = json.dumps(out, ensure_ascii=False, indent=1)
    if "--write" in sys.argv:
        (HERE / "bench_results.json").write_text(blob + "\n", encoding="utf-8")
    print(blob)
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
