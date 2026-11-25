#!/usr/bin/env python3
"""review_tool v3 自测；每个命令均有正向零误杀与破坏性变异必命中。"""
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "review_tool.py")
TMP = tempfile.mkdtemp(prefix="methods-review-bench-")
checks = []


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:300], "stderr": proc.stderr[:300]}


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def textfile(name, content, binary=False):
    path = os.path.join(TMP, name)
    with open(path, "wb" if binary else "w", encoding=None if binary else "utf-8") as f:
        f.write(content)
    return path


def qh(s):
    canonical = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).strip()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


TEXT = "方法\n\n随机对照试验共纳入 45 例。\n\n结果\n\n双因素方差分析显示 z=1.96，p=0.05。"
QUOTE = "双因素方差分析显示 z=1.96，p=0.05。"
ISSUE = {"id": "P1", "category": "statistics", "facet": "reporting", "severity": "major",
         "defect_type": "evidence_gap", "review_status": "confirmed",
         "location": {"section": "结果", "page": 1, "paragraph": 4, "quote_sha256": qh(QUOTE)},
         "quote": QUOTE, "claim": "缺少效应量与置信区间", "fix": "补报效应量及 95% CI",
         "evidence": [{"source_id": "M", "quote": QUOTE, "basis": "结果段仅报告 z 与 p，未见效应量或 CI",
                       "locator": {"section": "结果", "page": 1, "paragraph": 4, "quote_sha256": qh(QUOTE)}}]}
LEGACY = [{"id": "P1", "category": "statistics", "severity": "major", "location": "结果 第2段",
           "quote": QUOTE, "claim": "统计报告缺效应量与置信区间", "fix": "补充效应量与 95% CI"}]
txt = textfile("manuscript.txt", TEXT)

# verify：原句、重复项和哈希
rc, d = run("verify", dump("verify-good.json", {"issues": LEGACY}), "--text", txt)
add("verify 正向:合规原句零误杀", rc == 0 and d.get("ok"), str(d))
bad_quote = dict(LEGACY[0], quote="不存在的统计句")
rc, d = run("verify", dump("verify-bad.json", {"issues": [bad_quote]}), "--text", txt)
add("verify 变异:伪造原句必命中", rc == 1 and len(d.get("quote_not_in_source", [])) == 1, str(d))
rc, d = run("verify", dump("verify-dup.json", {"issues": LEGACY + [dict(LEGACY[0], id="P2")]}))
add("verify 变异:重复问题必命中", len(d.get("duplicates", [])) == 1, str(d))
rc, d = run("verify", dump("verify-hash.json", {"issues": [dict(LEGACY[0], quote_sha256="0" * 64)]}), "--text", txt)
add("verify 变异:错误引文哈希必命中", rc == 1 and any("quote_sha256" in e for e in d.get("errors", [])), str(d))

# preflight：完整、合法混排和可降级警告均不能误杀
manifest = dump("manifest-good.json", {"expected_pages": [1], "unresolved_figures": [], "missing_statistical_outputs": []})
rc, d = run("preflight", "--text", txt, "--manifest", manifest)
add("preflight 正向:完整输入零误杀", rc == 0 and d.get("status") == "ready" and len(d.get("text_sha256", "")) == 64, str(d))
mixed = textfile("mixed.txt", ("方法：采用随机对照试验。" * 4) + "\n" + ("Methods: randomized controlled trial with allocation concealment. " * 5))
rc, d = run("preflight", "--text", mixed)
add("preflight 正向:合法中英混排不误杀", rc == 0 and d.get("language_profile", {}).get("class") == "mixed" and "mixed_language" in d.get("warnings", []), str(d))
fig_manifest = dump("manifest-fig.json", {"unresolved_figures": ["Figure 2"]})
rc, d = run("preflight", "--text", txt, "--manifest", fig_manifest)
add("preflight 正向:图表失败降级而非全文误杀", rc == 0 and d.get("status") == "partial" and "unresolved_figures" in d.get("warnings", []), str(d))
stat_manifest = dump("manifest-stat.json", {"missing_statistical_outputs": ["Table 3"]})
rc, d = run("preflight", "--text", txt, "--manifest", stat_manifest)
add("preflight 正向:统计输出缺失保留部分审查", rc == 0 and "missing_statistical_outputs" in d.get("warnings", []), str(d))
missing_manifest = dump("manifest-missing.json", {"expected_pages": [1, 2]})
rc, d = run("preflight", "--text", txt, "--manifest", missing_manifest)
add("preflight 变异:缺页必命中", rc == 1 and d.get("missing_pages") == [2], str(d))
empty = textfile("empty.txt", " \n")
rc, d = run("preflight", "--text", empty)
add("preflight 变异:扫描抽取空文本必命中", rc == 1 and "empty_text" in d.get("blockers", []), str(d))
garble = textfile("garble.txt", b"\xff" * 80, binary=True)
rc, d = run("preflight", "--text", garble)
add("preflight 变异:严重解码失败必命中", rc == 1 and "excessive_decode_errors" in d.get("blockers", []), str(d))

# coverage：没有问题不等于没有审查
facets = {name: {"status": "checked", "notes": "已阅读相关章节并记录判定", "reason": ""} for name in
          ["design", "variables", "statistics", "sample_size", "reporting"]}
categories = {name: {"status": "checked", "notes": "已检查，无论是否发现问题", "reason": ""} for name in
              ["fact", "citation", "design", "statistics", "argument", "compliance"]}
BASE = {"schema_version": "3.0", "case_id": "bench-synthetic", "status": "issues",
        "manuscript_version": {"label": "synthetic-v1", "sha256": "a" * 64, "files": ["manuscript.txt"]},
        "run": {"tool_version": "3.0.0", "run_id": "bench-run-001"},
        "contract": {"source": "/input/case.json#/output_contract", "preserved_fields": ["case_id", "status", "issues"]},
        "issues": [ISSUE], "facets": facets, "categories": categories,
        "sources": [{"source_id": "M", "path": "manuscript.txt", "sha256": "b" * 64}],
        "checked_scope": {"did": ["全文五面"], "not_checked": []}, "gain": {},
        "unchecked": [], "uncertainty": [], "change_log": ["合成 bench，仅验证规则"]}
rc, d = run("coverage", dump("coverage-good.json", BASE))
add("coverage 正向:五面六类完成零误杀", rc == 0 and d.get("ok"), str(d))
no_issue = copy.deepcopy(BASE); no_issue["issues"] = []; no_issue["status"] = "pass"
rc, d = run("coverage", dump("coverage-no-issue.json", no_issue))
add("coverage 正向:零问题但有审查记录不误杀", rc == 0 and d.get("ok"), str(d))
bad = copy.deepcopy(BASE); del bad["facets"]["variables"]
rc, d = run("coverage", dump("coverage-missing.json", bad))
add("coverage 变异:变量定义漏查必命中", rc == 1 and any("variables" in e for e in d.get("errors", [])), str(d))
partial = copy.deepcopy(BASE); partial["facets"]["statistics"] = {"status": "pending", "reason": "统计输出缺失"}
rc, d = run("coverage", dump("coverage-pending.json", partial))
add("coverage 变异:未完成统计面默认必拦截", rc == 1 and d.get("incomplete"), str(d))
rc, d = run("coverage", dump("coverage-pending.json", partial), "--allow-partial")
add("coverage 正向:显式 partial 可诚实降级", rc == 0 and d.get("incomplete") == ["facets.statistics"], str(d))
bad = copy.deepcopy(BASE); bad["categories"]["fact"] = {"status": "unchecked"}
rc, d = run("coverage", dump("coverage-reason.json", bad))
add("coverage 变异:未查无原因必命中", rc == 1 and any("reason" in e for e in d.get("errors", [])), str(d))

# statcheck：适配线性/比值区间以及精确 z-p
GOOD_STATS = [
    {"id": "S1", "p": 0.01, "ci_low": 0.2, "ci_high": 1.8, "scale": "linear"},
    {"id": "S2", "p": 0.20, "ci_low": -0.5, "ci_high": 1.0, "scale": "linear"},
    {"id": "S3", "p": 0.02, "ci_low": 1.1, "ci_high": 3.0, "scale": "ratio"},
    {"id": "S4", "p": 0.20, "ci_low": 0.5, "ci_high": 1.5, "scale": "ratio"},
    {"id": "S5", "p": 0.0455002639, "z": 2.0, "df": 20},
    {"id": "S6", "n_enrolled": 50, "n_excluded": 5, "n_analyzed": 45}
]
rc, d = run("statcheck", dump("stats-good.json", {"statistics": GOOD_STATS}))
add("statcheck 正向:六组合法记录零误杀", rc == 0 and d.get("total") == 6, str(d))
bad_stats = copy.deepcopy(GOOD_STATS); bad_stats[0]["p"] = 0.20
rc, d = run("statcheck", dump("stats-ci-bad.json", {"statistics": bad_stats}))
add("statcheck 变异:p-CI方向冲突必命中", rc == 1 and any("p 与 CI" in e for e in d["results"][0]["errors"]), str(d))
bad_stats = copy.deepcopy(GOOD_STATS); bad_stats[4]["p"] = 0.20
rc, d = run("statcheck", dump("stats-z-bad.json", {"statistics": bad_stats}))
add("statcheck 变异:z-p不一致必命中", rc == 1 and any("z-p" in e for e in d["results"][4]["errors"]), str(d))
bad_stats = copy.deepcopy(GOOD_STATS); bad_stats[5]["n_analyzed"] = 40
rc, d = run("statcheck", dump("stats-n-bad.json", {"statistics": bad_stats}))
add("statcheck 变异:样本流不守恒必命中", rc == 1 and any("样本流" in e for e in d["results"][5]["errors"]), str(d))
incomplete_n = [{"id": "N", "n_enrolled": 50, "n_excluded": 5, "n_analyzed": 40, "accounting_incomplete": True}]
rc, d = run("statcheck", dump("stats-n-partial.json", {"statistics": incomplete_n}))
add("statcheck 正向:明示其他剔除不强行误杀", rc == 0 and d.get("ok"), str(d))
bad_stats = [{"id": "D", "df": 0}]
rc, d = run("statcheck", dump("stats-df-bad.json", {"statistics": bad_stats}))
add("statcheck 变异:非法自由度必命中", rc == 1 and any("df" in e for e in d["results"][0]["errors"]), str(d))

# gate：版本、原契约、细粒度证据、严重度和状态均为硬约束
rc, d = run("gate", dump("gate-good.json", BASE))
add("gate 正向:完整可复核结果零误杀", rc == 0 and d.get("ok"), str(d))
rc, d = run("schema", dump("schema-good.json", BASE))
add("schema 正向:基础契约向后兼容", rc == 0 and d.get("ok"), str(d))
for label, mutate, token in [
    ("缺稿件内容哈希", lambda x: x["manuscript_version"].pop("sha256"), "sha256"),
    ("缺运行标识", lambda x: x["run"].pop("run_id"), "run"),
    ("未保留原输出契约记录", lambda x: x.pop("contract"), "contract"),
    ("缺粒度定位", lambda x: (x["issues"][0]["location"].pop("paragraph"), x["issues"][0]["location"].pop("page")), "细粒度定位"),
    ("引文哈希被篡改", lambda x: x["issues"][0]["location"].update(quote_sha256="0" * 64), "不匹配"),
    ("缺判断依据", lambda x: x["issues"][0].update(evidence=[]), "evidence"),
]:
    bad = copy.deepcopy(BASE); mutate(bad)
    rc, d = run("gate", dump("gate-" + str(len(checks)) + ".json", bad))
    add("gate 变异:" + label + "必命中", rc == 1 and any(token in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["issues"][0]["defect_type"] = "suggestion"
rc, d = run("gate", dump("gate-severity-bad.json", bad))
add("gate 变异:建议冒充major必命中", rc == 1 and any("suggestion" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["status"] = "pass"
rc, d = run("gate", dump("gate-state-bad.json", bad))
add("gate 变异:pass却携带问题必命中", rc == 1 and any("pass" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["issues"][0]["review_status"] = "pending"
rc, d = run("gate", dump("gate-pending-bad.json", bad))
add("gate 变异:待复核无不确定性必命中", rc == 1 and any("uncertainty" in e for e in d.get("errors", [])), str(d))
honest_partial = copy.deepcopy(BASE); honest_partial["status"] = "partial"
honest_partial["facets"]["statistics"] = {"status": "pending", "reason": "统计输出缺失"}
honest_partial["unchecked"] = ["Table 3 未提供，统计量无法复算"]
rc, d = run("gate", dump("gate-partial-good.json", honest_partial))
add("gate 正向:材料不足时诚实partial零误杀", rc == 0 and d.get("ok"), str(d))

ok = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
