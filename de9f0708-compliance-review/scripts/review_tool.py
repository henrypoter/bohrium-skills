#!/usr/bin/env python3
"""Source-bound academic compliance review, Python standard library only.

Commands:
  index TEXT --out INDEX.json                 Stable sentence locators and hashes.
  verify RESULT.json --source ID=TEXT [...]  Exact quote/offset/hash verification.
  citations TEXT --out OUT.json              Numeric citation/reference resolution.
  privacy TEXT --out OUT.json                Direct identifiers and restricted-data candidates.
  license TEXT --out OUT.json                Third-party asset source/license/ND checks.
  guidelines GUIDE.json TEXT --out OUT.json  Versioned journal-rule evaluation; no invented rules.
  coverage RESULT.json                        Six explicit compliance facet dispositions.
  compare BASELINE.json SKILL.json --decisions D.json
                                              Same-input adjudicated quality/efficiency gain.
  schema RESULT.json                          Machine-checkable delivery contract.

Exit 0 means the requested check ran/passed; exit 1 means invalid/failed; exit 2 means usage/I/O error.
Domain scanners return ok=true with status=issues when review candidates exist.
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
CATEGORIES = ("integrity", "citation", "privacy", "copyright", "ethics", "submission")
SEVERITIES = ("critical", "major", "minor")
ISSUE_TYPES = ("fact_error", "insufficient_evidence", "normative_issue", "suggestion")
ISSUE_STATUSES = ("confirmed", "needs_review")
SCOPE_STATUSES = ("checked", "partial", "not_applicable", "not_checked")
FIX_ACTIONS = ("replace", "add", "remove", "clarify", "verify", "restrict", "deidentify", "obtain_permission")
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


def compliance_candidate(text, start, end, idx, source_id, identifier, category, rule_id,
                         claim, instruction, action="restrict", severity="major", detection="presence"):
    primary = span(text, start, end, "primary", source_id, idx)
    return {
        "id": identifier,
        "category": category,
        "type": "normative_issue",
        "severity": severity,
        "status": "needs_review",
        "detection": detection,
        "compliance_status": "not_established_from_supplied_material",
        "location": copy.deepcopy(primary["location"]),
        "quote": primary["quote"],
        "quote_sha256": primary["quote_sha256"],
        "claim": claim,
        "evidence": [primary],
        "basis": [{"kind": "deterministic_rule", "source": "scripts/review_tool.py",
                   "locator": rule_id, "statement": claim}],
        "fix": {"action": action, "target": primary["location"]["sentence_id"], "instruction": instruction},
        "handling": "restricted evidence; keep in controlled output and do not send to external services",
    }


def valid_prc_id(value):
    if not re.fullmatch(r"\d{17}[0-9Xx]", value):
        return False
    try:
        datetime.datetime.strptime(value[6:14], "%Y%m%d")
    except ValueError:
        return False
    weights = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    codes = "10X98765432"
    expected = codes[sum(int(a) * b for a, b in zip(value[:17], weights)) % 11]
    return value[-1].upper() == expected


def cmd_privacy(args):
    text = read_text(args.text)
    idx = build_index(text, args.source_id)
    candidates = []

    def add_matches(pattern, kind, instruction, flags=0, group=0, action="deidentify", validator=None):
        for match in re.finditer(pattern, text, flags):
            value = match.group(group)
            if validator and not validator(value):
                continue
            if kind == "email" and re.search(r"(?:corresponding\s+author|通讯作者|correspondence)\s*[:：]?\s*$",
                                               text[max(0, match.start() - 100):match.start()], re.I):
                continue
            start, end = match.start(group), match.end(group)
            candidates.append(compliance_candidate(
                text, start, end, idx, args.source_id, "PRIV-%03d" % (len(candidates) + 1),
                "privacy", "privacy." + kind,
                "Potential %s is present; supplied text alone does not establish authorization or lawful basis." % kind,
                instruction, action=action))

    add_matches(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])",
                "email", "Replace the address with a role-based contact or remove it unless public-contact authorization is documented.")
    add_matches(r"(?<!\d)1[3-9]\d{9}(?!\d)", "mainland_mobile",
                "Replace the mobile number with a controlled contact alias and remove it from public manuscripts/data.")
    add_matches(r"(?<!\d)(\d{17}[0-9Xx])(?!\d)", "prc_resident_id",
                "Remove the resident ID and use a random study subject code; store any linkage file separately with access controls.",
                group=1, validator=valid_prc_id)
    add_matches(r"(?:患者姓名|受试者姓名|联系人姓名|姓名)[ \t]*[:：][ \t]*([\u4e00-\u9fff·]{2,4}|[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+)",
                "labeled_name", "Replace the direct name with a random study subject code and remove the name from shared outputs.", group=1)
    add_matches(r"(?:住址|家庭住址|通讯地址|详细地址)[ \t]*[:：][ \t]*([^\n，。；;]{4,120})",
                "labeled_address", "Generalize the address to the approved minimum geographic level or remove it.", group=1)
    add_matches(r"(?:住院号|病历号|门诊号|身份证件号)[ \t]*[:：][ \t]*([A-Za-z0-9-]{4,32})",
                "institutional_record_id", "Replace the institutional record identifier with an irreversible study code.", group=1)
    add_matches(r"(?:未公开数据(?:集)?|受限数据(?:集)?|保密数据(?:集)?|内部数据(?:集)?)",
                "restricted_dataset", "Identify the data owner and permitted use; restrict redistribution and add an access/authorization statement.",
                action="restrict")
    # Deduplicate overlapping patterns while keeping distinct identifier types visible.
    unique = {}
    for item in candidates:
        key = (item["location"]["char_start"], item["location"]["char_end"], item["basis"][0]["locator"])
        unique[key] = item
    candidates = list(unique.values())
    for number, item in enumerate(candidates, 1):
        item["id"] = "PRIV-%03d" % number
    safeguards = []
    for match in re.finditer(r"知情同意|伦理(?:委员会|审批|批件)|\bIRB\b|授权|许可|脱敏|匿名化|去标识化", text, re.I):
        safeguards.append(span(text, match.start(), match.end(), "possible_safeguard", args.source_id, idx))
    result = {
        "ok": True,
        "tool_version": TOOL_VERSION,
        "status": "issues" if candidates else "checked",
        "source_id": args.source_id,
        "source_sha256": sha_text(text),
        "scope": "deterministic direct identifiers and explicit restricted-data markers; unnamed identities/quasi-identifiers require human review",
        "findings": candidates,
        "possible_safeguards": safeguards,
        "authorization_rule": "Safeguard keywords are leads only; authorization is not_established until a source-linked permission/ethics record is reviewed.",
        "unchecked": ["Unlabeled names, voices, faces, genomic data and quasi-identifier combinations not resolvable by these patterns"],
    }
    return emit(result, args.out)


def cmd_license(args):
    text = read_text(args.text)
    idx = build_index(text, args.source_id)
    findings, passed = [], []
    asset_re = re.compile(r"(?:^|\s)(?:图\s*\d+|表\s*\d+|Figure\s*\d+|Fig\.\s*\d+|Table\s*\d+|代码|code|数据集|dataset)", re.I)
    third_re = re.compile(r"转载自|改编自|来源于|源于|第三方|reproduced\s+from|adapted\s+from|source\s*:|third[- ]party", re.I)
    license_re = re.compile(r"CC\s*(?:0|BY(?:-NC|-ND|-SA){0,2})(?:\s*\d\.\d)?|Creative\s+Commons|Public\s+Domain|MIT\s+License|GPL|BSD|Apache\s+License|授权许可|许可协议|已获授权|permission\s+granted", re.I)
    adapted_re = re.compile(r"改编自|adapted\s+from|modified\s+from", re.I)
    nd_re = re.compile(r"CC\s*BY(?:-NC)?-ND|CC\s*BY-ND(?:-NC)?", re.I)
    blocks = list(re.finditer(r"\S(?:.*?\S)?(?=(?:\r?\n){2,}|\Z)", text, re.S))
    for block in blocks:
        value = block.group(0)
        if not asset_re.search(value) or not third_re.search(value):
            continue
        license_match = license_re.search(value)
        if not license_match:
            findings.append(compliance_candidate(
                text, block.start(), block.end(), idx, args.source_id,
                "LIC-%03d" % (len(findings) + 1), "copyright", "copyright.third_party_license_unstated",
                "Third-party asset reuse is stated but no reusable license or separate permission is identifiable in this block.",
                "Add creator/title/source and the exact license or permission record; if permission cannot be documented, replace the asset with an original or openly licensed alternative.",
                action="obtain_permission"))
        elif nd_re.search(value) and adapted_re.search(value):
            findings.append(compliance_candidate(
                text, block.start(), block.end(), idx, args.source_id,
                "LIC-%03d" % (len(findings) + 1), "copyright", "copyright.nd_adaptation_conflict",
                "An adaptation is paired with an ND license; redistribution may require separate permission.",
                "Obtain separate written adaptation/redistribution permission or replace the adapted asset; do not treat the ND label alone as permission.",
                action="obtain_permission"))
        else:
            passed.append(span(text, block.start(), block.end(), "licensed_asset", args.source_id, idx))
    return emit({
        "ok": True, "tool_version": TOOL_VERSION, "status": "issues" if findings else "checked",
        "source_id": args.source_id, "source_sha256": sha_text(text),
        "scope": "explicit third-party figure/table/code/dataset statements; silent uncredited reuse requires image/code provenance review",
        "findings": findings, "passed_assets": passed,
        "unchecked": ["Pixel-level image duplication and code similarity are not inferred from text"],
    }, args.out)


def first_anchor(text, idx, source_id):
    if not idx["sentences"]:
        raise ToolError("cannot anchor absence in an empty text")
    sentence = idx["sentences"][0]
    start, end = sentence["location"]["char_start"], sentence["location"]["char_end"]
    return span(text, start, end, "document_anchor", source_id, idx)


def section_scope(text, pattern):
    heading = re.search(r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:" + pattern + r")[^\r\n]*$", text)
    if not heading:
        return None
    content_start = heading.end()
    if content_start < len(text) and text[content_start] == "\r":
        content_start += 1
    if content_start < len(text) and text[content_start] == "\n":
        content_start += 1
    next_heading = re.search(r"(?im)^[ \t]*(?:#{1,6}[ \t]+|(?:摘要|Abstract|引言|Introduction|方法|Methods?|结果|Results?|讨论|Discussion|结论|Conclusions?|参考文献|References?)[ \t]*$)", text[content_start:])
    end = content_start + next_heading.start() if next_heading else len(text)
    return heading, content_start, end


def word_count(text):
    english = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text)
    han = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text)
    return len(english) + len(han)


def cmd_guidelines(args):
    guide = load_json(args.guide)
    text = read_text(args.text)
    idx = build_index(text, args.source_id)
    for key in ("guide_version", "guide_date", "source", "rules"):
        if key not in guide or guide[key] in (None, "", []):
            raise ToolError("guide metadata/rules required: " + key)
    if not isinstance(guide["rules"], list):
        raise ToolError("guide.rules must be a list")
    results = []
    for pos, rule in enumerate(guide["rules"]):
        for key in ("id", "kind", "description"):
            if not str(rule.get(key, "")).strip():
                raise ToolError("rules[%d].%s required" % (pos, key))
        rid, kind = rule["id"], rule["kind"]
        anchor = None
        passed, actual, limit = False, None, None
        absence = None
        scope_label = "full manuscript"
        if kind == "required_pattern":
            pattern = rule.get("pattern")
            if not pattern:
                raise ToolError(rid + ".pattern required")
            start, end = 0, len(text)
            if rule.get("section"):
                section = section_scope(text, rule["section"])
                if section:
                    heading, start, end = section
                    anchor = span(text, heading.start(), heading.end(), "section_anchor", args.source_id, idx)
                    scope_label = heading.group(0).strip()
            match = re.search(pattern, text[start:end], re.I)
            passed = bool(match)
            if match:
                anchor = span(text, start + match.start(), start + match.end(), "requirement_evidence", args.source_id, idx)
            actual = "present" if passed else "absent"
        elif kind == "required_section":
            if not rule.get("pattern"):
                raise ToolError(rid + ".pattern required")
            section = section_scope(text, rule["pattern"])
            passed = section is not None
            if section:
                heading = section[0]
                anchor = span(text, heading.start(), heading.end(), "section_anchor", args.source_id, idx)
            actual = "present" if passed else "absent"
        elif kind == "max_words":
            if not rule.get("section") or not isinstance(rule.get("limit"), int) or rule["limit"] < 0:
                raise ToolError(rid + " requires section and non-negative integer limit")
            section = section_scope(text, rule["section"])
            limit = rule["limit"]
            if section:
                heading, start, end = section
                anchor = span(text, heading.start(), heading.end(), "section_anchor", args.source_id, idx)
                actual = word_count(text[start:end])
                passed = actual <= limit
                scope_label = heading.group(0).strip()
            else:
                actual = "section_absent"
                passed = False
        elif kind == "max_pages":
            if not isinstance(rule.get("limit"), int) or rule["limit"] < 1:
                raise ToolError(rid + " requires positive integer limit")
            actual = text.count("\f") + 1
            limit = rule["limit"]
            passed = actual <= limit
        else:
            raise ToolError("unsupported guideline rule kind: " + kind)
        if anchor is None:
            anchor = first_anchor(text, idx, args.source_id)
        basis = {"kind": "guideline", "source": guide["source"], "locator": rid,
                 "statement": rule["description"], "version": guide["guide_version"], "date": guide["guide_date"]}
        if passed:
            results.append({"rule_id": rid, "status": "pass", "actual": actual, "limit": limit,
                            "evidence": anchor, "basis": basis, "counting_method": "Unicode Han characters + English/number tokens" if kind == "max_words" else None})
            continue
        absence = {"searched": True, "search_scope": scope_label, "source_sha256": sha_text(text),
                   "expected": rule.get("pattern", rule.get("section", kind)),
                   "statement": "Absence/failure was evaluated against the stated scope; the anchor is a locator, not fabricated missing text."}
        candidate = compliance_candidate(
            text, anchor["location"]["char_start"], anchor["location"]["char_end"], idx, args.source_id,
            "GUIDE-%03d" % (pos + 1), "submission", "guideline." + rid,
            "Guideline rule %s failed: actual=%s, limit=%s." % (rid, actual, limit),
            "Edit the mapped manuscript section to satisfy rule %s, then rerun this command against the same guide version." % rid,
            action="add" if actual in ("absent", "section_absent") else "replace",
            detection="absence" if actual in ("absent", "section_absent") else "limit")
        candidate["basis"] = [basis]
        candidate["absence_evidence"] = absence
        candidate["actual"] = actual
        candidate["limit"] = limit
        results.append({"rule_id": rid, "status": "issue", "actual": actual, "limit": limit,
                        "finding": candidate, "basis": basis})
    findings = [item["finding"] for item in results if item["status"] == "issue"]
    return emit({
        "ok": True, "tool_version": TOOL_VERSION, "status": "issues" if findings else "pass",
        "guide": {"version": guide["guide_version"], "date": guide["guide_date"], "source": guide["source"]},
        "source_id": args.source_id, "source_sha256": sha_text(text),
        "counting_method": "max_words = Unicode Han characters + English/number tokens; max_pages = form-feed pages",
        "rules": results, "findings": findings,
    }, args.out)


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
                if item.get("kind") == "guideline" and not str(item.get("date", "")).strip():
                    errors.append("%s.basis[%d].date required for guideline" % (prefix, bpos))
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
    for name, func in (("privacy", cmd_privacy), ("license", cmd_license)):
        p = sub.add_parser(name)
        p.add_argument("text")
        p.add_argument("--source-id", default="manuscript_text")
        p.add_argument("--out", required=True)
        p.set_defaults(func=func)
    p = sub.add_parser("guidelines")
    p.add_argument("guide")
    p.add_argument("text")
    p.add_argument("--source-id", default="manuscript_text")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_guidelines)
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
