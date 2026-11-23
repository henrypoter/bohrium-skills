#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reading-client v3: 打开→检索→选中→问答→批注→导出+断点续读; 锚点四级回退, 未核验记 needs_confirmation。"""
import argparse, difflib, json, os, re, shutil, subprocess, sys, time

SCHEMA = 2
VERIFIED = ("verbatim", "normalized")

def norm(s): return re.sub(r"\s+", " ", s or "").strip()
def nows(s): return re.sub(r"\s+", "", s or "")          # CJK 跨行/断字：去全部空白后精确比对
def dehyph(s): return re.sub(r"-\s*\n\s*", "", s or "")
def readf(p): return open(p, encoding="utf-8", errors="replace").read() if p else ""
def pub(l): return {k: l[k] for k in ("page", "line", "matched", "confidence") if k in l}
def is_verified(c): return bool(c) and c.split("(")[0] in VERIFIED
def jout(o): print(json.dumps(o, ensure_ascii=False))

class Session:
    DEFAULT = {"schema_version": SCHEMA, "doc": None, "pages": 0, "text_status": None,
               "extraction": None, "page_offset": 0, "selection": None, "qa": [],
               "notes": [], "reading_position": None, "opened_at": None}
    def __init__(self, d):
        self.dir = d
        os.makedirs(d, exist_ok=True)
        self.sp = os.path.join(d, "session.json"); self.pp = os.path.join(d, "pages.jsonl")
        self.state = dict(self.DEFAULT); self.health = "fresh"; self.bak_done = False
        existed = os.path.exists(self.sp)
        for cand, tag in ((self.sp, "ok"), (self.sp + ".bak", "recovered_from_backup")):
            if not os.path.exists(cand): continue
            try:
                st = json.load(open(cand, encoding="utf-8"))
                if isinstance(st, dict) and all(k in st for k in ("doc", "qa", "notes")):
                    self.state.update(st); self.health = tag; break
            except Exception: continue
        else:
            if existed: self.health = "fresh_after_corruption"
    def save(self):
        self.state["schema_version"] = SCHEMA
        if not self.bak_done and os.path.exists(self.sp):
            try: shutil.copyfile(self.sp, self.sp + ".bak")
            except Exception: pass
            self.bak_done = True
        tmp = self.sp + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=1)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, self.sp)
    def pages(self):
        out = []
        if os.path.exists(self.pp):
            for line in open(self.pp, encoding="utf-8"):
                line = line.strip()
                if line: out.append(json.loads(line))
        return out

def fail(msg, code=2):
    jout({"ok": False, "error": msg}); sys.exit(code)

def locate(pages, quote):
    q = norm(quote)
    if not q: return []
    qd = norm(dehyph(quote))
    qn = nows(quote)
    res = []
    for pg in pages:
        raw, t, td = pg["text"], norm(pg["text"]), norm(dehyph(pg["text"]))
        tn = nows(pg["text"])
        for cand, conf, tt in ((quote, "verbatim", raw), (q, "normalized", t),
                               (qd, "normalized", td), (qn, "normalized", tn)):
            if not cand: continue
            idx = tt.find(cand)
            if idx >= 0:
                head = norm(cand)[:40]
                hws = nows(cand)[:12]      # 取引文开头定位所在行，跨行引文也能落到起始行
                ln = next((i for i, l in enumerate(raw.splitlines(), 1)
                           if head in norm(l) or (hws and hws in nows(l))), None)
                res.append({"page": pg["page"], "line": ln, "confidence": conf,
                            "matched": norm(cand)[:120],
                            "pre": norm(tt[max(0, idx - 48):idx]),
                            "suf": norm(tt[idx + len(cand):idx + len(cand) + 48])})
                break
    return res

def fuzzy_find(pages, anchor):
    q = nows(anchor.get("exact", ""))
    if len(q) < 12: return None
    pre, suf = norm(anchor.get("prefix", ""))[-8:], norm(anchor.get("suffix", ""))[:8]
    best = None
    for pg in pages:
        t = nows(dehyph(pg["text"]))
        starts = ([m.start() for m in re.finditer(re.escape(pre), t)] if pre else [])
        if suf:
            starts += [max(0, m.start() - len(q)) for m in re.finditer(re.escape(suf), t)]
        if not starts:
            starts = range(0, max(1, len(t) - len(q)), max(1, len(q) // 3))
        for st in list(starts)[:200]:
            r = difflib.SequenceMatcher(None, q, t[st:st + len(q)]).ratio()
            if best is None or r > best[0]: best = (r, pg, st, t)
    if best:
        d = max(2, len(q) // 3)
        for st2 in range(max(0, best[2] - d),
                         max(1, min(len(best[3]) - len(q), best[2] + d)) + 1):
            r2 = difflib.SequenceMatcher(None, q, best[3][st2:st2 + len(q)]).ratio()
            if r2 > best[0]: best = (r2, best[1], st2, best[3])
    if best and best[0] >= 0.85:
        r, pg, st, t = best
        seg = t[st:st + len(q)]
        ln = next((i for i, l in enumerate(pg["text"].splitlines(), 1)
                   if seg[:30] in norm(l)), None)
        return {"page": pg["page"], "line": ln, "matched": seg[:120],
                "confidence": "fuzzy(%.2f)" % r}
    return None

def resolve(pages, anchor):
    locs = locate(pages, anchor.get("exact", ""))
    if locs: return locs
    loc = fuzzy_find(pages, anchor)
    if loc: return [loc]
    pg = next((p for p in pages if p["page"] == anchor.get("physical_page")), None)
    if pg:
        lines = pg["text"].splitlines()
        ln = anchor.get("line") or 1
        if 1 <= ln <= len(lines):
            return [{"page": pg["page"], "line": ln, "matched": norm(lines[ln - 1])[:120],
                     "confidence": "page_line_only"}]
    return []

def make_anchor(loc, quote):
    return {"physical_page": loc["page"], "line": loc.get("line"),
            "prefix": loc.get("pre", ""), "exact": norm(quote)[:300],
            "suffix": loc.get("suf", ""), "confidence": loc["confidence"]}

def resolve_and_anchor(pages, quote):
    anch = {"physical_page": None, "line": None, "prefix": "",
            "exact": norm(quote)[:300], "suffix": "", "confidence": None}
    locs = resolve(pages, anch)
    if locs:
        anch.update(physical_page=locs[0]["page"], line=locs[0].get("line"),
                    confidence=locs[0]["confidence"])
    return anch

def paragraph_at(pg, line_no):
    lines = pg["text"].splitlines()
    if line_no is None or not lines: return norm(pg["text"])[:800]
    i = line_no - 1
    lo = hi = i
    while lo > 0 and norm(lines[lo - 1]): lo -= 1
    while hi < len(lines) - 1 and norm(lines[hi + 1]): hi += 1
    return norm("\n".join(lines[lo:hi + 1]))[:800]

def set_pos(s, page, line, quote, src):
    s.state["reading_position"] = {"doc": s.state.get("doc"), "physical_page": page or 1,
        "line": line or 1, "quote": norm(quote)[:160], "source": src, "ts": int(time.time())}

def cmd_open(a):
    s = Session(a.workdir)
    if not os.path.exists(a.file): fail("material_missing: %s" % a.file)
    if a.file.lower().endswith(".pdf"):
        try:
            def _pdf(flag):
                c = ["pdftotext"] + ([flag] if flag else []) + [a.file, "-"]
                return subprocess.run(c, capture_output=True, timeout=120).stdout.decode("utf-8", "replace")
            txt, mode = _pdf("-layout"), "pdftotext-layout"
            if len(norm(txt)) < 40: txt, mode = _pdf(None), "pdftotext-raw"
        except FileNotFoundError: fail("tool_missing: pdftotext")
        except subprocess.TimeoutExpired: fail("extract_timeout: pdftotext >120s")
        pages = txt.split("\f")
    else:
        txt = readf(a.file)
        pages = txt.split("\f") if "\f" in txt else [txt]
        mode = "plain-text"
    if pages and not norm(pages[-1]): pages = pages[:-1]
    if not pages: fail("empty_document")
    text_status = "ok" if sum(len(norm(p)) for p in pages) >= 100 else "no_text_layer"
    with open(s.pp, "w", encoding="utf-8") as f:
        for i, p in enumerate(pages, 1):
            f.write(json.dumps({"page": i, "text": p}, ensure_ascii=False) + "\n")
    doc = os.path.abspath(a.file)
    rp = s.state.get("reading_position")
    s.state.update(doc=doc, pages=len(pages), text_status=text_status,
                   extraction=mode, page_offset=a.page_offset, selection=None,
                   opened_at=int(time.time()))
    if not rp or rp.get("doc") != doc: set_pos(s, 1, 1, "", "open")
    s.save()
    jout({"ok": True, "doc": doc, "pages": len(pages), "text_status": text_status,
          "extraction": mode, "session_health": s.health})

def cmd_search(a):
    s = Session(a.workdir)
    pages = s.pages()
    if not pages: fail("session_empty")
    pat = re.compile(a.query if a.regex else re.escape(a.query), re.I)
    off = s.state.get("page_offset", 0)
    hits = [{"page": pg["page"], "line": ln, "printed_page": pg["page"] + off,
             "text": norm(line)[:160]}
            for pg in pages for ln, line in enumerate(pg["text"].splitlines(), 1)
            if pat.search(line)]
    jout({"total": len(hits), "hits": hits[:a.topk]})

def cmd_select(a):
    s = Session(a.workdir)
    pages = s.pages()
    if not pages: fail("session_empty")
    if a.quote:
        locs = locate(pages, a.quote) or resolve(pages, {"exact": a.quote})
        if not locs: fail("quote_not_found: 引用不在原文（需改用原文原句）")
        sel = {"kind": "quote", "anchor": make_anchor(locs[0], a.quote)}
    else:
        pg = next((p for p in pages if p["page"] == a.page), None)
        if pg is None: fail("page_out_of_range: %s（共 %s 页）" % (a.page, len(pages)))
        lines = pg["text"].splitlines()
        st, en = a.start_line or 1, min(a.end_line or len(lines), len(lines))
        if st > en: fail("bad_range")
        quote = norm("\n".join(lines[st - 1:en]))[:300]
        locs = locate(pages, quote)
        sel = {"kind": "range", "anchor": make_anchor(locs[0], quote) if locs else
               {"physical_page": a.page, "line": st, "prefix": "", "exact": quote,
                "suffix": "", "confidence": "page_line_only"}}
    s.state["selection"] = sel
    anch = sel["anchor"]
    set_pos(s, anch.get("physical_page"), anch.get("line"), anch.get("exact", ""), "select")
    s.save()
    pg = next(p for p in pages if p["page"] == anch["physical_page"])
    jout({"ok": True, "selection": sel,
          "needs_confirmation": not is_verified(anch.get("confidence")),
          "context_paragraph": paragraph_at(pg, anch.get("line"))})

def cmd_verify(a):
    s = Session(a.workdir)
    pages = s.pages()
    if not pages: fail("session_empty")
    quote = a.quote or readf(a.quote_file)
    locs = locate(pages, quote) or resolve(pages, {"exact": quote})
    ok = bool(locs) and is_verified(locs[0]["confidence"])
    jout({"verified": ok, "needs_confirmation": not ok,
          "locations": [pub(l) for l in locs[:3]],
          "note": None if ok else
          ("证据仅模糊/兜底命中，需人工复核" if locs else "证据不在原文：该结论不得写为事实")})
    sys.exit(0 if ok else 1)

def cmd_qa(a):
    s = Session(a.workdir)
    pages = s.pages()
    if not pages: fail("session_empty")
    q = a.question or readf(a.question_file)
    ans = a.answer or readf(a.answer_file)
    if not (q and ans): fail("need_question_and_answer")
    evid = list(a.evidence or [])
    if a.evidence_file:
        evid += [b for b in (norm(x) for x in re.split(r"\n\s*\n", readf(a.evidence_file))) if b]
    entries = []
    for ev in evid:
        locs = locate(pages, ev)
        anch = make_anchor(locs[0], ev) if locs else resolve_and_anchor(pages, ev)
        conf = anch.get("confidence")
        verified = is_verified(conf)
        entries.append({"quote": norm(ev)[:300], "anchor": anch,
                        "verified": verified, "confidence": conf or "failed",
                        "needs_confirmation": not verified,
                        "locations": [pub(l) for l in resolve(pages, anch)[:2]]})
    entry = {"id": len(s.state["qa"]) + 1, "question": q, "answer": ans,
             "selection": s.state.get("selection"), "evidence": entries,
             "all_verified": (all(e["verified"] for e in entries) if entries else None),
             "ts": int(time.time())}
    s.state["qa"].append(entry)
    pos_a = (s.state.get("selection") or {}).get("anchor") or \
            (entries[0]["anchor"] if entries else None)
    if pos_a and pos_a.get("physical_page"):
        set_pos(s, pos_a.get("physical_page"), pos_a.get("line"), pos_a.get("exact", ""), "qa")
    s.save()
    unv = [e["quote"][:60] for e in entries if e["needs_confirmation"]]
    jout({"ok": True, "qa_id": entry["id"], "all_verified": entry["all_verified"],
          "confidence": [e["confidence"] for e in entries],
          "needs_confirmation": unv, "unverified": unv})

def cmd_note(a):
    s = Session(a.workdir)
    pages = s.pages()
    if not s.state.get("doc"): fail("session_empty")
    anch = None
    if a.quote:
        locs = locate(pages, a.quote)
        anch = make_anchor(locs[0], a.quote) if locs else resolve_and_anchor(pages, a.quote)
    page = anch.get("physical_page") if anch and anch.get("physical_page") else a.page
    line = anch.get("line") if anch else a.line
    s.state["notes"].append({"page": page, "line": line, "anchor": anch,
        "quote": norm(a.quote)[:200] if a.quote else None, "text": a.text,
        "ts": int(time.time())})
    set_pos(s, page, line, a.quote or (anch.get("exact", "") if anch else ""), "note")
    s.save()
    jout({"ok": True, "note_id": len(s.state["notes"]),
          "anchor_confidence": anch["confidence"] if anch else None,
          "needs_confirmation": bool(anch) and not is_verified(anch.get("confidence"))})

def _hint(st):
    rp = st.get("reading_position")
    if rp and st.get("pages"):
        return "续读 p%d:L%d(%s)" % (rp.get("physical_page", 1), rp.get("line", 1),
                                     rp.get("source", "?"))
    return None

def cmd_status(a):
    s = Session(a.workdir)
    st = s.state
    nc = sorted({e["id"] for e in st["qa"] for ev in e["evidence"]
                 if ev.get("needs_confirmation")})
    jout({"doc": st["doc"], "pages": st["pages"], "text_status": st["text_status"],
          "extraction": st.get("extraction"), "page_offset": st.get("page_offset", 0),
          "schema_version": st.get("schema_version"), "session_health": s.health,
          "backup_exists": os.path.exists(s.sp + ".bak"), "opened_at": st.get("opened_at"),
          "reading_position": st.get("reading_position"), "resume_hint": _hint(st),
          "qa_count": len(st["qa"]), "qa_needs_confirmation": nc,
          "notes_count": len(st["notes"])})

def cmd_resume(a):
    s = Session(a.workdir)
    st = s.state
    pages = s.pages()
    if not st.get("doc") or not pages: fail("session_empty")
    rp = st.get("reading_position") or {}
    pg = next((p for p in pages if p["page"] == rp.get("physical_page")), pages[0])
    ln = rp.get("line") or 1
    jout({"ok": True, "doc": st["doc"], "reading_position": rp,
          "resume_hint": _hint(st), "context_paragraph": paragraph_at(pg, ln),
          "qa_count": len(st["qa"]), "notes_count": len(st["notes"]),
          "session_health": s.health})

def _target(doc, an, quote):
    return {"source": doc,
            "selector": {"type": "TextQuoteSelector", "prefix": an.get("prefix", ""),
                         "exact": an.get("exact", quote), "suffix": an.get("suffix", "")},
            "physical_page": an.get("physical_page"), "line": an.get("line")}

def cmd_export(a):
    s = Session(a.workdir)
    st = s.state
    if not st.get("doc"): fail("session_empty")
    os.makedirs(a.out, exist_ok=True)
    L = ["# 阅读记录 Reading Record", "", "- 文献: `%s`" % st["doc"],
         "- 页数: %s | 文本层: %s | 抽取方式: %s" % (st["pages"], st["text_status"],
                                                   st["extraction"]),
         "- 页码偏移(物理页→印刷页): %+d" % st.get("page_offset", 0), ""]
    for e in st["qa"]:
        L += ["## Q%d %s" % (e["id"], e["question"]), "", e["answer"], "", "证据锚点:"]
        if not e["evidence"]:
            L.append("- （无证据引用：此回答仅为概述，未绑定原文）")
        for ev in e["evidence"]:
            loc = ev["locations"][0] if ev["locations"] else None
            anch = ("p%d%s" % (loc["page"], ":L%d" % loc["line"] if loc.get("line") else "")) \
                   if loc else "未定位"
            tag = "已核验" if ev["verified"] else "需人工确认"
            L.append("- [%s|%s] %s — “%s”" % (tag, ev.get("confidence", "failed"),
                                              anch, ev["quote"][:80]))
        L.append("")
    if st["notes"]:
        L += ["## 批注"]
        for n in st["notes"]:
            conf = ("|%s" % n["anchor"]["confidence"]) if n.get("anchor") else ""
            L.append("- p%s%s%s: %s" % (n["page"], ":L%d" % n["line"] if n.get("line") else "",
                                        conf, n["text"]))
        L.append("")
    rec = os.path.join(a.out, "reading_record.md")
    open(rec, "w", encoding="utf-8").write("\n".join(L))
    anns = []
    for e in st["qa"]:
        for i, ev in enumerate(e["evidence"]):
            an = ev.get("anchor") or {}
            anns.append({"id": "qa%d-ev%d" % (e["id"], i + 1), "type": "Annotation",
                "body": {"question": e["question"], "answer": e["answer"]},
                "target": _target(st["doc"], an, ev["quote"]),
                "confidence": ev.get("confidence"), "verified": ev["verified"],
                "needs_confirmation": ev.get("needs_confirmation", False)})
    for i, n in enumerate(st["notes"]):
        an = n.get("anchor") or {}
        anns.append({"id": "note%d" % (i + 1), "type": "Annotation",
            "body": {"text": n["text"]}, "target": _target(st["doc"], an, n.get("quote") or ""),
            "confidence": an.get("confidence"), "verified": bool(n.get("anchor")),
            "needs_confirmation": bool(an) and not is_verified(an.get("confidence"))})
    ap = os.path.join(a.out, "annotations.json")
    json.dump({"schema_version": SCHEMA, "doc": st["doc"], "annotations": anns},
              open(ap, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    unv = [e["id"] for e in st["qa"] if e["all_verified"] is False]
    fuzzy = any(str(ev.get("confidence", "")).startswith("fuzzy")
                for e in st["qa"] for ev in e["evidence"])
    nc = [{"qa_id": e["id"], "quote": ev["quote"][:80], "confidence": ev.get("confidence"),
           "reason": "证据未能逐字核验（模糊/兜底/未命中），需人工复核原文"}
          for e in st["qa"] for ev in e["evidence"] if ev.get("needs_confirmation")]
    if st["text_status"] != "ok":
        status = "partial: 扫描件/无文本层，仅部分可读"
    elif unv:
        status = "partial: QA %s 存在未核验证据" % unv
    else:
        status = "success"
    draft = {"case_id": "", "status": status,
             "answers": [{"question": e["question"], "answer": e["answer"],
                          "evidence": e["evidence"]} for e in st["qa"]],
             "annotations": st["notes"], "needs_confirmation": nc,
             "reading_record": rec, "annotations_file": ap, "sources": [st["doc"]],
             "uncertainty": (["扫描件无文本层，仅覆盖可抽取文本"] if st["text_status"] != "ok"
                             else []) + ["存在未核验证据引用"] * bool(unv)
                            + ["存在模糊匹配证据，置信度已降级，建议人工复核"] * bool(fuzzy),
             "change_log": ["export at %d: %d QA, %d notes, %d annotations" %
                            (int(time.time()), len(st["qa"]), len(st["notes"]), len(anns))]}
    dp = os.path.join(a.out, "result_draft.json")
    json.dump(draft, open(dp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    jout({"ok": True, "reading_record": rec, "annotations": ap, "result_draft": dp,
          "status": status, "needs_confirmation": len(nc)})

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workdir", default="/app/work/reader_session")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("open")
    p.add_argument("file"); p.add_argument("--page-offset", type=int, default=0)
    p.set_defaults(f=cmd_open)
    p = sub.add_parser("search")
    p.add_argument("query"); p.add_argument("--regex", action="store_true")
    p.add_argument("--topk", type=int, default=8); p.set_defaults(f=cmd_search)
    p = sub.add_parser("select")
    p.add_argument("--quote"); p.add_argument("--page", type=int)
    p.add_argument("--start-line", type=int); p.add_argument("--end-line", type=int)
    p.set_defaults(f=cmd_select)
    p = sub.add_parser("verify")
    p.add_argument("--quote"); p.add_argument("--quote-file")
    p.set_defaults(f=cmd_verify)
    p = sub.add_parser("qa")
    p.add_argument("--question"); p.add_argument("--question-file")
    p.add_argument("--answer"); p.add_argument("--answer-file")
    p.add_argument("--evidence", action="append"); p.add_argument("--evidence-file")
    p.set_defaults(f=cmd_qa)
    p = sub.add_parser("note")
    p.add_argument("--page", type=int, required=True); p.add_argument("--text", required=True)
    p.add_argument("--line", type=int); p.add_argument("--quote")
    p.set_defaults(f=cmd_note)
    p = sub.add_parser("status")
    p.set_defaults(f=cmd_status)
    p = sub.add_parser("resume")
    p.set_defaults(f=cmd_resume)
    p = sub.add_parser("export")
    p.add_argument("--out", default="/app/output"); p.set_defaults(f=cmd_export)
    a = ap.parse_args()
    a.f(a)

if __name__ == "__main__":
    main()
