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
    and any(s["quote"] == "采用单组前后对照设计，未设安慰剂对照组。" for s in INDEX["sentences"])
    and INDEX["source_sha256"] == TEXT_SHA)
mutated_path = os.path.join(TMP, "mutated.txt")
with open(mutated_path, "w", encoding="utf-8", newline="") as handle:
    handle.write(TEXT.replace("30 例患者", "31 例患者", 1))
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
    "P1", "argument", "证明药物 A 对所有高血压患者均有效",
    "A 30-patient uncontrolled before/after sample does not support universal efficacy.",
    "The method states no placebo control and the abstract states 30 patients; universal causal efficacy exceeds this design."
)


def result(issues, case_id="bench-quality"):
    scope = {category: {"status": "checked", "search_scope": "all extracted manuscript sentences",
                        "reason": "no issue found in this facet"} for category in
             ("fact", "citation", "design", "statistics", "argument", "compliance")}
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
bad["issues"][0]["quote"] = bad["issues"][0]["quote"].replace("所有", "全部")
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

absent = copy.deepcopy(GOOD)
absent["issues"][0]["detection"] = "absence"
absent["issues"][0]["absence_evidence"] = {"searched": True, "search_scope": "all extracted manuscript sentences",
    "source_sha256": TEXT_SHA, "expected": "a synthetic required statement", "statement": "Full supplied scope searched; the quote is only an anchor."}
rc, data = run("schema", dump("absence-good.json", absent))
add("schema positive: absence claim with searched scope zero false rejection", rc == 0 and data.get("ok"), str(data)[:240])
bad = copy.deepcopy(absent)
bad["issues"][0].pop("absence_evidence")
rc, data = run("schema", dump("absence-bad.json", bad))
add("schema mutation: absence claim without searched scope must fail", rc == 1
    and any("absence_evidence" in e for e in data.get("errors", [])))

rc, data = run("coverage", GOOD_PATH)
add("coverage positive: explicit checked dispositions pass with zero false rejection", rc == 0 and data.get("ok"))
bad = copy.deepcopy(GOOD)
bad["issues"] = []
bad["checked_scope"]["design"] = {"status": "not_checked", "reason": ""}
rc, data = run("coverage", dump("coverage-gap.json", bad))
add("coverage mutation: silent unchecked design facet must fail", rc == 1
    and any("design.reason" in e for e in data.get("errors", [])))
empty = result([])
empty_path = dump("empty-checked.json", empty)
rc, data = run("coverage", empty_path)
add("coverage positive: zero findings plus real checked scopes is valid", rc == 0 and data.get("ok"))

BASELINE_ISSUE = make_issue("B1", "fact", "p < 0.05", "The p-value alone proves clinical importance.",
                            "Adjudication fixture: statistical significance alone does not establish clinical importance.")
BASELINE = result([BASELINE_ISSUE])
BASELINE["runtime"] = {"elapsed_seconds": 160.0, "manual_review_seconds": 90.0, "rounds": 4}
SKILL = result([GOOD_ISSUE])
SKILL["runtime"] = {"elapsed_seconds": 100.0, "manual_review_seconds": 40.0, "rounds": 2}
DECISIONS = {
    "case_id": "bench-quality", "text_sha256": TEXT_SHA,
    "permissions": "same local files; no network for either arm",
    "allowed_sources": "same manuscript and supplied references only",
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
BAD_DECISIONS.pop("allowed_sources")
rc, data = run("compare", dump("baseline4.json", BASELINE), dump("skill4.json", SKILL),
               "--decisions", dump("missing-sources-decisions.json", BAD_DECISIONS))
add("compare mutation: undocumented shared source scope must fail", rc == 1
    and any("allowed_sources" in e for e in data.get("errors", [])))

passed = sum(condition for _, condition, _ in CHECKS)
for name, condition, detail in CHECKS:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition and detail else ""))
print("total %d/%d" % (passed, len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
