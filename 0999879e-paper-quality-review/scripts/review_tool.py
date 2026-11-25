#!/usr/bin/env python3
"""Source-bound paper review, Python standard library only.

Commands:
  index TEXT --out INDEX.json
      Stable page/line/paragraph/sentence/character locators and SHA-256 hashes.
  verify RESULT.json --source SOURCE_ID=TEXT [--source ...]
      Exact UTF-8 quote, offsets, sentence and hash verification; no fuzzy pass.
  citations TEXT --out CITATIONS.json
      Resolve numeric inline citations to bibliography entries and emit claim/source pairs.
  coverage RESULT.json
      Validate six explicit facet dispositions (issues are not evidence of coverage).
  compare BASELINE.json SKILL.json --decisions DECISIONS.json
      Same-input, adjudicated quality and measured efficiency comparison.
  schema RESULT.json
      Validate the machine-checkable delivery contract.

Exit 0 means the requested check passed; exit 1 means invalid/failed; exit 2 means usage/I/O error.
"""
import argparse
import bisect
import collections
import copy
import datetime
import hashlib
import json
import os
import re
import sys

TOOL_VERSION = "3.0.0"
RESULT_SCHEMA_VERSION = "2.0.0"
CATEGORIES = ("fact", "citation", "design", "statistics", "argument", "compliance")
SEVERITIES = ("critical", "major", "minor")
ISSUE_TYPES = ("fact_error", "insufficient_evidence", "normative_issue", "suggestion")
ISSUE_STATUSES = ("confirmed", "needs_review")
SCOPE_STATUSES = ("checked", "partial", "not_applicable", "not_checked")
FIX_ACTIONS = ("replace", "add", "remove", "clarify", "verify", "restrict")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ToolError(Exception):
    pass


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def read_text(path):
    # newline="" is intentional: character offsets must round-trip to the actual text file.
    with open(path, "r", encoding="utf-8", errors="strict", newline="") as handle:
        return handle.read()


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_text(text):
    return sha_bytes(text.encode("utf-8"))


def dump_json(path, value):
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def emit(value, out=None):
    dump_json(out, value)
    if not out:
        print(json.dumps(value, ensure_ascii=False))
    return 0 if value.get("ok", True) else 1


def line_starts(text):
    starts = [0]
    starts.extend(match.end() for match in re.finditer(r"\n", text))
    return starts


def section_intervals(text):
    headings = []
    pattern = re.compile(
        r"(?m)^\s*(?:#{1,6}\s+(?P<md>.+?)\s*#*\s*|"
        r"(?P<plain>摘要|Abstract|引言|Introduction|方法|Methods?|材料与方法|"
        r"结果|Results?|讨论|Discussion|结论|Conclusions?|参考文献|References?|"
        r"数据可用性|Data Availability|伦理|Ethics)\s*|"
        r"(?P<numbered>\d+(?:\.\d+)*\s+[^\n]{1,120}))$"
    )
    for match in pattern.finditer(text):
        title = next(value for value in match.groups() if value is not None).strip()
        headings.append((match.start(), title))
    return headings


def section_at(headings, position):
    titles = [title for start, title in headings if start <= position]
    return titles[-1] if titles else "front_matter"


def sentence_spans(text):
    """Conservative sentence segmentation; blank lines and terminal punctuation only.

    Single PDF newlines do not create fake sentence boundaries. Decimal points do not split.
    """
    boundary = re.compile(
        r"[。！？；!?;]+[\"'’”」』）\)]*|"
        r"(?<=[A-Za-z0-9\)])\.(?=\s+(?:[\"'“‘(\[]*[A-Z0-9]|$))|"
        r"(?m:^[ \t]*#{1,6}[^\r\n]+(?:\r?\n|$))|"
        r"(?m:^[ \t]*(?:摘要|Abstract|引言|Introduction|方法|Methods?|结果|Results?|讨论|Discussion|结论|Conclusions?|参考文献|References?)[ \t]*(?:\r?\n|$))|"
        r"(?:\r?\n){2,}"
    )
    spans = []
    start = 0
    for match in boundary.finditer(text):
        end = match.end()
        left = start
        while left < end and text[left].isspace():
            left += 1
        right = end
        while right > left and text[right - 1].isspace():
            right -= 1
        if right > left:
            spans.append((left, right))
        start = end
    left = start
    while left < len(text) and text[left].isspace():
        left += 1
    right = len(text)
    while right > left and text[right - 1].isspace():
        right -= 1
    if right > left:
        spans.append((left, right))
    return spans


def build_index(text, source_id="manuscript_text"):
    digest = sha_text(text)
    starts = line_starts(text)
    headings = section_intervals(text)
    paragraphs = [match for match in re.finditer(r"(?:\r?\n){2,}", text)]
    sentences = []
    for number, (start, end) in enumerate(sentence_spans(text), 1):
        line_start = bisect.bisect_right(starts, start)
        line_end = bisect.bisect_right(starts, max(start, end - 1))
        quote = text[start:end]
        sentences.append({
            "sentence_id": "s%05d" % number,
            "location": {
                "source_id": source_id,
                "source_sha256": digest,
                "page": text.count("\f", 0, start) + 1,
                "line_start": line_start,
                "line_end": line_end,
                "paragraph": bisect.bisect_right([m.start() for m in paragraphs], start) + 1,
                "section": section_at(headings, start),
                "sentence_id": "s%05d" % number,
                "char_start": start,
                "char_end": end,
            },
            "quote": quote,
            "quote_sha256": sha_text(quote),
        })
    return {
        "ok": True,
        "index_schema_version": RESULT_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source_id": source_id,
        "source_sha256": digest,
        "char_count": len(text),
        "byte_count": len(text.encode("utf-8")),
        "page_count": text.count("\f") + (1 if text or not text else 0),
        "coordinate_system": "Python Unicode code-point offsets; end-exclusive; lines/pages/paragraphs 1-based",
        "sentences": sentences,
    }


def locate(text, start, end, source_id="manuscript_text", index=None):
    idx = index or build_index(text, source_id)
    sentence_id = None
    for sentence in idx["sentences"]:
        loc = sentence["location"]
        if loc["char_start"] <= start < loc["char_end"]:
            sentence_id = loc["sentence_id"]
            break
    starts = line_starts(text)
    headings = section_intervals(text)
    paragraphs = [m.start() for m in re.finditer(r"(?:\r?\n){2,}", text)]
    return {
        "source_id": source_id,
        "source_sha256": sha_text(text),
        "page": text.count("\f", 0, start) + 1,
        "line_start": bisect.bisect_right(starts, start),
        "line_end": bisect.bisect_right(starts, max(start, end - 1)),
        "paragraph": bisect.bisect_right(paragraphs, start) + 1,
        "section": section_at(headings, start),
        "sentence_id": sentence_id,
        "char_start": start,
        "char_end": end,
    }


def span(text, start, end, role="primary", source_id="manuscript_text", index=None):
    quote = text[start:end]
    return {
        "role": role,
        "location": locate(text, start, end, source_id, index),
        "quote": quote,
        "quote_sha256": sha_text(quote),
    }


def cmd_index(args):
    text = read_text(args.text)
    result = build_index(text, args.source_id)
    return emit(result, args.out)


def parse_sources(pairs):
    sources = {}
    for pair in pairs:
        if "=" not in pair:
            raise ToolError("--source must be SOURCE_ID=TEXT: %s" % pair)
        source_id, path = pair.split("=", 1)
        if not source_id or source_id in sources:
            raise ToolError("empty or duplicate source_id: %s" % source_id)
        sources[source_id] = read_text(path)
    return sources


def issue_list(value):
    if isinstance(value, dict):
        return value.get("issues", [])
    return value


def verify_span(item, prefix, sources, indexes, errors):
    location = item.get("location") if isinstance(item, dict) else None
    quote = item.get("quote") if isinstance(item, dict) else None
    if not isinstance(location, dict) or not isinstance(quote, str) or not quote:
        errors.append({"path": prefix, "error": "missing_location_or_quote"})
        return
    source_id = location.get("source_id")
    if source_id not in sources:
        errors.append({"path": prefix, "error": "source_not_provided", "source_id": source_id})
        return
    text = sources[source_id]
    idx = indexes.get(source_id)
    if idx is None:
        idx = build_index(text, source_id)
        indexes[source_id] = idx
    start, end = location.get("char_start"), location.get("char_end")
    if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(text)):
        errors.append({"path": prefix, "error": "invalid_character_offsets"})
        return
    actual = text[start:end]
    if actual != quote:
        error = "quote_not_in_source" if quote not in text else "locator_or_quote_mismatch"
        errors.append({"path": prefix, "error": error, "actual_at_locator": actual[:120]})
        return
    if location.get("source_sha256") != sha_text(text):
        errors.append({"path": prefix, "error": "source_hash_mismatch"})
    if item.get("quote_sha256") != sha_text(quote):
        errors.append({"path": prefix, "error": "quote_hash_mismatch"})
    expected = locate(text, start, end, source_id, idx)
    for field in ("page", "line_start", "line_end", "paragraph", "section", "sentence_id"):
        if location.get(field) != expected[field]:
            errors.append({"path": prefix, "error": "location_%s_mismatch" % field,
                           "expected": expected[field], "actual": location.get(field)})


def cmd_verify(args):
    result = load_json(args.result)
    sources = parse_sources(args.source)
    if not sources:
        raise ToolError("verify requires at least one --source; silent skipping is forbidden")
    errors, indexes = [], {}
    issues = issue_list(result)
    if not isinstance(issues, list):
        raise ToolError("issues must be a list")
    seen = {}
    duplicates = []
    for number, issue in enumerate(issues):
        prefix = "issues[%d]" % number
        verify_span(issue, prefix, sources, indexes, errors)
        for epos, evidence in enumerate(issue.get("evidence", [])):
            verify_span(evidence, "%s.evidence[%d]" % (prefix, epos), sources, indexes, errors)
        loc = issue.get("location", {})
        key = (issue.get("category"), loc.get("source_id"), loc.get("char_start"),
               loc.get("char_end"), issue.get("quote"))
        if key in seen:
            duplicates.append({"a": seen[key], "b": issue.get("id")})
        else:
            seen[key] = issue.get("id")
    if isinstance(result, dict) and "manuscript_version" in result:
        version = result["manuscript_version"]
        source_id = version.get("source_id") if isinstance(version, dict) else None
        if source_id in sources and version.get("text_sha256") != sha_text(sources[source_id]):
            errors.append({"path": "manuscript_version", "error": "text_hash_mismatch"})
    return emit({
        "ok": not errors and not duplicates,
        "tool_version": TOOL_VERSION,
        "verification": "exact substring + exact offsets + source/quote SHA-256 + page/line/paragraph/sentence",
        "issues": len(issues),
        "sources_checked": sorted(sources),
        "errors": errors,
        "duplicates": duplicates,
    })


def expand_citation(body):
    numbers = []
    for part in re.split(r"[,，]", body):
        part = part.strip()
        match = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
        if match:
            first, last = map(int, match.groups())
            if last >= first and last - first <= 500:
                numbers.extend(range(first, last + 1))
        elif part.isdigit():
            numbers.append(int(part))
    return numbers


def cmd_citations(args):
    text = read_text(args.text)
    idx = build_index(text, args.source_id)
    heading = re.search(r"(?im)^\s*(?:#{1,6}\s*)?(参考文献|references|bibliography)\s*$", text)
    reference_start = heading.start() if heading else len(text)
    entry_pattern = re.compile(r"(?m)^\s*\[(\d+)\]\s+")
    entry_matches = [m for m in entry_pattern.finditer(text, reference_start)] if heading else []
    references = {}
    for pos, match in enumerate(entry_matches):
        end = entry_matches[pos + 1].start() if pos + 1 < len(entry_matches) else len(text)
        while end > match.start() and text[end - 1].isspace():
            end -= 1
        start = match.start()
        while start < end and text[start] in " \t\r\n":
            start += 1
        number = int(match.group(1))
        item = span(text, start, end, "bibliography", args.source_id, idx)
        item["reference_number"] = number
        references[number] = item
    inline = []
    unresolved = []
    cited = set()
    marker_pattern = re.compile(r"\[((?:\d+)(?:\s*[-–,，]\s*\d+)*)\]")
    for match in marker_pattern.finditer(text, 0, reference_start):
        numbers = expand_citation(match.group(1))
        if not numbers:
            continue
        marker = span(text, match.start(), match.end(), "inline_citation", args.source_id, idx)
        sentence = next((s for s in idx["sentences"]
                         if s["location"]["char_start"] <= match.start() < s["location"]["char_end"]), None)
        pair = {
            "citation_numbers": numbers,
            "marker": marker,
            "manuscript_claim": copy.deepcopy(sentence) if sentence else None,
            "reference_entries": [copy.deepcopy(references[n]) for n in numbers if n in references],
            "support": "not_checked",
            "support_reason": "A bibliography match does not establish semantic support; read the cited source.",
        }
        inline.append(pair)
        for number in numbers:
            cited.add(number)
            if heading and number not in references:
                unresolved.append({
                    "reference_number": number,
                    "status": "confirmed_missing_entry_in_supplied_bibliography",
                    "marker": marker,
                    "fix": {"action": "add", "target": marker["location"]["sentence_id"],
                            "instruction": "Add bibliography entry [%d] or correct the inline citation number." % number},
                })
    uncited = []
    for number, reference in sorted(references.items()):
        if number not in cited:
            uncited.append({"reference_number": number, "status": "needs_review",
                            "reason": "No numeric inline citation found; bibliography-only styles require manual review.",
                            "reference": reference})
    errors = []
    if not heading and list(marker_pattern.finditer(text)):
        errors.append("bibliography_heading_not_found; citation support and missing entries not_checked")
    result = {
        "ok": not unresolved and not errors,
        "tool_version": TOOL_VERSION,
        "source_id": args.source_id,
        "source_sha256": sha_text(text),
        "scope": "numeric bracket citations only; author-year and semantic support require source review",
        "status": "partial" if errors else ("issues" if unresolved else "checked"),
        "inline_citations": inline,
        "references": list(references.values()),
        "unresolved_citations": unresolved,
        "uncited_references": uncited,
        "errors": errors,
    }
    return emit(result, args.out)


def scope_errors(result):
    errors = []
    scope = result.get("checked_scope") if isinstance(result, dict) else None
    if not isinstance(scope, dict):
        return ["checked_scope must be an object"]
    for category in CATEGORIES:
        record = scope.get(category)
        if not isinstance(record, dict):
            errors.append("checked_scope.%s missing" % category)
            continue
        status = record.get("status")
        if status not in SCOPE_STATUSES:
            errors.append("checked_scope.%s.status invalid" % category)
        if status in ("partial", "not_applicable", "not_checked") and not str(record.get("reason", "")).strip():
            errors.append("checked_scope.%s.reason required for %s" % (category, status))
        if status == "checked" and not str(record.get("search_scope", "")).strip():
            errors.append("checked_scope.%s.search_scope required for checked" % category)
    if set(scope) - set(CATEGORIES):
        errors.append("unknown checked_scope categories: %s" % sorted(set(scope) - set(CATEGORIES)))
    return errors


def schema_errors(result):
    errors = []
    if not isinstance(result, dict):
        return ["top level must be an object"]
    required = ("result_schema_version", "tool_version", "case_id", "status", "manuscript_version",
                "issues", "checked_scope", "gain", "unchecked", "sources", "uncertainty", "change_log")
    for key in required:
        if key not in result:
            errors.append("missing top-level field %s" % key)
    if result.get("result_schema_version") != RESULT_SCHEMA_VERSION:
        errors.append("result_schema_version must be %s" % RESULT_SCHEMA_VERSION)
    if result.get("tool_version") != TOOL_VERSION:
        errors.append("tool_version must be %s" % TOOL_VERSION)
    if not str(result.get("case_id", "")).strip():
        errors.append("case_id empty")
    if result.get("status") not in ("pass", "issues", "partial", "failed"):
        errors.append("status invalid")
    version = result.get("manuscript_version")
    if not isinstance(version, dict):
        errors.append("manuscript_version must be an object")
    else:
        for key in ("file", "source_id", "file_sha256", "text_sha256", "extractor"):
            if not str(version.get(key, "")).strip():
                errors.append("manuscript_version.%s required" % key)
        for key in ("file_sha256", "text_sha256"):
            if not SHA256.fullmatch(str(version.get(key, ""))):
                errors.append("manuscript_version.%s must be lowercase SHA-256" % key)
    issues = result.get("issues")
    if not isinstance(issues, list):
        errors.append("issues must be a list")
        issues = []
    ids = set()
    for pos, issue in enumerate(issues):
        prefix = "issues[%d]" % pos
        if not isinstance(issue, dict):
            errors.append(prefix + " must be an object")
            continue
        for key in ("id", "category", "type", "severity", "status", "location", "quote",
                    "quote_sha256", "claim", "evidence", "basis", "fix"):
            if key not in issue:
                errors.append("%s missing %s" % (prefix, key))
        if issue.get("id") in ids:
            errors.append(prefix + " duplicate id")
        ids.add(issue.get("id"))
        if issue.get("category") not in CATEGORIES:
            errors.append(prefix + " category invalid")
        if issue.get("type") not in ISSUE_TYPES:
            errors.append(prefix + " type invalid")
        if issue.get("severity") not in SEVERITIES:
            errors.append(prefix + " severity invalid")
        if issue.get("status") not in ISSUE_STATUSES:
            errors.append(prefix + " status invalid")
        if not str(issue.get("claim", "")).strip():
            errors.append(prefix + " claim empty")
        location = issue.get("location")
        if not isinstance(location, dict):
            errors.append(prefix + " location must be an object")
        else:
            for key in ("source_id", "source_sha256", "page", "line_start", "line_end",
                        "paragraph", "section", "sentence_id", "char_start", "char_end"):
                if key not in location or location[key] in (None, ""):
                    errors.append("%s.location.%s required" % (prefix, key))
            if not SHA256.fullmatch(str(location.get("source_sha256", ""))):
                errors.append(prefix + " location.source_sha256 invalid")
            if not isinstance(location.get("char_start"), int) or not isinstance(location.get("char_end"), int) \
                    or location.get("char_start", -1) < 0 or location.get("char_end", -1) <= location.get("char_start", -1):
                errors.append(prefix + " character offsets invalid")
        quote = issue.get("quote")
        if not isinstance(quote, str) or not quote:
            errors.append(prefix + " quote empty")
        elif not SHA256.fullmatch(str(issue.get("quote_sha256", ""))) or issue.get("quote_sha256") != sha_text(quote):
            errors.append(prefix + " quote_sha256 does not hash the exact UTF-8 quote")
        evidence = issue.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(prefix + " evidence must contain at least one source span")
        else:
            primary_found = False
            for epos, item in enumerate(evidence):
                if not isinstance(item, dict):
                    errors.append("%s.evidence[%d] must be object" % (prefix, epos))
                    continue
                for key in ("role", "location", "quote", "quote_sha256"):
                    if key not in item:
                        errors.append("%s.evidence[%d] missing %s" % (prefix, epos, key))
                if item.get("quote") == quote and item.get("location") == location:
                    primary_found = True
            if not primary_found:
                errors.append(prefix + " evidence must repeat the primary span exactly")
        basis = issue.get("basis")
        if not isinstance(basis, list) or not basis:
            errors.append(prefix + " basis must contain at least one checkable rule/source")
        else:
            for bpos, item in enumerate(basis):
                if not isinstance(item, dict):
                    errors.append("%s.basis[%d] must be object" % (prefix, bpos))
                    continue
                for key in ("kind", "source", "locator", "statement"):
                    if not str(item.get(key, "")).strip():
                        errors.append("%s.basis[%d].%s required" % (prefix, bpos, key))
                if item.get("kind") == "guideline" and not str(item.get("version", "")).strip():
                    errors.append("%s.basis[%d].version required for guideline" % (prefix, bpos))
        if issue.get("detection") == "absence":
            absence = issue.get("absence_evidence")
            if not isinstance(absence, dict) or absence.get("searched") is not True:
                errors.append(prefix + " absence finding requires absence_evidence.searched=true")
            else:
                for key in ("search_scope", "source_sha256", "expected", "statement"):
                    if not str(absence.get(key, "")).strip():
                        errors.append("%s.absence_evidence.%s required" % (prefix, key))
        fix = issue.get("fix")
        if not isinstance(fix, dict):
            errors.append(prefix + " fix must be an object")
        else:
            if fix.get("action") not in FIX_ACTIONS:
                errors.append(prefix + " fix.action invalid")
            for key in ("target", "instruction"):
                value = str(fix.get(key, "")).strip()
                if len(value) < 2:
                    errors.append("%s.fix.%s required" % (prefix, key))
                if value in ("注意", "建议检查", "请修改", "有待完善"):
                    errors.append("%s.fix.%s is not executable" % (prefix, key))
    errors.extend(scope_errors(result))
    if result.get("status") == "partial" and not result.get("unchecked"):
        errors.append("partial result must explain unchecked items")
    for key in ("unchecked", "sources", "uncertainty", "change_log"):
        if not isinstance(result.get(key), list):
            errors.append(key + " must be a list")
    for pos, source in enumerate(result.get("sources", []) if isinstance(result.get("sources"), list) else []):
        if not isinstance(source, dict):
            errors.append("sources[%d] must be an object" % pos)
            continue
        for key in ("source_id", "path_or_url", "role"):
            if not str(source.get(key, "")).strip():
                errors.append("sources[%d].%s required" % (pos, key))
        if source.get("sha256") is not None and not SHA256.fullmatch(str(source.get("sha256"))):
            errors.append("sources[%d].sha256 invalid" % pos)
    gain = result.get("gain")
    if not isinstance(gain, dict) or gain.get("status") not in ("not_measured", "measured"):
        errors.append("gain.status must be not_measured or measured")
    elif gain.get("status") == "not_measured":
        if not str(gain.get("reason", "")).strip():
            errors.append("gain.reason required when not_measured")
    else:
        for key in ("protocol", "quality", "efficiency"):
            if not isinstance(gain.get(key), dict):
                errors.append("gain.%s required for measured comparison" % key)
    return errors


def cmd_schema(args):
    result = load_json(args.result)
    errors = schema_errors(result)
    return emit({"ok": not errors, "result_schema_version": RESULT_SCHEMA_VERSION,
                 "tool_version": TOOL_VERSION, "errors": errors,
                 "issues": len(result.get("issues", [])) if isinstance(result, dict) else 0})


def cmd_coverage(args):
    result = load_json(args.result)
    errors = scope_errors(result)
    counts = collections.Counter()
    if isinstance(result, dict) and isinstance(result.get("checked_scope"), dict):
        for record in result["checked_scope"].values():
            if isinstance(record, dict):
                counts[record.get("status")] += 1
    return emit({"ok": not errors, "categories": list(CATEGORIES), "status_counts": dict(counts),
                 "errors": errors,
                 "rule": "zero issues never implies checked; every facet needs a disposition and scope/reason"})


def precision(decisions):
    supported = sum(value == "supported" for value in decisions.values())
    unsupported = sum(value == "unsupported" for value in decisions.values())
    unresolved = sum(value == "unresolved" for value in decisions.values())
    decided = supported + unsupported
    return {
        "issues": len(decisions), "supported": supported, "unsupported": unsupported,
        "unresolved": unresolved,
        "precision_decided": round(supported / decided, 6) if decided else None,
        "false_positive_rate_decided": round(unsupported / decided, 6) if decided else None,
    }


def cmd_compare(args):
    baseline, skill = load_json(args.baseline), load_json(args.skill)
    adjudication = load_json(args.decisions)
    errors = []
    if baseline.get("case_id") != skill.get("case_id"):
        errors.append("case_id differs")
    bv, sv = baseline.get("manuscript_version", {}), skill.get("manuscript_version", {})
    if bv.get("text_sha256") != sv.get("text_sha256"):
        errors.append("manuscript text SHA-256 differs")
    if adjudication.get("case_id") != skill.get("case_id") or adjudication.get("text_sha256") != sv.get("text_sha256"):
        errors.append("adjudication does not bind to the same case and text")
    for key in ("permissions", "allowed_sources", "budget"):
        if not str(adjudication.get(key, "")).strip():
            errors.append("adjudication.%s must explicitly document the shared condition" % key)
    arms = {}
    for name, result in (("baseline", baseline), ("skill", skill)):
        ids = [issue.get("id") for issue in result.get("issues", [])]
        decisions = adjudication.get(name)
        if not isinstance(decisions, dict):
            errors.append("adjudication.%s missing" % name)
            decisions = {}
        if set(ids) != set(decisions):
            errors.append("%s issue IDs and adjudication IDs differ" % name)
        bad = {key: value for key, value in decisions.items()
               if value not in ("supported", "unsupported", "unresolved")}
        if bad:
            errors.append("%s has invalid adjudication labels" % name)
        runtime = result.get("runtime")
        if not isinstance(runtime, dict):
            errors.append("%s.runtime required" % name)
            runtime = {}
        for key in ("elapsed_seconds", "manual_review_seconds", "rounds"):
            if not isinstance(runtime.get(key), (int, float)) or runtime.get(key) < 0:
                errors.append("%s.runtime.%s must be a non-negative number" % (name, key))
        arms[name] = {"result": result, "decisions": decisions, "runtime": runtime}
    if errors:
        return emit({"ok": False, "errors": errors})
    bp, sp = precision(arms["baseline"]["decisions"]), precision(arms["skill"]["decisions"])
    br, sr = arms["baseline"]["runtime"], arms["skill"]["runtime"]
    delta = lambda key: None if bp[key] is None or sp[key] is None else round(sp[key] - bp[key], 6)
    gain = {
        "ok": True,
        "status": "measured",
        "tool_version": TOOL_VERSION,
        "protocol": {
            "design": "same case_id, same manuscript text SHA-256, independent per-issue adjudication, recorded runtime",
            "case_id": skill.get("case_id"), "text_sha256": sv.get("text_sha256"),
            "adjudication_sha256": sha_bytes(read_bytes(args.decisions)),
            "permissions": adjudication["permissions"],
            "allowed_sources": adjudication["allowed_sources"],
            "budget": adjudication["budget"],
        },
        "quality": {
            "baseline": bp, "skill": sp,
            "delta_precision_decided": delta("precision_decided"),
            "delta_false_positive_rate_decided": delta("false_positive_rate_decided"),
            "unresolved_excluded_from_precision_and_reported_separately": True,
        },
        "efficiency": {
            "baseline": br, "skill": sr,
            "elapsed_seconds_saved": round(br["elapsed_seconds"] - sr["elapsed_seconds"], 6),
            "manual_review_seconds_saved": round(br["manual_review_seconds"] - sr["manual_review_seconds"], 6),
            "rounds_saved": round(br["rounds"] - sr["rounds"], 6),
        },
    }
    return emit(gain, args.out)


def parser():
    root = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("index")
    p.add_argument("text")
    p.add_argument("--source-id", default="manuscript_text")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_index)
    p = sub.add_parser("verify")
    p.add_argument("result")
    p.add_argument("--source", action="append", default=[])
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("citations")
    p.add_argument("text")
    p.add_argument("--source-id", default="manuscript_text")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_citations)
    for name, func in (("coverage", cmd_coverage), ("schema", cmd_schema)):
        p = sub.add_parser(name)
        p.add_argument("result")
        p.set_defaults(func=func)
    p = sub.add_parser("compare")
    p.add_argument("baseline")
    p.add_argument("skill")
    p.add_argument("--decisions", required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_compare)
    return root


def main():
    args = parser().parse_args()
    try:
        return args.func(args)
    except (OSError, UnicodeError, json.JSONDecodeError, ToolError, KeyError, TypeError, re.error) as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
