#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""科研成果转化写作的可复核机检（仅 Python 3 标准库）。

命令：
  evidence <project.json> [report.json]
      逐字回查 quote、核对 source/line、检查冲突组与术语/保留项 schema。
  audit <draft.md> <project.json> <brief.json> [report.json]
      检查保留项、数值+单位+来源、图表、术语/缩写、论断强度、受众/体裁/
      篇幅、逐段改动记录以及涉密/未发表处置。
  result <result.json> <case.json> [report.json]
      检查 output_contract 全字段、交付文件、验证报告与诚实 gain 对照。

退出码：0=无 fail；1=有 fail；2=参数/读入错误。
所有路径相对 JSON 所在目录解析；不会联网，也不会修改输入稿件。
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

TAG = re.compile(r"\[([A-Za-z]{1,8}\d+(?:\s*[,，]\s*[A-Za-z]{1,8}\d+)*)\]")
NUM = re.compile(r"(?<![A-Za-z0-9_])(?:\d+(?:\.\d+)?|\.\d+)(?:\s*(?:%|‰|个百分点|倍|例|人|名|个|种|年|月|天|小时|分钟|秒|mg|g|kg|μg|ml|mL|L|μM|mM|M|mm|cm|m|km|MPa|kPa|Pa|Hz|kHz|MHz|°C|K|h|min|s))?", re.I)
FIG = re.compile(r"(?:图|表)\s*S?\d+[A-Za-z]?|(?:Fig(?:ure)?|Table)\.?\s*S?\d+[A-Za-z]?", re.I)
ACR = re.compile(r"(?<![A-Za-z])[A-Z][A-Z0-9]{1,9}(?![A-Za-z])")
STRONG = ["证明", "证实", "定论", "必然", "确立因果", "prove", "demonstrate", "conclusive"]
CAUSAL = ["导致", "造成", "使得", "因果", "治愈", "caus", "cure"]
HEDGE = ["初步", "可能", "提示", "尚", "有待", "需进一步", "不能", "未", "相关", "观察",
         "preliminary", "may", "might", "suggest", "associat", "observ", "uncertain"]
NEG = ["不显著", "未达显著", "未达到显著", "无显著", "未见显著", "不能推断因果",
       "无法推断因果", "非因果", "not significant", "no significant", "not causal"]
ALLOWED_STATUS = {"complete", "partial", "failed"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def emit(report, path=None):
    items = report.setdefault("items", [])
    report["summary"] = {
        "fail": sum(x["level"] == "fail" for x in items),
        "warn": sum(x["level"] == "warn" for x in items),
        "by_kind": {k: sum(x["kind"] == k for x in items)
                    for k in sorted({x["kind"] for x in items})},
    }
    report["ok"] = report["summary"]["fail"] == 0
    blob = json.dumps(report, ensure_ascii=False, indent=1)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(blob + "\n", encoding="utf-8")
    print(blob)
    return 0 if report["ok"] else 1


def issue(report, level, kind, msg, **kw):
    report["items"].append({"level": level, "kind": kind, "msg": msg, **kw})


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def source_path(name, base):
    p = Path(str(name or ""))
    candidates = [p] if p.is_absolute() else [base / p, Path("/input") / p, Path.cwd() / p]
    return next((x.resolve() for x in candidates if x.is_file()), None)


def lines_of(text):
    return text.splitlines()


def locate_quote(text, quote):
    """返回规范空白后逐字命中的原始行号（含多行 quote 的起始行）。"""
    if not quote:
        return []
    if quote in text:
        start = text.index(quote)
        return [text.count("\n", 0, start) + 1]
    # 仅容忍空白排版差异，不容忍字词、数字或标点差异。
    q = norm(quote)
    if not q:
        return []
    lines = lines_of(text)
    for i in range(len(lines)):
        acc = ""
        for j in range(i, min(len(lines), i + 30)):
            acc += lines[j]
            if norm(acc) == q:
                return [i + 1]
            if len(norm(acc)) > len(q):
                break
    # 对单行内部引文精确定位。
    return [i + 1 for i, ln in enumerate(lines) if q in norm(ln)]


def ids_in(text):
    out = []
    for m in TAG.finditer(text):
        out.extend(re.split(r"\s*[,，]\s*", m.group(1)))
    return out


def sentences(text):
    for ln, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        # 分号连接的同一句可共用一个句末来源标注；只按完整句结束符切分。
        # 兼容“句。[S1]”与“句[S1]。”两种写法：标签不单独成句。
        parts = re.split(r"(?<=[。！？!?])", line)
        merged = []
        for part in parts:
            if merged and re.fullmatch(r"\s*(?:\[[A-Za-z]{1,8}\d+(?:\s*[,，]\s*[A-Za-z]{1,8}\d+)*\]\s*)+", part):
                merged[-1] += part
            else:
                merged.append(part)
        for s in merged:
            if s.strip():
                yield ln, s.strip()


def paragraphs(text):
    buf, start = [], None
    for n, line in enumerate(text.splitlines() + [""], 1):
        if line.strip() and not line.lstrip().startswith("#"):
            if start is None:
                start = n
            buf.append(line.strip())
        elif buf:
            yield start, "\n".join(buf)
            buf, start = [], None


def project_index(project):
    return {str(x.get("id")): x for x in project.get("items", [])}


def cmd_evidence(project_path, report_path=None):
    report = {"command": "evidence", "project": str(project_path), "items": []}
    project = load(project_path)
    base = Path(project_path).resolve().parent
    items = project.get("items")
    if not isinstance(items, list) or not items:
        issue(report, "fail", "schema", "items 必须是非空数组")
        items = []
    seen, cache = set(), {}
    for i, item in enumerate(items):
        iid = str(item.get("id") or "")
        loc = {"item": iid or str(i)}
        if not re.fullmatch(r"[A-Za-z]{1,8}\d+", iid):
            issue(report, "fail", "schema", "id 须为字母+数字，如 S1", **loc)
        if iid in seen:
            issue(report, "fail", "schema", "重复证据 id", **loc)
        seen.add(iid)
        for key in ("quote", "source", "kind", "strength"):
            if not item.get(key):
                issue(report, "fail", "schema", "缺字段 %s" % key, **loc)
        if item.get("line") is None and not item.get("field"):
            issue(report, "fail", "locator", "缺 line 或 field 定位", **loc)
        src = source_path(item.get("source"), base)
        if not src:
            issue(report, "fail", "source", "来源文件不存在: %s" % item.get("source"), **loc)
            continue
        if src not in cache:
            try:
                cache[src] = src.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as e:
                issue(report, "fail", "source", "来源不是可读 UTF-8 文本: %s" % e, **loc)
                continue
        text = cache[src]
        found = locate_quote(text, item.get("quote", ""))
        item["resolved_source"] = str(src)
        item["actual_lines"] = found
        if not found:
            issue(report, "fail", "verbatim", "quote 未在来源逐字命中", **loc)
        elif item.get("line") is not None:
            try:
                declared = int(item["line"])
                if declared not in found and not (found[0] <= declared < found[0] + item["quote"].count("\n") + 1):
                    issue(report, "fail", "locator", "声明 line=%s，实际起始行=%s" % (declared, found), **loc)
            except (TypeError, ValueError):
                issue(report, "fail", "locator", "line 不是整数", **loc)
        if item.get("field"):
            # JSON 字段定位：字段值本身也必须包含 quote。
            try:
                obj = json.loads(text)
                cur = obj
                for part in re.split(r"[./]", str(item["field"])):
                    if part == "":
                        continue
                    cur = cur[int(part)] if isinstance(cur, list) else cur[part]
                if norm(item["quote"]) not in norm(cur):
                    issue(report, "fail", "locator", "field 值不含 quote", **loc)
            except (ValueError, KeyError, IndexError, TypeError) as e:
                issue(report, "fail", "locator", "field 无法解析: %s" % e, **loc)
        if item.get("kind") == "number" and not item.get("surfaces"):
            issue(report, "fail", "schema", "数值证据缺 surfaces（值+单位的原文表面形式）", **loc)
        for surface in item.get("surfaces", []):
            if norm(surface) not in norm(item.get("quote")):
                issue(report, "fail", "surface", "surface 不是 quote 的逐字片段: %s" % surface, **loc)
    groups = {}
    for item in items:
        if item.get("conflict_group"):
            groups.setdefault(item["conflict_group"], []).append(item)
    resolutions = {x.get("group"): x for x in project.get("resolutions", [])}
    for group, vals in groups.items():
        signatures = {norm(v.get("quote")) for v in vals}
        if len(signatures) > 1:
            r = resolutions.get(group)
            chosen = r and r.get("chosen")
            if not r or r.get("status") != "human_confirmed" or chosen not in {v.get("id") for v in vals}:
                issue(report, "fail", "conflict", "冲突组 %s 未由人工确认 chosen" % group, group=group)
    terms = project.get("terms", [])
    for i, term in enumerate(terms):
        if not term.get("canonical"):
            issue(report, "fail", "terminology", "terms[%d] 缺 canonical" % i)
        abbr = term.get("abbreviation")
        if abbr and not term.get("expanded"):
            issue(report, "fail", "terminology", "%s 有缩写但缺 expanded" % term.get("canonical"))
    report["evidence"] = items
    return emit(report, report_path)


def numeric_missing(sentence, cited, index):
    clean = TAG.sub(" ", sentence)
    clean = FIG.sub(" ", clean)
    clean = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", clean)
    missing = []
    cited_surfaces = "".join("".join(index[x].get("surfaces", [])) + index[x].get("quote", "")
                             for x in cited if x in index)
    for m in NUM.finditer(clean):
        token = m.group(0).strip()
        # 去掉来源编号、图表编号后剩余的科学数字必须逐字来自被引证据。
        if norm(token) not in norm(cited_surfaces):
            missing.append(token)
    return missing


def check_strength(report, ln, sentence, cited, index):
    scan = sentence
    for neg in NEG:
        scan = scan.replace(neg, "")
    for iid in cited:
        item = index.get(iid, {})
        strength = item.get("strength")
        if strength in {"association", "observational"} and any(x.lower() in scan.lower() for x in CAUSAL):
            issue(report, "fail", "claim_strength", "相关/观察证据被写成因果", loc=ln, item=iid)
        if strength in {"preliminary", "association", "observational", "uncertain"}:
            if any(x.lower() in scan.lower() for x in STRONG):
                issue(report, "fail", "claim_strength", "初步/相关证据被写成定论", loc=ln, item=iid)
            elif not any(x.lower() in sentence.lower() for x in HEDGE):
                issue(report, "fail", "claim_strength", "初步/相关证据句缺边界词", loc=ln, item=iid)
        if strength == "not_significant" and "显著" in scan:
            issue(report, "fail", "claim_strength", "不显著证据被写成显著", loc=ln, item=iid)


def cmd_audit(draft_path, project_path, brief_path, report_path=None):
    report = {"command": "audit", "draft": str(draft_path), "items": []}
    draft = Path(draft_path).read_text(encoding="utf-8")
    project, brief = load(project_path), load(brief_path)
    index = project_index(project)
    used = set(ids_in(draft))
    for iid in sorted(used - set(index)):
        issue(report, "fail", "dangling_source", "正文来源标注不存在: %s" % iid)
    for item in project.get("items", []):
        if item.get("required") and item.get("id") not in used:
            issue(report, "fail", "retention", "必须保留项未进入正文: %s" % item.get("id"), item=item.get("id"))
        if item.get("figure") and item.get("id") in used and not re.search(re.escape(item["figure"]), draft, re.I):
            issue(report, "fail", "figure", "%s 的证据图/表 %s 未在正文引用" % (item.get("id"), item["figure"]))
    for ln, sentence in sentences(draft):
        cited = ids_in(sentence)
        missing = numeric_missing(sentence, cited, index)
        if not cited and (NUM.search(FIG.sub("", sentence)) or re.search(r"\[[A-Za-z]+\d+\]", sentence)):
            issue(report, "fail", "source_binding", "含事实/数字句缺来源标注", loc=ln, excerpt=sentence[:80])
        for token in missing:
            issue(report, "fail", "number", "数字或单位未逐字回溯到本句来源: %s" % token, loc=ln)
        check_strength(report, ln, sentence, cited, index)
    # 受众与术语：别名统一；公开读者必须能看到中文展开/白话解释。
    public = str(brief.get("audience", "")).lower() in {"public", "公众", "科普", "lay", "general"}
    declared_abbr = set()
    for term in project.get("terms", []):
        canonical = term.get("canonical", "")
        for alias in term.get("aliases", []):
            if alias and alias != canonical and alias in draft:
                issue(report, "fail", "terminology", "使用未锁定别名 %r，应统一为 %r" % (alias, canonical))
        abbr = term.get("abbreviation")
        if not abbr:
            continue
        declared_abbr.add(abbr)
        pos = draft.find(abbr)
        if pos < 0:
            continue
        window = draft[max(0, pos - 180):pos + len(abbr) + 180]
        if term.get("expanded") and term["expanded"] not in window:
            issue(report, "fail", "abbreviation", "%s 首次出现未在邻近位置展开" % abbr)
        if public and term.get("plain") and term["plain"] not in draft:
            issue(report, "fail", "audience", "公众稿缺 %s 的白话解释" % (abbr or canonical))
        if public and not term.get("plain") and canonical in draft:
            issue(report, "fail", "audience", "术语表缺 %s 的 plain 解释" % canonical)
    ignored = set(brief.get("allowed_abbreviations", [])) | {"CI", "SD", "SEM", "SE", "IQR"}
    # 只有未在术语表声明、也不在 brief 白名单中的缩写才报；统计缩写在公众稿仍须声明。
    if public:
        ignored = set(brief.get("allowed_abbreviations", []))
    masked = TAG.sub(" ", draft)
    for m in ACR.finditer(masked):
        abbr = m.group(0)
        if abbr not in declared_abbr and abbr not in ignored and not re.fullmatch(r"[IVXLCDM]+", abbr):
            issue(report, "fail" if public else "warn", "abbreviation", "未声明缩写: %s" % abbr,
                  loc=draft.count("\n", 0, m.start()) + 1)
    # 体裁、篇幅和结构硬约束。
    for section in brief.get("required_sections", []):
        if not re.search(r"(?m)^#{1,6}\s+%s\s*$" % re.escape(section), draft):
            issue(report, "fail", "genre", "缺指定体裁小节: %s" % section)
    plain = TAG.sub("", re.sub(r"(?m)^#{1,6}\s+", "", draft)).strip()
    count = len(re.sub(r"\s+", "", plain))
    if brief.get("max_chars") is not None and count > int(brief["max_chars"]):
        issue(report, "fail", "length", "正文 %d 字超过 max_chars=%s" % (count, brief["max_chars"]))
    if brief.get("min_chars") is not None and count < int(brief["min_chars"]):
        issue(report, "fail", "length", "正文 %d 字低于 min_chars=%s" % (count, brief["min_chars"]))
    # 每段均须能由一条改动记录精确定位；删除不必出现在新稿。
    changes = project.get("changes", [])
    covered = []
    for i, ch in enumerate(changes):
        action = ch.get("action")
        if action not in {"keep", "revise", "add", "delete"}:
            issue(report, "fail", "change_schema", "changes[%d] action 非法" % i)
        if not str(ch.get("reason", "")).strip():
            issue(report, "fail", "change_schema", "changes[%d] 缺删改理由" % i)
        segment = ch.get("draft_segment", "")
        if action != "delete":
            if not segment or segment not in draft:
                issue(report, "fail", "change_anchor", "changes[%d] draft_segment 未逐字命中新稿" % i)
            else:
                covered.append(segment)
        for iid in ch.get("evidence_ids", []):
            if iid not in index:
                issue(report, "fail", "change_schema", "changes[%d] 悬空 evidence_id %s" % (i, iid))
        before = ch.get("before_quote", "")
        if action in {"keep", "revise", "delete"}:
            if not before:
                issue(report, "fail", "change_schema", "changes[%d] 缺 before_quote" % i)
            elif not any(norm(before) in norm(x.get("quote")) for x in project.get("items", [])):
                issue(report, "fail", "change_anchor", "changes[%d] before_quote 未回原文" % i)
    for ln, para in paragraphs(draft):
        if not any(para in c or c in para for c in covered):
            issue(report, "fail", "change_coverage", "正文段落无逐段改动记录", loc=ln, excerpt=para[:60])
    # 题面点名的涉密与未发表材料：默认禁止公开，必须留人工审批。
    sensitive = bool(brief.get("confidential") or brief.get("unpublished"))
    if sensitive:
        handling = brief.get("handling") or {}
        if handling.get("no_external_upload") is not True or handling.get("human_review_required") is not True:
            issue(report, "fail", "disclosure", "涉密/未发表材料须 no_external_upload=true 且 human_review_required=true")
        if brief.get("target_channel") == "public" and not handling.get("release_approved"):
            issue(report, "fail", "disclosure", "公开渠道缺 release_approved，禁止直接发布")
    report["metrics"] = {"chars_no_space": count, "required": sum(bool(x.get("required")) for x in project.get("items", [])),
                         "retained": sum(bool(x.get("required")) and x.get("id") in used for x in project.get("items", [])),
                         "source_tags": len(used), "paragraphs": sum(1 for _ in paragraphs(draft)),
                         "changes": len(changes)}
    return emit(report, report_path)


def metric_numbers(metrics):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in metrics.values())


def cmd_result(result_path, case_path, report_path=None):
    report = {"command": "result", "result": str(result_path), "items": []}
    result, case = load(result_path), load(case_path)
    required = {"case_id", "status", "main_output", "artifacts", "sources", "uncertainty",
                "changes", "validation", "gain"}
    for key in sorted(required - set(result)):
        issue(report, "fail", "contract", "缺顶层字段 %s" % key)
    if result.get("status") not in ALLOWED_STATUS:
        issue(report, "fail", "contract", "status 非法")
    expected_cid = case.get("case_id") or case.get("id")
    if expected_cid and result.get("case_id") != expected_cid:
        issue(report, "fail", "contract", "case_id 与 case.json 不一致")
    oc = case.get("output_contract") or case.get("outputContract") or {}
    names = list(oc) if isinstance(oc, dict) else [x.get("field") or x.get("name") if isinstance(x, dict) else str(x) for x in oc] if isinstance(oc, list) else []
    for name in names:
        if name and name not in result:
            issue(report, "fail", "contract", "缺 output_contract 字段 %s" % name)
    base = Path(result_path).resolve().parent
    for key in ["main_output"]:
        p = result.get(key)
        if p and not (Path(p).is_file() or (base / str(p)).is_file()):
            issue(report, "fail", "artifact", "main_output 文件不存在: %s" % p)
    for art in result.get("artifacts", []):
        p = art.get("path") if isinstance(art, dict) else art
        if p and not (Path(p).is_file() or (base / str(p)).is_file()):
            issue(report, "fail", "artifact", "artifact 文件不存在: %s" % p)
    validation = result.get("validation") or {}
    if result.get("status") == "complete" and (validation.get("fail") != 0 or validation.get("evidence_fail") != 0):
        issue(report, "fail", "closure", "complete 必须有 validation.fail=0 且 evidence_fail=0")
    gain = result.get("gain") or {}
    protocol = gain.get("protocol") or {}
    for key in ("same_input", "same_constraints", "same_permissions", "same_budget"):
        if protocol.get(key) is not True:
            issue(report, "fail", "gain", "gain.protocol.%s 必须为 true" % key)
    state = gain.get("comparison_status")
    if state not in {"pending_platform", "completed", "local_fixture"}:
        issue(report, "fail", "gain", "comparison_status 非法或缺失")
    if state in {"completed", "local_fixture"}:
        b, s = gain.get("baseline") or {}, gain.get("skill") or {}
        if not b.get("input_sha256") or b.get("input_sha256") != s.get("input_sha256"):
            issue(report, "fail", "gain", "A/B 输入指纹不一致，不能比较")
        for side, obj in (("baseline", b), ("skill", s)):
            if not isinstance(obj.get("metrics"), dict) or not obj["metrics"] or not metric_numbers(obj["metrics"]):
                issue(report, "fail", "gain", "%s.metrics 须为非空非负数值" % side)
        if not gain.get("evidence"):
            issue(report, "fail", "gain", "完成的 A/B 必须给 evidence 路径")
    elif gain.get("baseline") not in (None, {}):
        issue(report, "fail", "gain", "pending_platform 不得填入未经平台提供的 baseline")
    report["checked_contract_fields"] = names
    return emit(report, report_path)


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    try:
        if argv[0] == "evidence" and len(argv) in (2, 3):
            return cmd_evidence(argv[1], argv[2] if len(argv) == 3 else None)
        if argv[0] == "audit" and len(argv) in (4, 5):
            return cmd_audit(argv[1], argv[2], argv[3], argv[4] if len(argv) == 5 else None)
        if argv[0] == "result" and len(argv) in (3, 4):
            return cmd_result(argv[1], argv[2], argv[3] if len(argv) == 4 else None)
        print(__doc__)
        return 2
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as e:
        print(json.dumps({"ok": False, "error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
