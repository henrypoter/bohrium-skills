#!/usr/bin/env python3
"""awc.py - Academic Writing Client core.
init|ingest|add-chapter|revise|accept|reject|claim|verify|status|export|result.
State:$AWC_ROOT Out:$AWC_OUT In:$AWC_INPUT."""
import json, os, re, shutil, subprocess, sys, time, zipfile
from pathlib import Path

ROOT = Path(os.environ.get("AWC_ROOT", "/app/work/awc"))
OUT = Path(os.environ.get("AWC_OUT", "/app/output"))
INPUT = Path(os.environ.get("AWC_INPUT", "/input"))

def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def load(p, d=None):
    p = Path(p)
    return json.loads(p.read_text("utf-8")) if p.exists() else d
def save(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".tmp")
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=1), "utf-8")
    os.replace(t, p)  # atomic: crash mid-write never corrupts session
def ok(**kw): print(json.dumps({"ok": True, **kw}, ensure_ascii=False))
def fail(msg, code=2):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False)); sys.exit(code)
def proj():
    try: p = load(ROOT / "project.json")
    except Exception: fail("project.json corrupted (not valid JSON); remove %s and re-init" % (ROOT / "project.json"), 1)
    if not p: fail("no session; run init first", 1)
    for k in ("chapters", "next_rev", "gaps", "case_id"):
        if k not in p: fail("project.json corrupted (missing %s)" % k, 1)
    return p
def touch(p, phase=None):
    p["updated"] = now()
    if phase: p["phase"] = phase
    save(ROOT / "project.json", p)
def need_chapters(p):
    if not p["chapters"]: fail("no chapters; run ingest --dir/--workorder or add-chapter", 5)
def opts(args):
    d, pos, i = {}, [], 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                d[a[2:]] = args[i + 1]; i += 2
            else: d[a[2:]] = True; i += 1
        else: pos.append(a); i += 1
    d["_"] = pos; return d
def get_ch(p, cid):
    for c in p["chapters"]:
        if c["id"] == cid: return c
    fail("unknown chapter %r; have %s" % (cid, [c["id"] for c in p["chapters"]]))
def revs(): return load(ROOT / "revisions.json", [])
def claims(): return load(ROOT / "claims.json", [])
def refs(): return load(ROOT / "refs.json", [])

def cmd_refs(o):
    proj()  # requires an active session
    rf = refs()
    if o.get("add") or (o.get("_") and o["_"][0] == "add"):
        key, entry = o.get("key"), o.get("entry")
        if key is None or not entry: fail("refs add needs --key and --entry")
        if any(str(r.get("key")) == str(key) for r in rf): fail("ref key %s already exists" % key)
        rf.append({"key": key, "entry": entry, "ts": now()})
        save(ROOT / "refs.json", rf); ok(added=key, total=len(rf))
    else:
        ok(refs=rf, total=len(rf))

def _cites(text):
    # 正文数字引用 [n] / [n,m] / [n-m] 抽取（用于引用-文献表交叉核对）。
    # 先剔除公式段/行内公式（如 $\alpha\in[0,1]$ 是区间而非引用），避免误杀。
    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.S)
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.S)
    text = re.sub(r"\$[^$\n]*\$", " ", text)
    out = set()
    for m in re.finditer(r"\[(\d+(?:\s*[-–,，]\s*\d+)*)\]", text):
        for part in re.split(r"[,，]", m.group(1)):
            part = part.strip()
            rm = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", part)
            if rm:
                a, b = int(rm.group(1)), int(rm.group(2))
                if 0 < b - a <= 50: out.update(range(a, b + 1))
            elif part.isdigit(): out.add(int(part))
    return out

def cmd_init(o):
    cid = o.get("case-id") or "case-unknown"
    save(ROOT / "project.json", {"case_id": cid, "title": o.get("title") or cid,
        "created": now(), "updated": now(), "phase": "init", "chapters": [], "next_rev": 1, "gaps": []})
    for f in ("revisions.json", "claims.json", "refs.json"):
        if not (ROOT / f).exists(): save(ROOT / f, [])
    ok(session=str(ROOT), case_id=cid, phase="init")

def _add(p, cid, title, text):
    cid = re.sub(r"[^\w-]", "_", str(cid))
    if any(c["id"] == cid for c in p["chapters"]): fail("chapter %s exists" % cid)
    if not text.strip(): fail("chapter %s: file empty or whitespace-only; treat as material gap, not a chapter" % cid, 4)
    cp = ROOT / "chapters" / (cid + ".md"); cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(text, "utf-8")
    p["chapters"].append({"id": cid, "title": title, "version": 1, "path": str(cp)})

def cmd_ingest(o):
    p = proj(); added = []
    wo, d = o.get("workorder"), o.get("dir")
    items = []
    if wo and Path(wo).exists():
        w = load(wo, {})
        items = w.get("chapters") or w.get("sections") or w.get("files") or []
    elif d and Path(d).is_dir():
        fs = sorted(Path(d).glob("*.md")) + sorted(Path(d).glob("*.txt"))
        items = [{"id": f.stem, "title": f.stem, "path": str(f)} for f in fs]
    else:
        fail("ingest: --workorder/--dir not found; use add-chapter manually", 4)
    for it in items:
        if isinstance(it, str): it = {"id": Path(it).stem, "path": it}
        cid = str(it.get("id") or it.get("file") or len(p["chapters"]) + 1)
        path = it.get("path") or it.get("file")
        if not path or not Path(path).exists():
            p["gaps"].append({"chapter": cid, "issue": "material file missing", "path": path}); continue
        if not Path(path).read_text("utf-8").strip():
            p["gaps"].append({"chapter": cid, "issue": "material file empty", "path": path}); continue
        _add(p, cid, it.get("title") or cid, Path(path).read_text("utf-8")); added.append(cid)
    touch(p, "ingested"); ok(added=added, gaps=p["gaps"], phase=p["phase"])

def cmd_add(o):
    p = proj()
    if not o["_"]: fail("add-chapter <id> [--title T] [--file F | stdin]")
    text = Path(o["file"]).read_text("utf-8") if o.get("file") else sys.stdin.read()
    _add(p, o["_"][0], o.get("title") or o["_"][0], text); touch(p, "ingested")
    ok(chapter=o["_"][0], chars=len(text), phase=p["phase"])

def cmd_revise(o):
    p = proj(); need_chapters(p)
    if not o["_"]: fail("revise <chapter> --anchor '<原文>' --new '<改后>' [--reason/--source/--type]")
    c = get_ch(p, o["_"][0])
    before, after = o.get("anchor"), o.get("new")
    if before is None or after is None: fail("revise needs --anchor and --new")
    if not str(before).strip(): fail("anchor is empty/whitespace; refusing no-op insert", 3)
    if before == after: fail("anchor == new text; no-op revision refused", 3)
    text = Path(c["path"]).read_text("utf-8")
    n = text.count(before)
    if n == 0:
        fail("anchor not found in %s; nothing changed" % c["id"], 3)
    hp = ROOT / "history" / ("%s.v%d.md" % (c["id"], c["version"]))
    hp.parent.mkdir(parents=True, exist_ok=True); hp.write_text(text, "utf-8")
    Path(c["path"]).write_text(text.replace(before, after, 1), "utf-8")
    rid = p["next_rev"]; p["next_rev"] += 1
    r = revs()
    r.append({"id": rid, "chapter": c["id"], "type": o.get("type") or "revise",
        "before": before, "after": after, "reason": o.get("reason") or "",
        "source": o.get("source") or "", "status": "proposed",
        "version_in": c["version"], "version_out": c["version"] + 1,
        "anchor_count": n, "ts": now()})
    c["version"] += 1
    save(ROOT / "revisions.json", r); touch(p, "revised")
    ok(revision=rid, chapter=c["id"], version=c["version"], status="proposed", anchor_count=n)

def _find_rev(rid):
    r = revs()
    for x in r:
        if x["id"] == int(rid): return r, x
    fail("no revision %s" % rid)

def cmd_accept(o):
    r, x = _find_rev(o["_"][0])
    x["status"] = "accepted"; x["decided_ts"] = now()
    save(ROOT / "revisions.json", r); ok(revision=x["id"], status="accepted")

def cmd_reject(o):
    p = proj(); r, x = _find_rev(o["_"][0])
    note = None
    if x["status"] != "rejected":
        c = get_ch(p, x["chapter"]); text = Path(c["path"]).read_text("utf-8")
        if x["after"] and x["after"] in text:
            Path(c["path"]).write_text(text.replace(x["after"], x["before"], 1), "utf-8")
            c["version"] += 1; touch(p)
        else: note = "after-text not found; revert skipped, needs manual check"
    x["status"] = "rejected"; x["decided_ts"] = now()
    if note: x["note"] = note
    save(ROOT / "revisions.json", r); ok(revision=x["id"], status="rejected", note=note)

def _src_file(src):
    if not src: return None
    c = [Path(src)]
    if not Path(src).is_absolute():
        c += [INPUT / src, ROOT / src, Path.cwd() / src, INPUT / Path(src).name]
    for f in c:
        if f.is_file(): return f
    return None

def verify_claim(e):
    # 论断-证据脚本化核验：证据必须在来源文件中逐字回查到，否则 needs-human
    if not e.get("evidence"):
        e["status"] = "needs-human"; e["verify"] = "no evidence text"; return
    f = _src_file(e.get("source") or "")
    if not f:
        e["status"] = "needs-human"; e["verify"] = "source not found: %s" % (e.get("source") or "")
        return
    txt = f.read_text("utf-8"); ev = e["evidence"]
    found = ev in txt or re.sub(r"\s+", "", ev) in re.sub(r"\s+", "", txt)
    e["status"] = "bound" if found else "needs-human"
    e["verify"] = ("verbatim in %s" % f) if found else ("NOT found in %s" % f)

def cmd_claim(o):
    cs = claims()
    e = {"id": o.get("id") or "C%d" % (len(cs) + 1), "claim": o.get("text") or "",
         "evidence": o.get("evidence") or "", "source": o.get("source") or "",
         "locator": o.get("locator") or "", "status": "bound"}
    verify_claim(e)
    cs.append(e); save(ROOT / "claims.json", cs)
    ok(claim=e["id"], status=e["status"], verify=e.get("verify", ""))

def cmd_verify(o):
    cs = claims()
    for e in cs: verify_claim(e)
    save(ROOT / "claims.json", cs)
    p = proj(); touch(p, "verified")
    bad = [c["id"] for c in cs if c["status"] != "bound"]
    ok(verified=len(cs) - len(bad), needs_human=bad, phase=p["phase"])

def cmd_status(o):
    p = proj()
    ok(case_id=p["case_id"], title=p["title"], updated=p["updated"], phase=p.get("phase", "init"),
       chapters=[{"id": c["id"], "version": c["version"]} for c in p["chapters"]],
       proposed_revisions=[r["id"] for r in revs() if r["status"] == "proposed"],
       needs_human_claims=[c["id"] for c in claims() if c["status"] != "bound"],
       gaps=p.get("gaps", []))

def esc_tex(s):
    parts = re.split(r"(\$\$.*?\$\$|\$[^$\n]*\$)", s)
    def e(t):
        t = t.replace("\\", "\\textbackslash{}")
        for a, b in [("&", "\\&"), ("%", "\\%"), ("#", "\\#"), ("_", "\\_"),
                     ("{", "\\{"), ("}", "\\}"), ("~", "\\textasciitilde{}"), ("^", "\\textasciicircum{}")]:
            t = t.replace(a, b)
        return t
    return "".join(x if i % 2 else e(x) for i, x in enumerate(parts))

def md2tex(text):
    out, inlist, inmath = [], False, False
    for ln in text.splitlines():
        s = ln.strip()
        if inmath:
            out.append(ln)
            if "\\]" in s or "$$" in s: inmath = False
            continue
        if s.startswith("\\[") or s.startswith("$$"):
            if inlist: out.append("\\end{itemize}"); inlist = False
            out.append(ln)
            if not ("\\]" in s or (s.startswith("$$") and s.count("$$") > 1)): inmath = True
            continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m:
            if inlist: out.append("\\end{itemize}"); inlist = False
            out.append("\\%s{%s}" % ({1: "section", 2: "subsection", 3: "subsubsection"}[len(m.group(1))], esc_tex(m.group(2))))
        elif re.match(r"^[-*]\s+", s):
            if not inlist: out.append("\\begin{itemize}"); inlist = True
            out.append("\\item " + esc_tex(re.sub(r"^[-*]\s+", "", s)))
        elif not s:
            if inlist: out.append("\\end{itemize}"); inlist = False
            out.append("")
        else: out.append(esc_tex(s))
    if inlist: out.append("\\end{itemize}")
    return "\n".join(out)

def esc_xml(s): return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
      '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>')
RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="%s">'
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="36"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:pPr><w:ind w:left="420"/></w:pPr></w:style></w:styles>') % WNS

def write_docx(title, text, path):
    paras = ['<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % esc_xml(title)]
    for ln in text.splitlines():
        s = ln.rstrip()
        if not s: continue
        m = re.match(r"^(#{1,3})\s+(.*)", s)
        if m: style, s = "Heading%d" % len(m.group(1)), m.group(2)
        elif re.match(r"^\s*[-*]\s+", s): style, s = "ListParagraph", "• " + re.sub(r"^\s*[-*]\s+", "", s)
        else: style = "Normal"
        paras.append('<w:p><w:pPr><w:pStyle w:val="%s"/></w:pPr><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (style, esc_xml(s)))
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>' % (WNS, "".join(paras)))
    with zipfile.ZipFile(str(path), "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT); z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", document); z.writestr("word/styles.xml", STYLES)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)

def readback(p, md, body, rep, cites_text=None):
    # 导出回读自检：docx/tex/md 结构回到内存核对，而非只信写入无异常
    rb = {}
    mdh = len(re.findall(r"^#{1,3}\s+", body, re.M))
    try:
        with zipfile.ZipFile(OUT / "manuscript.docx") as z:
            doc = z.read("word/document.xml").decode("utf-8", "replace")
        h = len(re.findall(r'pStyle w:val="Heading\d"', doc))
        paras = doc.count("<w:p>")
        rb["docx"] = {"status": "ok" if (paras > 0 and esc_xml(p["title"]) in doc and h == mdh) else "mismatch",
                      "paragraphs": paras, "headings": h, "expected_headings": mdh}
    except Exception as e:
        rb["docx"] = {"status": "failed", "reason": str(e)}
    try:
        tex = (OUT / "manuscript.tex").read_text("utf-8")
        rb["tex"] = {"status": "ok" if ("\\begin{document}" in tex and "\\end{document}" in tex and esc_tex(p["title"]) in tex) else "mismatch"}
    except Exception as e:
        rb["tex"] = {"status": "failed", "reason": str(e)}
    rb["md"] = {"status": "ok" if p["title"] in md else "mismatch", "bytes": len(md.encode("utf-8"))}
    keys = set()
    for r in refs():
        try: keys.add(int(r.get("key")))
        except (TypeError, ValueError): pass
    cits = _cites(body if cites_text is None else cites_text)  # 引用核对只看正文，不含文献表自身
    unresolved = sorted(cits - keys)
    rb["refs"] = {"status": "ok" if not unresolved else "mismatch",
                  "citations": sorted(cits), "ref_keys": sorted(keys),
                  "unresolved": unresolved, "unreferenced": sorted(keys - cits)}
    rep["readback"] = rb

def cmd_export(o):
    p = proj(); need_chapters(p)
    OUT.mkdir(parents=True, exist_ok=True)
    manuscript = "\n\n".join(Path(c["path"]).read_text("utf-8") for c in p["chapters"])
    cites_text = manuscript  # 引用核对以正文为准（文献表自身不计入）
    rf = refs()
    if rf:
        manuscript = manuscript.rstrip() + "\n\n## 参考文献\n\n" + \
            "\n".join("[%s] %s" % (r.get("key"), r.get("entry")) for r in rf)
    md = "# %s\n\n%s\n" % (p["title"], manuscript)
    (OUT / "manuscript.md").write_text(md, "utf-8")
    rep = {"md": {"status": "ok", "path": str(OUT / "manuscript.md")}}
    tex = ("\\documentclass[12pt]{ctexart}\n\\usepackage{amsmath,amssymb,booktabs,graphicx}\n"
           "\\usepackage[margin=2.5cm]{geometry}\n\\title{%s}\n\\date{}\n\\begin{document}\n\\maketitle\n"
           % esc_tex(p["title"])) + md2tex(manuscript) + "\n\\end{document}\n"
    (OUT / "manuscript.tex").write_text(tex, "utf-8")
    rep["tex"] = {"status": "ok", "path": str(OUT / "manuscript.tex")}
    try:
        write_docx(p["title"], manuscript, OUT / "manuscript.docx")
        rep["docx"] = {"status": "ok", "path": str(OUT / "manuscript.docx")}
    except Exception as e:
        rep["docx"] = {"status": "failed", "reason": str(e)}
    pdf, tries = OUT / "manuscript.pdf", []
    for name, cmd in [("latex-compiler", ["latex-compiler", "manuscript.tex"]),
                      ("xelatex", ["xelatex", "-interaction=nonstopmode", "manuscript.tex"]),
                      ("pdflatex", ["pdflatex", "-interaction=nonstopmode", "manuscript.tex"])]:
        if pdf.exists(): break
        if not shutil.which(name): tries.append({"tool": name, "status": "absent"}); continue
        try:
            r = None
            for _ in range(2):
                r = subprocess.run(cmd, cwd=str(OUT), timeout=150, capture_output=True, text=True)
            st = "ok" if pdf.exists() and pdf.stat().st_size > 500 else "failed"
            tries.append({"tool": name, "status": st,
                          "reason": None if st == "ok" else (r.stdout or "")[-300:]})
        except Exception as e:
            tries.append({"tool": name, "status": "failed", "reason": str(e)})
    for ext in ("aux", "log", "out", "toc"):
        f = OUT / ("manuscript." + ext)
        if f.exists(): f.unlink()
    rep["pdf"] = {"status": "ok", "path": str(pdf)} if pdf.exists() else \
                 {"status": "failed", "reason": "no latex toolchain; md/tex/docx kept", "tries": tries}
    readback(p, md, manuscript, rep, cites_text)
    save(OUT / "export_report.json", rep)
    touch(p, "exported")
    ok(export_report=rep)

def cmd_result(o):
    p = proj()
    case = load(INPUT / "case.json", {}) or {}
    cid = o.get("case-id") or case.get("case_id") or case.get("id") or p["case_id"]
    cs = claims()
    for e in cs: verify_claim(e)
    save(ROOT / "claims.json", cs)
    r = revs(); rep = load(OUT / "export_report.json", {})
    gaps = p.get("gaps", [])
    pending = [c["id"] for c in cs if c["status"] != "bound"]
    proposed = [x["id"] for x in r if x["status"] == "proposed"]
    failed = [k for k, v in rep.items() if isinstance(v, dict) and v.get("status") == "failed"]
    unres = ((rep.get("readback") or {}).get("refs") or {}).get("unresolved") or []
    limits = (["material gaps: %s" % gaps] if gaps else []) + \
             (["export failed: %s (see export_report.json)" % failed] if failed else []) + \
             (["unverified claims: %s" % pending] if pending else []) + \
             (["unresolved citations: %s (add refs or fix numbering)" % unres] if unres else [])
    status = o.get("status") or ("partial" if limits or proposed else "complete")
    save(OUT / "session_state.json", p)
    keep = ["manuscript.md", "manuscript.tex", "manuscript.docx", "manuscript.pdf",
            "export_report.json", "session_state.json"]
    arts = [{"path": str(OUT / k), "kind": k.rsplit(".", 1)[-1], "bytes": (OUT / k).stat().st_size}
            for k in keep if (OUT / k).exists()]
    res = {
        "case_id": cid, "skill": "academic-writing-client", "status": status,
        "summary": o.get("summary") or "%d chapters, %d revisions (%d proposed), %d claims (%d bound)" %
                   (len(p["chapters"]), len(r), len(proposed), len(cs), len(cs) - len(pending)),
        "main_output": str(OUT / "manuscript.docx") if (OUT / "manuscript.docx").exists() else str(OUT / "manuscript.md"),
        "artifacts": arts,
        "sources": {"claims": cs, "refs": load(ROOT / "refs.json", [])},
        "changes": r,
        "versions": [{"chapter": c["id"], "current_version": c["version"]} for c in p["chapters"]],
        "export_report": rep,
        "confirmations_needed": pending,
        "uncertainty": o.get("uncertainty") or ("; ".join(limits) if limits else "none recorded"),
        "limits": limits, "generated_at": now(),
    }
    oc = case.get("output_contract") or case.get("outputContract")
    names = list(oc) if isinstance(oc, dict) else \
            [x.get("field") or x.get("name") if isinstance(x, dict) else str(x) for x in oc] if isinstance(oc, list) else []
    missing = [k for k in names if k and k not in res]
    for k in missing: res[k] = None
    if missing:
        res["uncertainty"] = str(res["uncertainty"]) + "; contract fields unfilled: %s" % missing
    save(OUT / "result.json", res)
    touch(p, "resulted")
    ok(result=str(OUT / "result.json"), status=status, contract_fields_filled=len(names) - len(missing))

CMDS = {"init": cmd_init, "ingest": cmd_ingest, "add-chapter": cmd_add, "revise": cmd_revise,
        "accept": cmd_accept, "reject": cmd_reject, "claim": cmd_claim, "verify": cmd_verify,
        "refs": cmd_refs, "status": cmd_status, "export": cmd_export, "result": cmd_result}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); sys.exit(0 if len(sys.argv) < 2 else 2)
    CMDS[sys.argv[1]](opts(sys.argv[2:]))
