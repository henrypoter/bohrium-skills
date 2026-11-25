#!/usr/bin/env python3
"""研究问题闭环、结论—数据范围与截断的可复核审计（仅标准库）。

用法:
  logic_audit.py scan <manuscript.md> [-o logic_audit.json]
  logic_audit.py verify <result.json> <logic_audit.json>

scan只能提出候选，不能替代语义诊断；verify要求模型逐候选给出原文锚点、范围关系、
理由和诊断编号。编号/锚点/哈希由脚本复核。exit: scan 0=成功；verify 0=通过、
1=有错误；用法/IO/JSON=2。
"""
import hashlib
import json
import os
import re
import sys

import skeleton as sk

RULE_VERSION = "logic-audit-1.0.0"
RQ_RE = re.compile(
    r"研究问题|研究目标|旨在|拟解决|本文.{0,16}(研究|考察|回答)|是否|如何|"
    r"research question|we aim|this (?:paper|study) (?:aims|investigates)|"
    r"we investigate|we ask|whether|how can", re.I)
CLAIM_RE = re.compile(
    r"表明|显示|证明|导致|提升|降低|优于|相关|发现|综上|总之|"
    r"show|demonstrate|cause|lead to|improve|reduce|outperform|associat|conclude", re.I)
NUM_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?\s*(?:%|℃|°C|mg|ml|μM|倍|天|周|年|例|个|篇)?", re.I)
HEDGE_RE = re.compile(r"可能|初步|在本|该实验|条件下|限于|may|might|suggest|in this|under .*?condition|limited", re.I)
BROAD_RE = re.compile(r"所有|普遍|任意|必然|证明|all|universal|always|proves?|guarantees?", re.I)


def sha_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sec_key(title):
    low = title.lower()
    for key, words in sk.SEC_KEYS.items():
        if any(w in low or w in title for w in words):
            return key
    return "other"


def records(text):
    out = []
    for si, (title, paras, _level) in enumerate(sk.split_sections(text), 1):
        key = sec_key(title)
        for pi, para in enumerate(paras, 1):
            sentences = sk.split_sents(para)
            if not sentences and para.strip():
                sentences = [para.strip()]
            for qi, sent in enumerate(sentences, 1):
                out.append({"anchor": "S%d.P%d.s%d" % (si, pi, qi),
                            "para_anchor": "S%d.P%d" % (si, pi),
                            "section": "S%d" % si, "section_key": key,
                            "title": title, "text": sent})
    return out


def nums(text):
    # 四位年份通常不是实验数据范围，排除；其余值精确到数值与单位。
    values = set()
    for m in NUM_RE.finditer(text):
        token = re.sub(r"\s+", "", m.group(0))
        core = re.match(r"[-+]?\d+(?:\.\d+)?", token).group(0)
        if re.fullmatch(r"(?:19|20)\d{2}", core):
            continue
        values.add(token)
    return values


def truncation(text, recs):
    stripped = text.rstrip()
    signals = []
    if text.count("```") % 2:
        signals.append("unclosed_code_fence")
    if stripped:
        last_line = stripped.splitlines()[-1].strip()
        if re.match(r"^(#{1,6})\s+\S+$|^\d+(?:\.\d+)*[、\s]+\S+$", last_line):
            signals.append("terminal_empty_heading")
        if last_line.endswith(("：", ":")):
            signals.append("dangling_colon")
        if not re.search(r"[。！？.!?；;]\s*$|\[\d+\]\s*$|[】\)\]}]\s*$", stripped):
            signals.append("unterminated_final_text")
    else:
        signals.append("empty_input")
        last_line = ""
    last_anchor = recs[-1]["anchor"] if recs else None
    tail = recs[-1]["text"] if recs else last_line
    return {"suspected": bool(signals), "signals": signals,
            "last_anchor": last_anchor, "last_text_sha256": sha_text(tail),
            "last_text_excerpt": tail[-100:],
            "note": "候选信号；verify 要求注明已读范围、异常与处置，不把正常短标题单独当成截断。"}


def scan(path):
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8", errors="replace")
    recs = records(text)
    intro = [r for r in recs if r["section_key"] in ("introduction", "abstract")]
    # 无标准引言标题时只扫描首节，减少结论/方法中“是否”引发误报。
    if not intro and recs:
        intro = [r for r in recs if r["section"] == recs[0]["section"]]
    questions = [r for r in intro if RQ_RE.search(r["text"])]
    methods = [r for r in recs if r["section_key"] == "method"]
    results = [r for r in recs if r["section_key"] == "results"]
    conclusions = [r for r in recs if r["section_key"] in ("conclusion", "discussion")]
    if not conclusions and recs:
        # 无标题短稿回退末段；_complete 仍需 verify 人工闭环。
        conclusions = [r for r in recs if r["para_anchor"] == recs[-1]["para_anchor"]]
    rqs = []
    for i, q in enumerate(questions, 1):
        missing = [name for name, rows in (("method", methods), ("results", results),
                                           ("conclusion", conclusions)) if not rows]
        rqs.append({"id": "RQ%d" % i, "question_anchor": q["anchor"],
                    "text": q["text"][:240], "missing_section_links": missing,
                    "method_anchors_suggested": [r["anchor"] for r in methods[:12]],
                    "result_anchors_suggested": [r["anchor"] for r in results[:20]],
                    "conclusion_anchors_suggested": [r["anchor"] for r in conclusions[:12]]})
    boundaries = []
    for r in conclusions:
        if not (CLAIM_RE.search(r["text"]) or nums(r["text"])):
            continue
        unseen = sorted(nums(r["text"]) - set().union(*(nums(x["text"]) for x in results)) if results else nums(r["text"]))
        signals = []
        if unseen:
            signals.append("conclusion_numeric_values_not_in_results")
        if BROAD_RE.search(r["text"]) and not HEDGE_RE.search(r["text"]):
            signals.append("unbounded_generalization_needs_scope_check")
        if re.search(r"导致|因果|caus", r["text"], re.I) and not HEDGE_RE.search(r["text"]):
            signals.append("causal_wording_needs_design_check")
        boundaries.append({"id": "CB%d" % (len(boundaries) + 1),
                           "conclusion_anchor": r["anchor"], "text": r["text"][:240],
                           "conclusion_numbers": sorted(nums(r["text"])),
                           "unseen_numbers_vs_results": unseen, "signals": signals,
                           "result_anchors_suggested": [x["anchor"] for x in results[:20]]})
    return {"rule_version": RULE_VERSION,
            "input_fingerprint": {"algorithm": "sha256", "path": path,
                                   "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                                   "anchors_version": "skeleton-v1"},
            "research_question_candidates": rqs, "conclusion_boundary_candidates": boundaries,
            "truncation": truncation(text, recs),
            "anchors": [r["anchor"] for r in recs],
            "sections": [{"section": r["section"], "section_key": r["section_key"],
                          "anchor": r["anchor"]} for r in recs],
            "note": "候选不是缺陷结论；须由 verify 对每条 RQ/CB 裁决，未找到候选时也要保留 scan 与空核查列表。"}


def as_list(value):
    return value if isinstance(value, list) else []


def verify(result, audit):
    errors = []
    fp = audit.get("input_fingerprint", {})
    mf = result.get("input_manifest")
    if result.get("artifact_version") in (None, ""):
        errors.append("P1 缺 artifact_version")
    if not isinstance(mf, dict) or mf.get("algorithm") != "sha256" or mf.get("sha256") != fp.get("sha256") or mf.get("bytes") != fp.get("bytes"):
        errors.append("P1 input_manifest 与 scan 的输入 SHA-256/bytes 不一致")
    logic = result.get("logic_audit")
    if not isinstance(logic, dict):
        return ["P2 缺 logic_audit 对象"]
    if logic.get("rule_version") != RULE_VERSION or audit.get("rule_version") != RULE_VERSION:
        errors.append("P2 logic_audit.rule_version 必须为 " + RULE_VERSION)
    if not str(logic.get("audit_report") or "").strip():
        errors.append("P2 缺 logic_audit.audit_report 路径")
    anchor_key = {r["anchor"]: r["section_key"] for r in audit.get("sections", [])}
    valid_anchors = set(anchor_key)
    diagnoses = {str(d.get("id")): d for d in as_list(result.get("diagnosis")) if isinstance(d, dict)}

    def valid_anchor_list(values, expected=None):
        vals = as_list(values)
        if not vals or any(v not in valid_anchors for v in vals):
            return False
        return expected is None or any(anchor_key.get(v) == expected for v in vals)

    rqs = logic.get("research_questions")
    expected_rq = {q["id"]: q for q in audit.get("research_question_candidates", [])}
    got_rq = {str(q.get("id")): q for q in as_list(rqs) if isinstance(q, dict)}
    if set(got_rq) != set(expected_rq) or len(as_list(rqs)) != len(got_rq):
        errors.append("Q1 research_questions 必须逐项且无重复覆盖 scan 的 RQ 编号")
    for qid, candidate in expected_rq.items():
        q = got_rq.get(qid)
        if not q:
            continue
        status = q.get("status")
        if q.get("question_anchor") != candidate["question_anchor"]:
            errors.append("Q2 %s question_anchor 被替换" % qid)
        if status not in ("closed", "open", "not_applicable"):
            errors.append("Q3 %s status 非法" % qid)
        if not str(q.get("rationale") or "").strip():
            errors.append("Q3 %s 缺闭环判定理由" % qid)
        if status == "closed":
            for field, key in (("method_anchors", "method"), ("result_anchors", "results"),
                               ("conclusion_anchors", ("conclusion", "discussion"))):
                values = as_list(q.get(field))
                if not values or any(v not in valid_anchors for v in values):
                    errors.append("Q3 %s closed 但 %s 缺失/锚点非法" % (qid, field))
                elif key != ("conclusion", "discussion") and not any(anchor_key.get(v) == key for v in values):
                    errors.append("Q3 %s %s 未落在 %s 节" % (qid, field, key))
                elif key == ("conclusion", "discussion") and not any(anchor_key.get(v) in key for v in values):
                    errors.append("Q3 %s conclusion_anchors 未落在结论/讨论节" % qid)
        if status == "open":
            ids = as_list(q.get("diagnosis_ids"))
            if not ids or any(did not in diagnoses or diagnoses[did].get("dimension") != "research_question" for did in ids):
                errors.append("Q4 %s open 必须关联 research_question diagnosis_ids" % qid)

    cbs = logic.get("conclusion_boundaries")
    expected_cb = {c["id"]: c for c in audit.get("conclusion_boundary_candidates", [])}
    got_cb = {str(c.get("id")): c for c in as_list(cbs) if isinstance(c, dict)}
    if set(got_cb) != set(expected_cb) or len(as_list(cbs)) != len(got_cb):
        errors.append("B1 conclusion_boundaries 必须逐项且无重复覆盖 scan 的 CB 编号")
    for cid, candidate in expected_cb.items():
        c = got_cb.get(cid)
        if not c:
            continue
        if c.get("conclusion_anchor") != candidate["conclusion_anchor"]:
            errors.append("B2 %s conclusion_anchor 被替换" % cid)
        relation = c.get("scope_relation")
        if relation not in ("within", "narrower", "broader", "uncertain"):
            errors.append("B6 %s scope_relation 非法" % cid)
        if not str(c.get("rationale") or "").strip():
            errors.append("B6 %s 缺范围比对理由" % cid)
        values = as_list(c.get("result_anchors"))
        if not values or any(v not in valid_anchors for v in values) or not any(anchor_key.get(v) == "results" for v in values):
            errors.append("B3 %s 缺 results 节数据锚点或锚点非法" % cid)
        if candidate.get("unseen_numbers_vs_results") and relation in ("within", "narrower"):
            errors.append("B4 %s 结论含结果中未见数值，不能判 within/narrower" % cid)
        ids = as_list(c.get("diagnosis_ids"))
        if relation == "broader" and (not ids or any(did not in diagnoses or diagnoses[did].get("dimension") != "conclusion_boundary" for did in ids)):
            errors.append("B5 %s broader 必须关联 conclusion_boundary diagnosis_ids" % cid)

    actual_t = audit.get("truncation", {})
    t = logic.get("truncation")
    if not isinstance(t, dict):
        errors.append("T1 缺 logic_audit.truncation")
        t = {}
    if t.get("suspected") is not actual_t.get("suspected") or t.get("last_anchor") != actual_t.get("last_anchor") or t.get("last_text_sha256") != actual_t.get("last_text_sha256"):
        errors.append("T1 截断状态/末锚点/末文本哈希与 scan 不一致")
    if not str(t.get("action") or "").strip():
        errors.append("T2 截断处置 action 为空（无截断也须写已完成全文核查）")
    if actual_t.get("suspected"):
        if result.get("status") != "partial" or t.get("read_scope") != "partial":
            errors.append("T2 疑似截断必须 status=partial 且 read_scope=partial")
        if not as_list(result.get("anomalies")) or not as_list(result.get("material_gaps")):
            errors.append("T2 疑似截断必须同时登记 anomalies 与 material_gaps")
    elif t.get("read_scope") != "complete":
        errors.append("T2 无截断信号时 read_scope 应为 complete；若有其他读取缺口须重跑/说明")
    return errors


def out_json(obj, path=None):
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def main(argv):
    try:
        if len(argv) >= 3 and argv[1] == "scan":
            args = argv[2:]
            path = args[0]
            out = None
            if "-o" in args:
                j = args.index("-o")
                if j + 1 >= len(args):
                    raise ValueError("-o 缺路径")
                out = args[j + 1]
            audit = scan(path)
            out_json(audit, out)
            return 0
        if len(argv) == 4 and argv[1] == "verify":
            with open(argv[2], encoding="utf-8") as f:
                result = json.load(f)
            with open(argv[3], encoding="utf-8") as f:
                audit = json.load(f)
            errors = verify(result, audit)
            report = {"ok": not errors, "errors": errors, "rule_version": RULE_VERSION}
            out_json(report)
            return 1 if errors else 0
        print(__doc__)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": ["IO/JSON: " + str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
