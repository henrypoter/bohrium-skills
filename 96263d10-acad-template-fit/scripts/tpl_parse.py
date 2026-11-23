#!/usr/bin/env python3
# tpl_parse.py -- extract checkable spec + template fingerprint. Stdlib only.
# Usage: tpl_parse.py <file>... [--out spec.json]; items carry file+line; conflicts kept.
import hashlib, json, os, re, subprocess, sys, zipfile

CN = {"初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18, "三号": 16, "小三": 15,
      "四号": 14, "小四": 12, "五号": 10.5, "小五": 9, "六号": 7.5}
REF = r"(GB/?T?\s*7714|IEEE|APA|Vancouver|ACS|numbered|author-?year)"
PROV = re.compile(r"\\Provides(Class|Package)\{([^}]+)\}(?:\[([^\]]*)\])?")
PKG = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}|\\RequirePackage(?:\[[^\]]*\])?\{([^}]+)\}")
KNOWN = {("natbib", "biblatex"): "two citation backends", ("inputenc", "fontspec"): "XeLaTeX: drop inputenc",
         ("float", "floatrow"): "float layout conflict"}

def it(key, req, val, unit, src, ln):
    return {"key": key, "requirement": req, "value": val, "unit": unit, "source_file": src, "source_line": ln}

def scan_tex(text, src):
    out, warn = [], []
    m = re.search(r"\\documentclass\[([^\]]*)\]\{([^}]*)\}", text)
    if m:
        ln = text[:m.start()].count("\n") + 1
        for o in m.group(1).split(","):
            o = o.strip()
            if o == "twocolumn": out.append(it("page.columns", "columns", 2, "", src, ln))
            if o in ("a4paper", "letterpaper"): out.append(it("page.size", "paper size", o.replace("paper", "").upper(), "", src, ln))
            if re.fullmatch(r"1[012]pt", o): out.append(it("body.font_size", "base font size", float(o[:-2]), "pt", src, ln))
    for i, line in enumerate(text.splitlines(), 1):
        if "geometry" in line:
            for k in ("top", "bottom", "left", "right", "margin"):
                mm = re.search(k + r"\s*=\s*([\d.]+)\s*(cm|mm|in)", line)
                if mm: out.append(it("page.margin_" + k, k + " margin", float(mm.group(1)), mm.group(2), src, i))
            if "twocolumn" in line: out.append(it("page.columns", "columns", 2, "", src, i))
        for pat, key, req, unit in (
            (r"\\linespread\{([\d.]+)\}", "body.line_spacing", "line spread factor", "x"),
            (r"\\bibliographystyle\{([^}]+)\}", "refs.style", "bibliography style", ""),
            (r"style\s*=\s*([\w-]+)[^\\]*\{biblatex\}", "refs.style", "biblatex style", "")):
            mm = re.search(pat, line)
            if mm: out.append(it(key, req, mm.group(1), unit, src, i))
        if re.search(r"\\(onehalfspacing|doublespacing)\b", line):
            out.append(it("body.line_spacing", "line spacing", "1.5" if "onehalf" in line else "2.0", "x", src, i))
        if re.search(r"\\usepackage\{?(newtxtext|mathptmx|times)\}?", line):
            warn.append("Times-like font at %s:%d -- use Liberation Serif (organizer revision3)" % (src, i))
    if "\\begin{abstract}" in text: out.append(it("front.abstract", "abstract env", True, "", src, 0))
    return out, warn

def scan_meta(text, src):
    vers, pkgs = [], []
    mm = PROV.search(text)
    if mm: vers.append({"file": src, "type": mm.group(1).lower(), "name": mm.group(2),
                        "version": (mm.group(3) or "").strip() or None})
    for m2 in PKG.finditer(text):
        p = (m2.group(1) or m2.group(2) or "").strip()
        if p: pkgs.append(p)
    return vers, pkgs

def scan_docx(path, src):
    out, warn = [], []
    try:
        z = zipfile.ZipFile(path); doc = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception as e:
        return [], ["cannot read docx XML in %s: %s" % (src, e)]
    m = re.search(r'<w:pgSz w:w="(\d+)" w:h="(\d+)"', doc)
    if m: out.append(it("page.size", "page size twips (11906x16838=A4)", "%sx%s" % m.groups(), "twip", src, 0))
    m = re.search(r"<w:pgMar ([^/]*)/>", doc)
    if m:
        for k in ("top", "right", "bottom", "left"):
            mm = re.search(r'w:%s="(\d+)"' % k, m.group(1))
            if mm: out.append(it("page.margin_" + k, k + " margin", round(int(mm.group(1)) / 567.0, 2), "cm(from twips)", src, 0))
    m = re.search(r'<w:cols w:num="(\d+)"', doc)
    if m and m.group(1) != "1": out.append(it("page.columns", "columns", int(m.group(1)), "", src, 0))
    try:
        sty = z.read("word/styles.xml").decode("utf-8", "replace")
        for sid, body in re.findall(r'<w:style [^>]*w:styleId="([^"]+)"[^>]*>(.*?)</w:style>', sty, re.S):
            nm = re.search(r'<w:name w:val="([^"]+)"', body); label = nm.group(1) if nm else sid
            sz = re.search(r'<w:sz w:val="(\d+)"', body)
            if sz: out.append(it("style.%s.font_size" % label, "font size", int(sz.group(1)) / 2, "pt", src, 0))
    except KeyError:
        warn.append("no styles.xml in %s" % src)
    return out, warn

def scan_text(text, src):
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for cn, ens in (("上下边距", ("top", "bottom")), ("左右边距", ("left", "right")),
                        ("上边距", ("top",)), ("下边距", ("bottom",)), ("左边距", ("left",)), ("右边距", ("right",))):
            pre = "(?<!上)" if cn == "下边距" else ("(?<!左)" if cn == "右边距" else "")
            mm = re.search(pre + cn + r"[^0-9]{0,10}([\d.]+)\s*(cm|mm|in|厘米|毫米)", line)
            if mm:
                u = {"厘米": "cm", "毫米": "mm"}.get(mm.group(2), mm.group(2))
                for en in ens: out.append(it("page.margin_" + en, cn, float(mm.group(1)), u, src, i))
        m2 = re.search(r"(A4|B5|Letter)\b", line)
        if m2 and ("纸" in line or "page" in low or "size" in low):
            out.append(it("page.size", "page size", m2.group(1), "", src, i))
        fkey = "body.font_size" if ("正文" in line or "body" in low) else "font_size@%d" % i
        if "字" in line or "font" in low or "正文" in line:
            for zh in sorted(CN, key=len, reverse=True):
                if re.search((r"(?<!小)" if not zh.startswith("小") else "") + zh, line):
                    out.append(it(fkey, "Chinese font size name", zh, "=%gpt" % CN[zh], src, i)); break
            mm = re.search(r"(\d+(?:\.\d+)?)\s*(pt|磅)", line)
            if mm: out.append(it(fkey, "font size", float(mm.group(1)), "pt", src, i))
        m4 = re.search(r"([\d.]+)\s*倍行距", line) or re.search(r"([\d.]+)[- ]line[- ]spaced", low)
        if m4: out.append(it("body.line_spacing", "line spacing", float(m4.group(1)), "x", src, i))
        if "双倍行距" in line or "double-spaced" in low: out.append(it("body.line_spacing", "line spacing", 2.0, "x", src, i))
        if "双栏" in line or re.search(r"(two|double)[- ]column", low): out.append(it("page.columns", "columns", 2, "", src, i))
        elif "单栏" in line or re.search(r"(one|single)[- ]column", low): out.append(it("page.columns", "columns", 1, "", src, i))
        m5 = re.search(r"(?:不超过|至多|within|max(?:imum)?)\s*(\d+)\s*(页|pages?)", line, re.I)
        if m5: out.append(it("page.count", "page limit", int(m5.group(1)), "pages", src, i))
        if re.search(REF, line, re.I) and re.search(r"参考文献|references|bibliograph|引用|citation", line, re.I):
            out.append(it("refs.style", "reference style", re.search(REF, line, re.I).group(1), "", src, i))
        if re.search(r"图注|图题|figure caption", line, re.I):
            pos = "below" if re.search(r"下|below", line) else ("above" if re.search(r"上|above", line) else "unspecified")
            out.append(it("caption.figure.position", "figure caption pos", pos, "", src, i))
        if re.search(r"表注|表题|table caption", line, re.I):
            pos = "above" if re.search(r"上|above", line) else ("below" if re.search(r"下|below", line) else "unspecified")
            out.append(it("caption.table.position", "table caption pos", pos, "", src, i))
        if "三线表" in line or "three-line table" in low: out.append(it("table.three_line", "three-line table", True, "", src, i))
    return out, []

def build_spec(a):
    """Parse template/guide files -> spec dict (no I/O side effects). Used by tpl_parse CLI and tpl_fit --guide."""
    items, warnings, vers, pkgs = [], [], [], []
    for path in a:
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext in (".tex", ".cls", ".sty"):
                t = open(path, encoding="utf-8", errors="replace").read()
                i2, w2 = scan_tex(t, path); v2, p2 = scan_meta(t, path); vers += v2; pkgs += p2
            elif ext in (".docx", ".dotx"): i2, w2 = scan_docx(path, path)
            elif ext == ".pdf":
                try:
                    t = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, timeout=60).stdout
                    i2, w2 = scan_text(t, path)
                except Exception as e:
                    i2, w2 = [], ["pdftotext unavailable for %s: %s -- read PDF visually" % (path, e)]
            else: i2, w2 = scan_text(open(path, encoding="utf-8", errors="replace").read(), path)
        except Exception as e:
            i2, w2 = [], ["cannot parse %s: %s" % (path, e)]
        items += i2; warnings += w2
    def norm(x):
        v = str(x["value"])
        if v in CN: return "%g" % CN[v]
        try: return "%g" % float(v)
        except (TypeError, ValueError): return re.sub(r"[^0-9a-z.]", "", v.lower())
    raw = {}
    for x in items:
        raw.setdefault(x["key"], {})[norm(x)] = str(x["value"]) + (" " + str(x["unit"]) if x["unit"] else "")
    conflicts = [{"key": k, "values": sorted(v.values()), "note": "conflict; do NOT silently pick one"}
                 for k, v in raw.items() if len(v) > 1]
    ups = sorted(set(pkgs))
    pkgc = [{"packages": sorted(set(p)), "note": msg} for p, msg in KNOWN.items() if set(p) <= set(ups)]
    if pkgs.count("hyperref") > 1: pkgc.append({"packages": ["hyperref"], "note": "hyperref loaded multiple times (option clash risk)"})
    for n, x in enumerate(items, 1): x["id"] = n
    fps = []
    for f in a:
        try: fps.append({"file": f, "sha256": hashlib.sha256(open(f, "rb").read()).hexdigest()})
        except OSError as e: fps.append({"file": f, "sha256": None, "note": "unreadable: %s" % e})
    if any(x.get("sha256") is None for x in fps) and not any("unreadable" in w for w in warnings):
        warnings.append("template file unreadable -- do NOT invent a spec; fall back to task.md text and record uncertainty")
    return {"files": a, "items": items, "conflicts": conflicts, "warnings": warnings,
            "fingerprints": fps, "versions": vers, "packages": ups, "pkg_conflicts": pkgc}


def main():
    a, out, skip = [], None, False
    for x in sys.argv[1:]:
        if skip: skip = False; continue
        if x == "--out": skip = True; continue
        if not x.startswith("--"): a.append(x)
    if "--out" in sys.argv:
        i = sys.argv.index("--out"); out = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    res = build_spec(a)
    items, conflicts, pkgc = res["items"], res["conflicts"], res["pkg_conflicts"]
    vers, warnings = res["versions"], res["warnings"]
    s = json.dumps(res, ensure_ascii=False, indent=1)
    if out:
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        open(out, "w", encoding="utf-8").write(s)
    print("items=%d conflicts=%d pkg_conflicts=%d versions=%d warnings=%d" %
          (len(items), len(conflicts), len(pkgc), len(vers), len(warnings)), "->", out or "stdout")

if __name__ == "__main__":
    main()
