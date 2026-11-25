#!/usr/bin/env python3
"""Executable mutation bench for every review_tool command; standard library only."""
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TOOL = os.path.join(ROOT, "scripts", "review_tool.py")
SAMPLE = os.path.join(HERE, "fixtures", "sample_paper.txt")
TMP = tempfile.mkdtemp(prefix="paper-review-bench-")
CHECKS = []


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    if proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = {"raw": proc.stdout[:300]}
    else:
        data = {"ok": proc.returncode == 0}
    if proc.returncode not in (0, 1) and not data.get("error"):
        data["stderr"] = proc.stderr[:200]
    return proc.returncode, data


def dump(name, value):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    return path


def add(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))


with open(SAMPLE, "rb") as handle:
    RAW = handle.read()
TEXT = RAW.decode("utf-8")
TEXT_SHA = sha(RAW)

# Build locators only through the public index command.
INDEX_PATH = os.path.join(TMP, "index.json")
rc, data = run("index", SAMPLE, "--out", INDEX_PATH)
with open(INDEX_PATH, encoding="utf-8") as handle:
    INDEX = json.load(handle)
add("index positive: exact sentence coordinates and hashes", rc == 0 and INDEX["ok"]
    and any(s["quote"] == "患者姓名：张三，随访数据已进入分析表。" for s in INDEX["sentences"])
    and INDEX["source_sha256"] == TEXT_SHA)
mutated_path = os.path.join(TMP, "mutated.txt")
with open(mutated_path, "w", encoding="utf-8", newline="") as handle:
    handle.write(TEXT.replace("患者姓名：张三", "患者姓名：李四", 1))
mutated_index_path = os.path.join(TMP, "mutated-index.json")
rc, data = run("index", mutated_path, "--out", mutated_index_path)
with open(mutated_index_path, encoding="utf-8") as handle:
    MUTATED_INDEX = json.load(handle)
add("index mutation: changed manuscript cannot reuse hash", rc == 0
    and MUTATED_INDEX["source_sha256"] != TEXT_SHA)


def make_span(quote, role="primary"):
    matches = [s for s in INDEX["sentences"] if quote in s["quote"]]
    if len(matches) != 1:
        raise AssertionError("fixture quote must occur in exactly one sentence: " + quote)
    sentence = matches[0]
    loc = copy.deepcopy(sentence["location"])
    relative = sentence["quote"].index(quote)
    loc["char_start"] += relative
    loc["char_end"] = loc["char_start"] + len(quote)
    return {"role": role, "location": loc, "quote": quote, "quote_sha256": sha(quote.encode("utf-8"))}


def make_issue(identifier, category, quote, claim, statement, decision="confirmed"):
    primary = make_span(quote)
    return {
        "id": identifier,
        "category": category,
        "type": "insufficient_evidence" if decision == "confirmed" else "suggestion",
        "severity": "major",
        "status": decision,
        "location": copy.deepcopy(primary["location"]),
        "quote": quote,
        "quote_sha256": primary["quote_sha256"],
        "claim": claim,
        "evidence": [primary],
        "basis": [{"kind": "manuscript_crosscheck", "source": "sample_paper.txt",
                   "locator": primary["location"]["sentence_id"], "statement": statement}],
        "fix": {"action": "clarify", "target": primary["location"]["sentence_id"],
                "instruction": "Limit the statement to the observed sample and explicitly state the missing evidential link.",
                "suggested_text": "In this 30-patient uncontrolled sample, blood pressure decreased."},
    }


GOOD_ISSUE = make_issue(
    "P1", "privacy", "张三",
    "A direct patient name is present; the general ethics/consent sentence does not establish permission to publish it.",
    "The exact labeled name is present and must be reviewed separately from the nearby general consent statement."
)


def result(issues, case_id="bench-quality"):
    scope = {category: {"status": "checked", "search_scope": "all extracted manuscript sentences",
                        "reason": "no issue found in this facet"} for category in
             ("integrity", "citation", "privacy", "copyright", "ethics", "submission")}
    return {
        "result_schema_version": "2.0.0",
        "tool_version": "3.0.0",
        "case_id": case_id,
        "status": "issues" if issues else "pass",
        "manuscript_version": {"file": "sample_paper.txt", "source_id": "manuscript_text",
                               "file_sha256": TEXT_SHA, "text_sha256": TEXT_SHA,
                               "extractor": "UTF-8 fixture reader v1"},
        "issues": copy.deepcopy(issues),
        "checked_scope": scope,
        "gain": {"status": "not_measured", "reason": "awaiting independent baseline adjudication"},
        "unchecked": [],
        "sources": [{"source_id": "manuscript_text", "path_or_url": "sample_paper.txt",
                     "role": "manuscript", "sha256": TEXT_SHA}],
        "uncertainty": [],
        "change_log": ["fixture generated through public index command"],
        "runtime": {"elapsed_seconds": 100.0, "manual_review_seconds": 40.0, "rounds": 2},
    }


GOOD = result([GOOD_ISSUE])
GOOD_PATH = dump("good.json", GOOD)

rc, data = run("verify", GOOD_PATH, "--source", "manuscript_text=" + SAMPLE)
add("verify positive: exact quote/location/hash zero false rejection", rc == 0 and data.get("ok"), str(data)[:240])
bad = copy.deepcopy(GOOD)
bad["issues"][0]["quote"] = bad["issues"][0]["quote"].replace("张三", "李四")
bad["issues"][0]["quote_sha256"] = sha(bad["issues"][0]["quote"].encode("utf-8"))
bad["issues"][0]["evidence"][0]["quote"] = bad["issues"][0]["quote"]
bad["issues"][0]["evidence"][0]["quote_sha256"] = bad["issues"][0]["quote_sha256"]
rc, data = run("verify", dump("bad-quote.json", bad), "--source", "manuscript_text=" + SAMPLE)
add("verify mutation: paraphrased quote must fail", rc == 1 and not data.get("ok")
    and any(e["error"] == "quote_not_in_source" for e in data.get("errors", [])), str(data)[:240])
bad = copy.deepcopy(GOOD)
bad["issues"][0]["location"]["line_start"] += 1
rc, data = run("verify", dump("bad-location.json", bad), "--source", "manuscript_text=" + SAMPLE)
add("verify mutation: wrong sentence line must fail", rc == 1
    and any(e["error"] == "location_line_start_mismatch" for e in data.get("errors", [])), str(data)[:240])
bad = copy.deepcopy(GOOD)
bad["manuscript_version"]["text_sha256"] = MUTATED_INDEX["source_sha256"]
rc, data = run("verify", dump("bad-version.json", bad), "--source", "manuscript_text=" + SAMPLE)
add("verify mutation: result bound to another text hash must fail", rc == 1
    and any(e["error"] == "text_hash_mismatch" for e in data.get("errors", [])), str(data)[:240])

CITATIONS_PATH = os.path.join(TMP, "citations.json")
rc, data = run("citations", SAMPLE, "--out", CITATIONS_PATH)
with open(CITATIONS_PATH, encoding="utf-8") as handle:
    CITATIONS = json.load(handle)
add("citations positive: resolved entry does not invent support verdict", rc == 0 and CITATIONS["ok"]
    and len(CITATIONS["inline_citations"]) == 0  # fixture uses author-year, which is explicitly out of scope
    and CITATIONS["status"] == "checked")
NUMERIC_PATH = os.path.join(TMP, "numeric.txt")
with open(NUMERIC_PATH, "w", encoding="utf-8", newline="") as handle:
    handle.write("As reported previously [1], the effect replicated.\n\n## References\n[1] Lee A. Original source. Journal. 2024.\n")
rc, data = run("citations", NUMERIC_PATH, "--out", os.path.join(TMP, "numeric-citations.json"))
with open(os.path.join(TMP, "numeric-citations.json"), encoding="utf-8") as handle:
    NUMERIC_CITATIONS = json.load(handle)
add("citations positive: numeric claim/source pair resolved", rc == 0 and NUMERIC_CITATIONS["ok"]
    and NUMERIC_CITATIONS["inline_citations"][0]["support"] == "not_checked"
    and len(NUMERIC_CITATIONS["inline_citations"][0]["reference_entries"]) == 1)
with open(NUMERIC_PATH, "a", encoding="utf-8", newline="") as handle:
    # Modify the citation, not the bibliography, to create a dangling reference.
    content = open(NUMERIC_PATH, encoding="utf-8").read().replace("[1]", "[2]", 1)
with open(NUMERIC_PATH, "w", encoding="utf-8", newline="") as handle:
    handle.write(content)
rc, data = run("citations", NUMERIC_PATH, "--out", os.path.join(TMP, "dangling-citations.json"))
with open(os.path.join(TMP, "dangling-citations.json"), encoding="utf-8") as handle:
    DANGLING = json.load(handle)
add("citations mutation: dangling [2] must hit exact marker", rc == 1 and not DANGLING["ok"]
    and DANGLING["unresolved_citations"][0]["reference_number"] == 2
    and DANGLING["unresolved_citations"][0]["marker"]["quote"] == "[2]")

rc, data = run("schema", GOOD_PATH)
add("schema positive: complete result zero false rejection", rc == 0 and data.get("ok"), str(data)[:240])
bad = copy.deepcopy(GOOD)
bad.pop("result_schema_version")
rc, data = run("schema", dump("no-version.json", bad))
add("schema mutation: missing result version must fail", rc == 1
    and any("result_schema_version" in e for e in data.get("errors", [])))
bad = copy.deepcopy(GOOD)
bad["issues"][0]["quote_sha256"] = "0" * 64
rc, data = run("schema", dump("bad-hash.json", bad))
add("schema mutation: false quote hash must fail", rc == 1
    and any("quote_sha256" in e for e in data.get("errors", [])))
bad = copy.deepcopy(GOOD)
bad["issues"][0]["fix"] = {"action": "clarify", "target": "注意", "instruction": "建议检查"}
rc, data = run("schema", dump("generic-fix.json", bad))
add("schema mutation: non-actionable suggestion must fail", rc == 1
    and sum("not executable" in e for e in data.get("errors", [])) == 2)

rc, data = run("coverage", GOOD_PATH)
add("coverage positive: explicit checked dispositions pass with zero false rejection", rc == 0 and data.get("ok"))
bad = copy.deepcopy(GOOD)
bad["issues"] = []
bad["checked_scope"]["copyright"] = {"status": "not_checked", "reason": ""}
rc, data = run("coverage", dump("coverage-gap.json", bad))
add("coverage mutation: silent unchecked copyright facet must fail", rc == 1
    and any("copyright.reason" in e for e in data.get("errors", [])))
empty = result([])
empty_path = dump("empty-checked.json", empty)
rc, data = run("coverage", empty_path)
add("coverage positive: zero findings plus real checked scopes is valid", rc == 0 and data.get("ok"))

BASELINE_ISSUE = make_issue("B1", "copyright", "CC BY 4.0", "A CC BY label permits removing attribution.",
                            "Adjudication fixture: CC BY requires appropriate attribution; the baseline claim is unsupported.")
BASELINE = result([BASELINE_ISSUE])
BASELINE["runtime"] = {"elapsed_seconds": 160.0, "manual_review_seconds": 90.0, "rounds": 4}
SKILL = result([GOOD_ISSUE])
SKILL["runtime"] = {"elapsed_seconds": 100.0, "manual_review_seconds": 40.0, "rounds": 2}
DECISIONS = {
    "case_id": "bench-quality", "text_sha256": TEXT_SHA,
    "permissions": "same local files; no network for either arm",
    "allowed_sources": "same manuscript and supplied compliance sources only",
    "budget": "same one-run fixture budget",
    "baseline": {"B1": "unsupported"}, "skill": {"P1": "supported"},
}
COMPARE_PATH = os.path.join(TMP, "gain.json")
rc, data = run("compare", dump("baseline.json", BASELINE), dump("skill.json", SKILL),
               "--decisions", dump("decisions.json", DECISIONS), "--out", COMPARE_PATH)
with open(COMPARE_PATH, encoding="utf-8") as handle:
    GAIN = json.load(handle)
add("compare positive: measured quality/efficiency gain", rc == 0 and GAIN["ok"]
    and GAIN["quality"]["delta_precision_decided"] == 1.0
    and GAIN["efficiency"]["manual_review_seconds_saved"] == 50.0)
SKILL["gain"] = GAIN
rc, data = run("schema", dump("measured-skill.json", SKILL))
add("compare integration: measured gain is valid result.json content", rc == 0 and data.get("ok"), str(data)[:240])
BAD_DECISIONS = copy.deepcopy(DECISIONS)
BAD_DECISIONS["text_sha256"] = MUTATED_INDEX["source_sha256"]
rc, data = run("compare", dump("baseline2.json", BASELINE), dump("skill2.json", SKILL),
               "--decisions", dump("wrong-input-decisions.json", BAD_DECISIONS))
add("compare mutation: cross-manuscript comparison must fail", rc == 1
    and any("adjudication" in e for e in data.get("errors", [])))
BAD_DECISIONS = copy.deepcopy(DECISIONS)
BAD_DECISIONS["skill"] = {}
rc, data = run("compare", dump("baseline3.json", BASELINE), dump("skill3.json", SKILL),
               "--decisions", dump("incomplete-decisions.json", BAD_DECISIONS))
add("compare mutation: unadjudicated issue cannot become a score", rc == 1
    and any("IDs differ" in e for e in data.get("errors", [])))

BAD_DECISIONS = copy.deepcopy(DECISIONS)
BAD_DECISIONS.pop("permissions")
rc, data = run("compare", dump("baseline4.json", BASELINE), dump("skill4.json", SKILL),
               "--decisions", dump("missing-permissions-decisions.json", BAD_DECISIONS))
add("compare mutation: undocumented shared permissions must fail", rc == 1
    and any("permissions" in e for e in data.get("errors", [])))

# Privacy scanner: safe text must stay clean; direct identifiers and restricted data must hit.
SAFE_PRIVACY = os.path.join(TMP, "safe-privacy.txt")
with open(SAFE_PRIVACY, "w", encoding="utf-8", newline="") as handle:
    handle.write("## Methods\nAll participants were deidentified. Ethics approval EX-1 and informed consent were obtained.\nCorresponding author: public@example.org.\nInvalid ID 110105194912310021 is not an identifier match.\n")
SAFE_PRIVACY_OUT = os.path.join(TMP, "safe-privacy.json")
rc, data = run("privacy", SAFE_PRIVACY, "--out", SAFE_PRIVACY_OUT)
with open(SAFE_PRIVACY_OUT, encoding="utf-8") as handle:
    SAFE_PRIVACY_RESULT = json.load(handle)
add("privacy positive: deidentified text/corresponding email/invalid ID zero false positives", rc == 0
    and SAFE_PRIVACY_RESULT["ok"] and SAFE_PRIVACY_RESULT["findings"] == [], str(SAFE_PRIVACY_RESULT)[:240])
PRIVACY_OUT = os.path.join(TMP, "privacy.json")
rc, data = run("privacy", SAMPLE, "--out", PRIVACY_OUT)
with open(PRIVACY_OUT, encoding="utf-8") as handle:
    PRIVACY_RESULT = json.load(handle)
add("privacy mutation: labeled direct name must hit exact span and action", rc == 0
    and len(PRIVACY_RESULT["findings"]) == 1
    and PRIVACY_RESULT["findings"][0]["quote"] == "张三"
    and PRIVACY_RESULT["findings"][0]["fix"]["action"] == "deidentify")
ID_PRIVACY = os.path.join(TMP, "id-privacy.txt")
with open(ID_PRIVACY, "w", encoding="utf-8", newline="") as handle:
    handle.write("受试者身份证件号：11010519491231002X。手机号13800138000。使用受限数据集开展分析。")
rc, data = run("privacy", ID_PRIVACY, "--out", os.path.join(TMP, "id-privacy.json"))
with open(os.path.join(TMP, "id-privacy.json"), encoding="utf-8") as handle:
    ID_RESULT = json.load(handle)
add("privacy mutation: checksum-valid ID/mobile/restricted dataset all detected", rc == 0
    and {f["basis"][0]["locator"] for f in ID_RESULT["findings"]} >=
    {"privacy.prc_resident_id", "privacy.mainland_mobile", "privacy.restricted_dataset"},
    str(ID_RESULT)[:300])
# A finding generated by the scanner is directly valid inside the common result contract.
SCAN_RESULT = result([PRIVACY_RESULT["findings"][0]])
rc, data = run("verify", dump("privacy-result.json", SCAN_RESULT), "--source", "manuscript_text=" + SAMPLE)
add("privacy integration: generated finding survives exact source verification", rc == 0 and data.get("ok"), str(data)[:240])

# License scanner: licensed CC BY adaptation passes; unstated and ND adaptations are candidates.
LICENSE_OUT = os.path.join(TMP, "license.json")
rc, data = run("license", SAMPLE, "--out", LICENSE_OUT)
with open(LICENSE_OUT, encoding="utf-8") as handle:
    LICENSE_RESULT = json.load(handle)
add("license positive: attributed CC BY adaptation zero false positives", rc == 0
    and LICENSE_RESULT["findings"] == [] and len(LICENSE_RESULT["passed_assets"]) == 1,
    str(LICENSE_RESULT)[:240])
NO_LICENSE = os.path.join(TMP, "no-license.txt")
with open(NO_LICENSE, "w", encoding="utf-8", newline="") as handle:
    handle.write(TEXT.replace("采用 CC BY 4.0 许可，", "", 1))
rc, data = run("license", NO_LICENSE, "--out", os.path.join(TMP, "no-license.json"))
with open(os.path.join(TMP, "no-license.json"), encoding="utf-8") as handle:
    NO_LICENSE_RESULT = json.load(handle)
add("license mutation: third-party reuse without license must hit", rc == 0
    and len(NO_LICENSE_RESULT["findings"]) == 1
    and NO_LICENSE_RESULT["findings"][0]["basis"][0]["locator"] == "copyright.third_party_license_unstated")
ND_LICENSE = os.path.join(TMP, "nd-license.txt")
with open(ND_LICENSE, "w", encoding="utf-8", newline="") as handle:
    handle.write(TEXT.replace("CC BY 4.0", "CC BY-ND 4.0", 1))
rc, data = run("license", ND_LICENSE, "--out", os.path.join(TMP, "nd-license.json"))
with open(os.path.join(TMP, "nd-license.json"), encoding="utf-8") as handle:
    ND_RESULT = json.load(handle)
add("license mutation: adapted ND asset must hit separate-permission action", rc == 0
    and ND_RESULT["findings"][0]["basis"][0]["locator"] == "copyright.nd_adaptation_conflict"
    and ND_RESULT["findings"][0]["fix"]["action"] == "obtain_permission")
LICENSE_INTEGRATION = result([ND_RESULT["findings"][0]])
rc, data = run("verify", dump("license-result.json", LICENSE_INTEGRATION), "--source", "manuscript_text=" + ND_LICENSE)
# Top-level version hash must follow the mutated source as well.
LICENSE_INTEGRATION["manuscript_version"]["file_sha256"] = sha(open(ND_LICENSE, "rb").read())
LICENSE_INTEGRATION["manuscript_version"]["text_sha256"] = LICENSE_INTEGRATION["manuscript_version"]["file_sha256"]
rc, data = run("verify", dump("license-result.json", LICENSE_INTEGRATION), "--source", "manuscript_text=" + ND_LICENSE)
add("license integration: generated ND finding survives exact source verification", rc == 0 and data.get("ok"), str(data)[:240])

# Versioned journal guide: a compliant guide yields no issue; tightened and missing rules must hit.
GUIDE = {
    "guide_version": "example-guide-2026.1", "guide_date": "2026-01-01",
    "source": "bench synthetic guide; not a real journal requirement",
    "rules": [
        {"id": "ethics-present", "kind": "required_pattern", "pattern": "知情同意", "description": "State informed consent."},
        {"id": "methods-length", "kind": "max_words", "section": "方法", "limit": 500, "description": "Methods at most 500 counted tokens."},
        {"id": "page-limit", "kind": "max_pages", "limit": 10, "description": "At most ten pages."},
    ],
}
GUIDE_PATH = dump("guide.json", GUIDE)
GUIDE_OUT = os.path.join(TMP, "guide-result.json")
rc, data = run("guidelines", GUIDE_PATH, SAMPLE, "--out", GUIDE_OUT)
with open(GUIDE_OUT, encoding="utf-8") as handle:
    GUIDE_RESULT = json.load(handle)
add("guidelines positive: satisfied versioned rules zero false positives", rc == 0
    and GUIDE_RESULT["status"] == "pass" and GUIDE_RESULT["findings"] == [], str(GUIDE_RESULT)[:240])
BAD_GUIDE = copy.deepcopy(GUIDE)
BAD_GUIDE["rules"][1]["limit"] = 1
BAD_GUIDE["rules"].append({"id": "coi-section", "kind": "required_section", "pattern": "利益冲突|Conflict of Interest",
                           "description": "Include a conflict-of-interest section."})
rc, data = run("guidelines", dump("bad-guide.json", BAD_GUIDE), SAMPLE, "--out", os.path.join(TMP, "bad-guide-result.json"))
with open(os.path.join(TMP, "bad-guide-result.json"), encoding="utf-8") as handle:
    BAD_GUIDE_RESULT = json.load(handle)
add("guidelines mutation: over-limit and absent section both hit", rc == 0
    and len(BAD_GUIDE_RESULT["findings"]) == 2
    and {f["detection"] for f in BAD_GUIDE_RESULT["findings"]} == {"limit", "absence"},
    str(BAD_GUIDE_RESULT)[:300])
GUIDE_RESULT_CONTRACT = result([BAD_GUIDE_RESULT["findings"][1]])
rc, data = run("schema", dump("guide-contract.json", GUIDE_RESULT_CONTRACT))
add("guidelines integration: absence evidence/version/date satisfy schema", rc == 0 and data.get("ok"), str(data)[:300])
BAD_GUIDE_CONTRACT = copy.deepcopy(GUIDE_RESULT_CONTRACT)
BAD_GUIDE_CONTRACT["issues"][0].pop("absence_evidence")
rc, data = run("schema", dump("bad-guide-contract.json", BAD_GUIDE_CONTRACT))
add("guidelines mutation: absence claim without searched scope must fail schema", rc == 1
    and any("absence_evidence" in e for e in data.get("errors", [])))

passed = sum(condition for _, condition, _ in CHECKS)
for name, condition, detail in CHECKS:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition and detail else ""))
print("total %d/%d" % (passed, len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
