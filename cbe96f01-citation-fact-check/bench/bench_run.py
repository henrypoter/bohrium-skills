#!/usr/bin/env python3
"""citation/fact review_tool v3：正向零误杀 + 定向变异必命中，纯标准库。"""
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
TMP = tempfile.mkdtemp(prefix="citation-review-bench-")
checks = []


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:400], "stderr": proc.stderr[:400]}


def dump(name, obj):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    return path


def write_text(name, text):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def qh(text):
    canonical = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def anchor(text, quote, source_hash):
    found = []
    for page_no, page in enumerate(text.split("\f"), 1):
        paras = re.split(r"(?:\r?\n)[ \t]*(?:\r?\n)+", page)
        for para_no, para in enumerate(paras, 1):
            if re.sub(r"\s+", "", unicodedata.normalize("NFKC", quote)) in re.sub(r"\s+", "", unicodedata.normalize("NFKC", para)):
                found.append((page_no, para_no))
    assert len(found) == 1, (quote, found)
    return {"page": found[0][0], "paragraph": found[0][1], "occurrence": 1,
            "quote_sha256": qh(quote), "source_sha256": source_hash}


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


M = "# 合成论文\n\n## 方法\n采用随机设计。\n\n## 结果\n记录结果。\n\n## 讨论\nLee 等报告药物 B 与血压下降相关[2]。\n\nSmith 等(2020)在1000例患者中证明药物A能治愈所有患者[1]。"
Q1 = "Lee 等报告药物 B 与血压下降相关[2]。"
Q2 = "Smith 等(2020)在1000例患者中证明药物A能治愈所有患者[1]。"
S1 = "Drug B was associated with lower blood pressure in 50 patients."
S2 = "In a pilot study of 20 patients, drug A was associated with lower blood pressure in some participants. No evidence demonstrates cure."
M_HASH, S1_HASH, S2_HASH = sha(M), sha(S1), sha(S2)
CLAIMS = [
    {"id": "C1", "source_id": "R2", "claim_quote": Q1, "claim_locator": anchor(M, Q1, M_HASH),
     "source_quote": S1, "source_locator": anchor(S1, S1, S1_HASH), "support": "full",
     "support_rationale": "来源直接报告药物B与血压下降相关，稿件未升级为因果。"},
    {"id": "C2", "source_id": "R1", "claim_quote": Q2, "claim_locator": anchor(M, Q2, M_HASH),
     "source_quote": S2, "source_locator": anchor(S2, S2, S2_HASH), "support": "none",
     "support_rationale": "来源为20例初步相关研究且明确无治愈证据，不支持1000例/治愈所有患者。"}
]
ISSUE = {"id": "F1", "category": "citation", "severity": "major", "defect_type": "fact_error",
         "review_status": "confirmed", "claim_id": "C2", "source_id": "R1",
         "location": anchor(M, Q2, M_HASH), "quote": Q2,
         "claim": "引文不支持治愈率/样本量，且所有患者结论越界", "fix": "按20例初步相关结果改写并删除治愈表述",
         "evidence": [{"source_id": "R1", "quote": S2,
                       "basis": "来源的20例、相关、部分参与者和无治愈证据与稿件肯定转述直接冲突",
                       "locator": anchor(S2, S2, S2_HASH)}]}
SOURCES = [
    {"source_id": "M", "role": "manuscript", "path": "manuscript.txt", "sha256": M_HASH},
    {"source_id": "R1", "role": "reference", "doi": "10.0000/r1", "url": "https://example.invalid/r1",
     "version": "published-v1", "publication_status": "published", "retraction_status": "not_retracted",
     "checked_at": "2026-11-25", "evidence_url": "https://registry.invalid/r1/status", "access": "open", "sha256": S2_HASH},
    {"source_id": "R2", "role": "reference", "doi": "10.0000/r2", "url": "https://example.invalid/r2",
     "version": "published-v1", "publication_status": "published", "retraction_status": "not_retracted",
     "checked_at": "2026-11-25", "evidence_url": "https://registry.invalid/r2/status", "access": "open", "sha256": S1_HASH}
]
REGISTRY = {
    "R1": {"canonical_doi": "10.0000/r1", "current_version": "published-v1", "publication_status": "published",
           "retraction_status": "not_retracted", "evidence_url": "https://registry.invalid/r1/status"},
    "R2": {"canonical_doi": "10.0000/r2", "current_version": "published-v1", "publication_status": "published",
           "retraction_status": "not_retracted", "evidence_url": "https://registry.invalid/r2/status"}
}
CATEGORIES = {name: {"status": "checked", "notes": "已按该类目回查原句，无论是否有issue", "reason": ""} for name in
              ["fact", "citation", "design", "statistics", "argument", "compliance"]}
SECTIONS = {name: {"status": "checked", "notes": "已阅读并登记该章节检查范围", "reason": ""} for name in
            ["methods", "results", "discussion"]}
BASE = {"schema_version": "3.0", "case_id": "bench-synthetic", "status": "issues",
        "manuscript_version": {"label": "synthetic-v1", "sha256": M_HASH, "files": ["manuscript.txt"]},
        "run": {"tool_version": "3.0.0", "run_id": "bench-run-001"},
        "contract": {"source": "/input/case.json#/output_contract", "preserved_fields": ["case_id", "status", "claims", "issues"]},
        "claims": CLAIMS, "issues": [ISSUE], "sources": SOURCES, "categories": CATEGORIES, "sections": SECTIONS,
        "checked_scope": {"did": ["全文与两条来源快照"], "not_checked": []}, "gain": {},
        "unchecked": [], "uncertainty": [], "change_log": ["合成bench，不是正式案例"]}
manuscript_path = write_text("manuscript.txt", M)
source_manifest = dump("source-manifest.json", {"sources": [{"source_id": "R1", "text": S2}, {"source_id": "R2", "text": S1}]})
claims_path = dump("claims-good.json", {"claims": CLAIMS})

# verify 基础原句闸
legacy = [{"id": "F1", "category": "citation", "severity": "major", "location": "讨论第2段", "quote": Q2,
           "claim": "不支持", "fix": "改写"}]
rc, d = run("verify", dump("verify-good.json", {"issues": legacy}), "--text", manuscript_path)
add("verify 正向:真实稿件原句零误杀", rc == 0 and d.get("ok"), str(d))
bad_legacy = [dict(legacy[0], quote="虚构且不存在的一句")]
rc, d = run("verify", dump("verify-bad.json", {"issues": bad_legacy}), "--text", manuscript_path)
add("verify 变异:伪造稿件原句必命中", rc == 1 and len(d.get("quote_not_in_source", [])) == 1, str(d))
rc, d = run("verify", dump("verify-dup.json", {"issues": legacy + [dict(legacy[0], id="F2")]}))
add("verify 变异:重复finding必命中", len(d.get("duplicates", [])) == 1, str(d))
rc, d = run("verify", dump("verify-hash.json", {"issues": [dict(legacy[0], quote_sha256="0" * 64)]}), "--text", manuscript_path)
add("verify 变异:错误quote哈希必命中", rc == 1 and any("quote_sha256" in e for e in d.get("errors", [])), str(d))

# locate 双侧段落锚点与重复项消歧
rc, d = run("locate", claims_path, "--manuscript", manuscript_path, "--sources", source_manifest)
add("locate 正向:稿件和来源双侧段落定位", rc == 0 and d.get("complete") and all(x.get("claim_anchor") and x.get("source_anchor") for x in d.get("claims", [])), str(d))
bad = copy.deepcopy(CLAIMS); bad[0]["claim_quote"] = "不存在的稿件论断"
rc, d = run("locate", dump("locate-claim-bad.json", {"claims": bad}), "--manuscript", manuscript_path, "--sources", source_manifest)
add("locate 变异:稿件论断不存在必命中", rc == 1 and any(e.get("side") == "manuscript" for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(CLAIMS); bad[0]["source_quote"] = "Invented source conclusion."
rc, d = run("locate", dump("locate-source-bad.json", {"claims": bad}), "--manuscript", manuscript_path, "--sources", source_manifest)
add("locate 变异:来源证据句不存在必命中", rc == 1 and any(e.get("side") == "source" for e in d.get("errors", [])), str(d))
repeated_text = "方法\n\n同一论断。\n\n结果\n\n同一论断。"
repeated_path = write_text("repeated.txt", repeated_text)
rep_claim = dict(copy.deepcopy(CLAIMS[0]), claim_quote="同一论断。")
rc, d = run("locate", dump("locate-ambiguous.json", {"claims": [rep_claim]}), "--manuscript", repeated_path, "--sources", source_manifest)
add("locate 变异:重复引文不消歧必命中", rc == 1 and any(e.get("error") == "ambiguous_quote_occurrence" for e in d.get("errors", [])), str(d))
rep_claim["claim_occurrence"] = 2
rc, d = run("locate", dump("locate-disambiguated.json", {"claims": [rep_claim]}), "--manuscript", repeated_path, "--sources", source_manifest)
add("locate 正向:显式occurrence可准确消歧", rc == 0 and d["claims"][0]["claim_anchor"]["paragraph"] == 4, str(d))
missing_manifest = dump("source-missing.json", {"sources": [{"source_id": "R2", "path": "not-here.txt"}]})
one_claim = dump("one-claim.json", {"claims": [CLAIMS[0]]})
rc, d = run("locate", one_claim, "--manuscript", manuscript_path, "--sources", missing_manifest)
add("locate 变异:原文取不到默认必拦截", rc == 1 and not d.get("complete"), str(d))
rc, d = run("locate", one_claim, "--manuscript", manuscript_path, "--sources", missing_manifest, "--allow-partial")
add("locate 正向:原文取不到可诚实partial", rc == 0 and d.get("ok") and not d.get("complete") and d.get("status") == "partial", str(d))
bad = copy.deepcopy(CLAIMS); bad[0]["source_quote_sha256"] = "0" * 64
rc, d = run("locate", dump("locate-hash-bad.json", {"claims": bad}), "--manuscript", manuscript_path, "--sources", source_manifest)
add("locate 变异:来源quote哈希错误必命中", rc == 1 and any(e.get("error") == "quote_sha256_mismatch" for e in d.get("errors", [])), str(d))

# align：先验证标签与保守语义冲突，不声称通用自然语言推理
rc, d = run("align", claims_path)
add("align 正向:full与none标签均不误杀", rc == 0 and d.get("ok"), str(d))
partial = copy.deepcopy(CLAIMS); partial[1]["support"] = "partial"
partial[1]["support_rationale"] = "来源只支持部分患者血压相关下降，明确不支持治愈与所有患者。"
rc, d = run("align", dump("align-partial-good.json", {"claims": partial}))
add("align 正向:如实partial不因范围差异误杀", rc == 0 and not d.get("support_label_mismatches"), str(d))
unknown = copy.deepcopy(CLAIMS); unknown[0]["support"] = "unknown"
unknown[0]["support_rationale"] = "权限不足，仅见摘要，待复核全文。"
unknown_path = dump("align-unknown.json", {"claims": unknown})
rc, d = run("align", unknown_path)
add("align 变异:无法判定默认不得伪装完成", rc == 1 and d.get("needs_review") == ["C1"], str(d))
rc, d = run("align", unknown_path, "--allow-unknown")
add("align 正向:显式unknown允许partial", rc == 0 and d.get("ok") and not d.get("complete"), str(d))
wrong = copy.deepcopy(CLAIMS); wrong[1]["support"] = "full"
wrong[1]["support_rationale"] = "故意把不支持错标为完整支持的变异。"
rc, d = run("align", dump("align-scope-bad.json", {"claims": wrong}))
add("align 变异:范围/样本/方向错标full必命中", rc == 1 and len(d.get("support_label_mismatches", [])) >= 1, str(d))
causal_bad = [{"id": "X", "source_id": "R", "claim_quote": "Drug B causes lower blood pressure.",
               "source_quote": S1, "support": "full", "support_rationale": "错误完整支持标签。"}]
rc, d = run("align", dump("align-causal-bad.json", {"claims": causal_bad}))
add("align 变异:相关证据支持因果必命中", rc == 1 and any(x.get("type") == "causal_overreach" for x in d.get("support_label_mismatches", [])), str(d))
sample_bad = [{"id": "N", "source_id": "R", "claim_quote": "The trial included 1000 patients.",
               "source_quote": "The trial included 20 patients.", "support": "full", "support_rationale": "错误样本量支持。"}]
rc, d = run("align", dump("align-n-bad.json", {"claims": sample_bad}))
add("align 变异:显式样本量矛盾必命中", rc == 1 and any(x.get("type") == "sample_size_mismatch" for x in d.get("support_label_mismatches", [])), str(d))
chinese_n_bad = [{"id": "NC", "source_id": "R", "claim_quote": "研究纳入1000例患者。",
                  "source_quote": "研究纳入20例患者。", "support": "full", "support_rationale": "错误中文样本量支持。"}]
rc, d = run("align", dump("align-chinese-n-bad.json", {"claims": chinese_n_bad}))
add("align 变异:中文样本量矛盾必命中", rc == 1 and any(x.get("type") == "sample_size_mismatch" for x in d.get("support_label_mismatches", [])), str(d))
direction_bad = [{"id": "D", "source_id": "R", "claim_quote": "The treatment is effective and significant.",
                  "source_quote": "The treatment showed no significant benefit.", "support": "full", "support_rationale": "错误方向标签。"}]
rc, d = run("align", dump("align-direction-bad.json", {"claims": direction_bad}))
add("align 变异:来源否定却标full必命中", rc == 1 and any(x.get("type") == "direction_conflict" for x in d.get("support_label_mismatches", [])), str(d))
missing = copy.deepcopy(CLAIMS); missing[0]["support_rationale"] = ""
rc, d = run("align", dump("align-missing.json", {"claims": missing}))
add("align 变异:缺语义判定依据必命中", rc == 1 and any(x.get("field") == "support_rationale" for x in d.get("missing_fields", [])), str(d))

# provenance：只核带来源的registry快照
sources_path, registry_path = dump("sources-good.json", {"sources": SOURCES}), dump("registry-good.json", REGISTRY)
rc, d = run("provenance", sources_path, "--registry", registry_path)
add("provenance 正向:版本标识状态完整零误杀", rc == 0 and d.get("complete"), str(d))
bad_sources = copy.deepcopy(SOURCES); bad_sources[1]["retraction_status"] = "retracted"
rc, d = run("provenance", dump("sources-retracted.json", {"sources": bad_sources}), "--registry", registry_path)
add("provenance 变异:撤稿来源必命中", rc == 1 and any(x.get("reason") == "retracted_source" for x in d.get("blocking", [])), str(d))
bad_sources = copy.deepcopy(SOURCES); bad_sources[1]["version"] = "preprint-v0"; bad_sources[1]["publication_status"] = "preprint"
version_bad_path = dump("sources-version-bad.json", {"sources": bad_sources})
rc, d = run("provenance", version_bad_path, "--registry", registry_path)
add("provenance 变异:预印本/正式版不一致必命中", rc == 1 and any(x.get("reason") == "version_mismatch" for x in d.get("blocking", [])), str(d))
disclosed = copy.deepcopy(bad_sources)
for src in disclosed:
    if src["source_id"] == "R1":
        src["version_difference_disclosed"] = True
rc, d = run("provenance", dump("sources-version-disclosed.json", {"sources": disclosed}), "--registry", registry_path)
add("provenance 正向:版本差异明示不误杀", rc == 0 and any("version_difference_disclosed" in x.get("warnings", []) for x in d.get("sources", [])), str(d))
bad_sources = copy.deepcopy(SOURCES); bad_sources[1]["doi"] = "10.0000/wrong"
rc, d = run("provenance", dump("sources-doi-bad.json", {"sources": bad_sources}), "--registry", registry_path)
add("provenance 变异:DOI与registry不一致必命中", rc == 1 and any(x.get("reason") == "identifier_mismatch" for x in d.get("blocking", [])), str(d))
paywall = copy.deepcopy(SOURCES); paywall[1]["access"] = "permission_denied"
paywall_path = dump("sources-permission.json", {"sources": paywall})
rc, d = run("provenance", paywall_path, "--registry", registry_path)
add("provenance 变异:数据库权限不足默认不伪装完成", rc == 1 and "R1" in d.get("incomplete_sources", []), str(d))
rc, d = run("provenance", paywall_path, "--registry", registry_path, "--allow-incomplete")
add("provenance 正向:权限不足可诚实partial", rc == 0 and d.get("ok") and not d.get("complete"), str(d))
unknown_status = copy.deepcopy(SOURCES); unknown_status[1]["retraction_status"] = "unknown"
unknown_reg = copy.deepcopy(REGISTRY); unknown_reg["R1"]["retraction_status"] = "unknown"
unknown_prov_path = dump("sources-prov-unknown.json", {"sources": unknown_status})
rc, d = run("provenance", unknown_prov_path, "--registry", dump("registry-unknown.json", unknown_reg))
add("provenance 变异:撤稿状态未知不得当not_retracted", rc == 1 and "R1" in d.get("incomplete_sources", []), str(d))
rc, d = run("provenance", unknown_prov_path, "--registry", dump("registry-unknown.json", unknown_reg), "--allow-incomplete")
add("provenance 正向:撤稿未知可显式降级", rc == 0 and not d.get("complete"), str(d))

# coverage
rc, d = run("coverage", dump("coverage-good.json", BASE))
add("coverage 正向:六类三章节有记录零误杀", rc == 0 and d.get("ok"), str(d))
bad = copy.deepcopy(BASE); del bad["categories"]["citation"]
rc, d = run("coverage", dump("coverage-missing.json", bad))
add("coverage 变异:引用支持漏查必命中", rc == 1 and any("citation" in e for e in d.get("errors", [])), str(d))
partial_cov = copy.deepcopy(BASE); partial_cov["sections"]["discussion"] = {"status": "pending", "reason": "讨论页缺失"}
partial_cov_path = dump("coverage-partial.json", partial_cov)
rc, d = run("coverage", partial_cov_path)
add("coverage 变异:讨论章节未查默认拦截", rc == 1 and "sections.discussion" in d.get("incomplete", []), str(d))
rc, d = run("coverage", partial_cov_path, "--allow-partial")
add("coverage 正向:章节缺失允许显式partial", rc == 0 and d.get("incomplete"), str(d))

# gate：双侧锚点、来源版本和引用结论之间的可复核关联
rc, d = run("gate", dump("gate-good.json", BASE))
add("gate 正向:完整引用审查零误杀", rc == 0 and d.get("ok"), str(d))
rc, d = run("schema", dump("schema-good.json", BASE))
add("schema 正向:基础契约向后兼容", rc == 0 and d.get("ok"), str(d))
for label, mutate, token in [
    ("缺run_id", lambda x: x["run"].pop("run_id"), "run_id"),
    ("缺原契约字段清单", lambda x: x.pop("contract"), "contract"),
    ("来源quote哈希篡改", lambda x: x["claims"][0]["source_locator"].update(quote_sha256="0" * 64), "不匹配"),
    ("证据锚点指向错误全文", lambda x: x["claims"][0]["source_locator"].update(source_sha256="1" * 64), "注册来源全文"),
    ("来源撤稿核验日期缺失", lambda x: x["sources"][1].pop("checked_at"), "checked_at"),
    ("来源版本缺失", lambda x: x["sources"][1].pop("version"), "version"),
]:
    bad = copy.deepcopy(BASE); mutate(bad)
    rc, d = run("gate", dump("gate-" + str(len(checks)) + ".json", bad))
    add("gate 变异:" + label + "必命中", rc == 1 and any(token in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["issues"] = []; bad["status"] = "pass"
rc, d = run("gate", dump("gate-unlinked.json", bad))
add("gate 变异:none支持却无关联问题必命中", rc == 1 and any("没有关联 issue" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["sources"][2]["retraction_status"] = "retracted"
rc, d = run("gate", dump("gate-retracted-unlinked.json", bad))
add("gate 变异:撤稿来源无关联问题必命中", rc == 1 and any("撤稿来源" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["claims"][0]["support"] = "unknown"
rc, d = run("gate", dump("gate-unknown-no-note.json", bad))
add("gate 变异:unknown无不确定性记录必命中", rc == 1 and any("uncertainty" in e or "不确定性" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["sources"][1]["access"] = "permission_denied"
rc, d = run("gate", dump("gate-access-no-note.json", bad))
add("gate 变异:权限不足无边界说明必命中", rc == 1 and any("权限" in e for e in d.get("errors", [])), str(d))
bad = copy.deepcopy(BASE); bad["issues"][0]["defect_type"] = "suggestion"
rc, d = run("gate", dump("gate-severity.json", bad))
add("gate 变异:建议冒充major必命中", rc == 1 and any("suggestion" in e for e in d.get("errors", [])), str(d))
honest_partial = copy.deepcopy(BASE); honest_partial["status"] = "partial"
honest_partial["claims"][0]["support"] = "unknown"
honest_partial["claims"][0]["support_rationale"] = "来源权限不足，暂不能完整判定。"
honest_partial["sources"][2]["access"] = "permission_denied"
honest_partial["unchecked"] = ["R2全文因数据库权限不足未核"]
honest_partial["uncertainty"] = ["C1: 仅核摘要/元数据，support=unknown，待取得全文"]
rc, d = run("gate", dump("gate-partial-good.json", honest_partial))
add("gate 正向:权限受限的partial有证据边界零误杀", rc == 0 and d.get("ok"), str(d))

ok = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
