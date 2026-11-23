#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学术论文写作三合一工具（仅标准库；调预装 pdftotext/pandoc）。
extract: 材料 -> 带 L0001 行号文本 + figure_inventory.json（图表提及）
check:   数值/单位归一化逐字核对；引文双通道（归一化匹配+loc 区间定位）；引用键、章节、
         术语、图表三向核对、overclaim 提示。有 fail 退出码 1。
build:   draft.json -> manuscript.md/.docx + 渲染 PDF + evidence_map.md，合并 result.json。"""
import json, os, re, shutil, subprocess, sys, unicodedata, zipfile

TEXT_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".log"}
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
NUM_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
UNIT_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?)\s*(%|°C|µM|μM|uM|mM|nM|pM|mg|µg|μg|ug|kg|g|mL|µL|μL|uL|L|ms|min|s|h|Hz|kHz|mV|V|mA|A|kPa|Pa|bp|kb|nm|µm|μm|um|mm|cm|fold|cells|CFU)\b")
CITE_RE = re.compile(r"\[@([\w:.\-]+)\]")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
LINE_RE = re.compile(r"^L(\d+)\t?(.*)$")
LOC_RE = re.compile(r"L(\d+)(?:\s*[-–]\s*L?(\d+))?")
FIGREF_RE = re.compile(r"(?:图|表)\s*([0-9０-９]+)|(?:Fig(?:ure)?|Table)\s*\.?\s*([0-9]+)", re.I)
STAT_RE = re.compile(r"p\s*[<＝=]|显著|置信|\bCI\b|significan", re.I)
STRONG = ("证明", "首次", "显著优于", "必然", "因果", "导致", "prove", "demonstrate", "causal")
REQ = ["Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusion", "References"]

def die(msg, code=2):
    print("ERROR: " + msg, file=sys.stderr); sys.exit(code)

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def paragraphs(d):
    for sec in d.get("sections", []):
        for p in sec.get("paragraphs", []):
            yield sec, p

def norm(s):  # 归一化：NFKC + µ/μ 统一 + 连字符换行修复 + 空白折叠
    s = unicodedata.normalize("NFKC", str(s)).replace("µ", "μ").replace("−", "-")
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", s))

# ---------------- extract ----------------
def cmd_extract(src, dst):
    os.makedirs(dst, exist_ok=True)
    manifest, inv = {}, {}
    files = [src] if os.path.isfile(src) else sorted(
        os.path.join(r, f) for r, _, fs in os.walk(src) for f in fs)
    for f in files:
        ext = os.path.splitext(f)[1].lower(); base = os.path.basename(f)
        out = os.path.join(dst, base + ".txt"); lines = None
        if ext in TEXT_EXT:
            lines = open(f, encoding="utf-8", errors="replace").read().splitlines()
        elif ext == ".docx":
            try:
                xml = zipfile.ZipFile(f).read("word/document.xml").decode("utf-8", "replace")
                xml = re.sub(r"<w:(br|tab)[^>]*/>|</w:p>", "\n", xml)
                lines = re.sub(r"<[^>]+>", "", xml).splitlines()
            except Exception as e:
                manifest[base] = "SKIP: docx 解析失败 %s" % e
        elif ext == ".pdf":
            exe = shutil.which("pdftotext")
            if exe:
                subprocess.run([exe, "-layout", f, out], check=False)
                lines = open(out, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(out) else []
            else:
                manifest[base] = "SKIP: 无 pdftotext"
        else:
            manifest[base] = "SKIP: 图片/二进制，由模型直接读取并手工登记"
        if lines is None:
            continue
        with open(out, "w", encoding="utf-8") as w:
            for i, ln in enumerate(lines, 1):
                w.write("L%04d\t%s\n" % (i, ln))
        for i, ln in enumerate(lines, 1):
            for m in FIGREF_RE.finditer(ln):
                inv.setdefault(base, []).append({"ref": m.group(0), "line": "L%04d" % i})
        manifest[base] = "%d 行 -> %s" % (len(lines), out)
    with open(os.path.join(dst, "figure_inventory.json"), "w", encoding="utf-8") as w:
        json.dump(inv, w, ensure_ascii=False, indent=1)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    print("figure_inventory: %d 处图表提及" % sum(map(len, inv.values())))

# ---------------- build ----------------
def render_md(d):
    out = ["# " + d.get("title", "Untitled"), ""]
    if d.get("abstract"):
        out += ["## Abstract", "", d["abstract"], ""]
    for sec in d.get("sections", []):
        out += ["## " + sec["heading"], ""]
        for p in sec.get("paragraphs", []):
            out += [p["text"], ""]
    for f in d.get("figures", []):
        out += ["**Figure %s.** %s（来源: %s）" % (f.get("id", "?"),
                f.get("caption") or "[CAPTION-MISSING: 材料未提供图注，待作者补写]", f.get("source", "?")), ""]
    if d.get("citations"):
        out += ["## References", ""]
        for k, c in d["citations"].items():
            out.append("- [%s] %s (%s). %s.%s" % (k, c.get("authors", "?"), c.get("year", "?"),
                       c.get("journal", ""), (" DOI: " + c["doi"]) if c.get("doi") else ""))
    if d.get("data_availability"):
        out += ["## Data Availability", "", d["data_availability"], ""]
    return "\n".join(out) + "\n"

def render_evmap(d):
    out = ["# 证据映射表（自动生成，供逐条复核）", ""]
    for sec in d.get("sections", []):
        out.append("## " + sec.get("heading", "?"))
        for i, p in enumerate(sec.get("paragraphs", []), 1):
            out.append("- [P%d][%s/%s] %s" % (i, p.get("kind", "fact"), p.get("strength", "-"),
                                              p.get("text", "")[:60].replace("\n", " ")))
            for e in p.get("evidence", []):
                out.append("  - 材料 %s %s：「%s」" % (e["material"], e.get("loc", "?"),
                           str(e.get("quote", ""))[:50].replace("\n", " ")) if e.get("material")
                           else "  - 文献 %s" % e.get("citation", "?"))
        out.append("")
    if d.get("figures"):
        out += ["## 图表清单"] + ["- 图/表 %s：%s（来源: %s）" % (f.get("id", "?"),
                f.get("caption") or "[CAPTION-MISSING]", f.get("source", "?")) for f in d["figures"]]
    return "\n".join(out) + "\n"

def pandoc_out(md_path, out_path, extra):  # pandoc 转 docx/pdf；含 CJK 时 pdf 用 xelatex
    exe = shutil.which("pandoc")
    if not exe:
        return "no-pandoc: 用 latex-compiler/office-renderer 渲染 manuscript.md"
    try:
        r = subprocess.run([exe, md_path, "-o", out_path] + extra,
                           capture_output=True, text=True, timeout=120)
        return "ok" if r.returncode == 0 and os.path.exists(out_path) else "pandoc-failed: " + (r.stderr or "")[-200:]
    except Exception as e:
        return "pandoc-error: %s" % e

def cmd_build(draft_path, outdir):
    d = load(draft_path)
    os.makedirs(outdir, exist_ok=True)
    md_path = os.path.join(outdir, "manuscript.md"); ev_path = os.path.join(outdir, "evidence_map.md")
    for path, content in [(md_path, render_md(d)), (ev_path, render_evmap(d))]:
        with open(path, "w", encoding="utf-8") as w:
            w.write(content)
    docx_status = pandoc_out(md_path, os.path.join(outdir, "manuscript.docx"), [])
    cjk = any(ord(c) > 0x2E7F for c in open(md_path, encoding="utf-8").read())
    extra = ["--pdf-engine=xelatex", "-V", "CJKmainfont=Noto Sans CJK SC"] if cjk else ["--pdf-engine=pdflatex"]
    pdf_status = pandoc_out(md_path, os.path.join(outdir, "manuscript.pdf"), extra)
    if pdf_status != "ok" and cjk:  # 字体缺失时退化
        pdf_status = pandoc_out(md_path, os.path.join(outdir, "manuscript.pdf"), ["--pdf-engine=xelatex"])
    rp = os.path.join(outdir, "result.json")
    res = load(rp) if os.path.exists(rp) else {}
    res.setdefault("case_id", d.get("meta", {}).get("case_id", "UNKNOWN"))
    res.update({"status": d.get("meta", {}).get("status", "partial"),
        "outputs": {"manuscript_md": md_path,
                    "manuscript_docx": os.path.join(outdir, "manuscript.docx") if docx_status == "ok" else None,
                    "manuscript_pdf": os.path.join(outdir, "manuscript.pdf") if pdf_status == "ok" else None,
                    "evidence_map": ev_path, "draft": draft_path},
        "sources": d.get("sources", []), "uncertainty": d.get("uncertainty", []),
        "change_log": d.get("change_log", []), "human_review": d.get("human_review", []),
        "pdf_status": pdf_status, "docx_status": docx_status})
    if os.path.exists("/input/case.json"):
        try:
            cjd = load("/input/case.json")
            if res.get("case_id") in (None, "UNKNOWN"):
                res["case_id"] = cjd.get("case_id") or cjd.get("id") or "UNKNOWN"
            oc = cjd.get("output_contract", {})
            if isinstance(oc, dict):
                for k in oc:
                    res.setdefault(k, None)
                missing = [k for k in oc if res.get(k) in (None, "", [])]
                if missing:
                    res["uncertainty"].append("output_contract 字段未填全: " + ",".join(missing))
        except Exception as e:
            res.setdefault("errors", []).append("case.json 读取失败: %s" % e)
    with open(rp, "w", encoding="utf-8") as w:
        json.dump(res, w, ensure_ascii=False, indent=1)
    print("built md/evidence_map | pdf=%s | docx=%s | result.json 已更新" % (pdf_status, docx_status))

# ---------------- check ----------------
def load_materials(mdir):  # {材料基名: [(行号, 原文)]}，来自 extract 产物
    mats = {}
    if mdir and os.path.isdir(mdir):
        for fn in os.listdir(mdir):
            if fn.endswith(".txt"):
                lines = [(int(m.group(1)), m.group(2)) for ln in
                         open(os.path.join(mdir, fn), encoding="utf-8", errors="replace")
                         for m in [LINE_RE.match(ln.rstrip("\n"))] if m]
                if lines:
                    mats[fn[:-4]] = lines
    return mats

def seg_text(lines, a=None, b=None):
    return norm("\n".join(t for n, t in lines if a is None or a <= n <= b))

def cmd_check(draft_path, report_path, mdir=None):
    d = load(draft_path); mats = load_materials(mdir); items = []

    def add(lv, ck, msg):
        items.append({"level": lv, "check": ck, "msg": msg})

    heads = [s.get("heading", "").lower() for s in d.get("sections", [])]
    if d.get("abstract"):
        heads.append("abstract")
    for h in d.get("required_sections", REQ):
        if h.lower() == "references":
            if not d.get("citations"):
                add("fail", "sections", "缺少 References/参考文献条目")
        elif not any(h.lower() in x for x in heads):
            add("fail", "sections", "缺少必需章节: " + h)

    def quote_channel(e):  # 双通道：归一化匹配 + loc 源区间定位
        name = os.path.basename(str(e.get("material", "")))
        if not mats:
            return
        if name not in mats:
            add("fail", "quote", "材料 %s 不在 extract 产物中" % name); return
        lines = mats[name]; m = LOC_RE.search(str(e.get("loc", ""))); a = b = None
        if m:
            a, b = int(m.group(1)), int(m.group(2) or m.group(1))
            if a > b or a < lines[0][0] or b > lines[-1][0]:
                add("fail", "quote", "区间 %s 超出材料 %s 行范围" % (e.get("loc"), name))
        else:
            add("warn", "quote", "证据 %s 缺 loc 区间" % name)
        frags = [f for f in (norm(x) for x in str(e.get("quote", "")).split("\n")) if f]
        if not frags:
            return
        whole = seg_text(lines)

        def found(f, hay):  # 片段级匹配；容忍 quote 侧连字符断词
            return f in hay or (f.endswith("-") and f[:-1] in hay)

        if a is None:
            bad = [f for f in frags if not found(f, whole)]
        else:
            seg = seg_text(lines, a, b)
            bad = [f for f in frags if not found(f, seg)]
            if bad and all(found(f, whole) for f in bad):
                add("fail", "quote", "引文片段不在所标区间 %s（%s 位置错配）" % (e.get("loc"), name))
                return
        if bad:
            add("fail", "quote", "引文片段未在材料 %s 找到: %s" % (name, bad[0][:30]))

    for sec, p in paragraphs(d):
        ev = p.get("evidence", []); hd = sec.get("heading", "?")
        if not ev:
            add("warn" if p.get("kind") == "comment" else "fail", "evidence",
                "[%s] 论断无证据绑定: %s..." % (hd, p.get("text", "")[:40])); continue
        quotes = norm(" \n".join(str(e.get("quote", "")) for e in ev))
        for e in ev:
            if not (e.get("material") or e.get("citation")):
                add("fail", "evidence", "证据未指向材料或文献: " + str(e)[:60])
            if e.get("material") and e.get("quote"):
                quote_channel(e)
        unit_nums = set()
        for m in UNIT_RE.finditer(p.get("text", "")):
            unit_nums.add(m.group(1))
            if norm(m.group(0)) not in quotes:
                add("fail", "numeric", "数值+单位「%s」未在证据引文中出现（%s）" % (m.group(0), hd))
        for m in NUM_RE.finditer(p.get("text", "")):
            tok = m.group(0)
            if not (YEAR_RE.match(tok) or tok in unit_nums) and norm(tok) not in quotes:
                add("fail", "numeric", "数值 %s 未在证据引文中出现（%s）" % (tok, hd))
        if p.get("kind") != "comment":  # overclaim 机器提示
            t = p.get("text", ""); hit = [w for w in STRONG if w.lower() in t.lower()]
            if hit and p.get("strength") != "hedged" and not STAT_RE.search(t + " " + quotes):
                add("warn", "overclaim", "[%s] 强论断词「%s」无统计标记（overclaim 风险）" % (hd, hit[0]))

    cites = d.get("citations", {}); used = set(CITE_RE.findall(d.get("abstract", "")))
    for sec, p in paragraphs(d):
        used |= set(CITE_RE.findall(p.get("text", "")))
    for k in sorted(used):
        if k not in cites:
            add("fail", "citation", "正文引用未定义文献键: " + k)
    for k, c in cites.items():
        if k not in used:
            add("warn", "citation", "文献 %s 未被正文引用（装饰性引用?）" % k)
        for fld in ("authors", "year", "journal"):
            if not c.get(fld):
                add("fail", "citation", "文献 %s 缺字段 %s" % (k, fld))
        if c.get("doi") and not DOI_RE.match(str(c["doi"])):
            add("warn", "citation", "文献 %s DOI 格式可疑: %s" % (k, c["doi"]))

    full_text = d.get("abstract", "") + "\n" + "\n".join(p.get("text", "") for _, p in paragraphs(d))
    for abbr, full in d.get("terms", {}).items():
        if abbr in full_text and full in full_text and ("%s (%s)" % (full, abbr)) not in full_text:
            add("warn", "terms", "缩写 %s 未按「全称 (缩写)」首次定义" % abbr)

    # 图表三向核对：材料 ↔ figures 清单 ↔ 正文引用
    figs = {str(f.get("id", "?")): f for f in d.get("figures", [])}; used_fig = set()
    for sec, p in paragraphs(d):
        for m in FIGREF_RE.finditer(p.get("text", "")):
            num = unicodedata.normalize("NFKC", m.group(1) or m.group(2)); used_fig.add(num)
            if num not in figs:
                add("fail", "figures", "正文引用「%s」不在 figures 清单（错位/缺项）" % m.group(0).strip())
    for fid, f in figs.items():
        if fid not in used_fig:
            add("warn", "figures", "图/表 %s 在清单中但正文未引用" % fid)
        if not f.get("caption"):
            add("fail", "figures", "图 %s 缺图注（须标注缺口，禁止编造）" % fid)
        elif f.get("caption_missing_in_source"):
            add("warn", "figures", "图 %s 图注为补写，需人工确认" % fid)
        src = re.match(r"(\S+)\s+(L\d+(?:\s*[-–]\s*L?\d+)?)", str(f.get("source", "")))
        if mats and f.get("caption") and src and os.path.basename(src.group(1)) in mats:
            m = LOC_RE.search(src.group(2)); lines = mats[os.path.basename(src.group(1))]
            seg = seg_text(lines, int(m.group(1)), int(m.group(2) or m.group(1))) if m else seg_text(lines)
            for t in NUM_RE.finditer(f["caption"]):
                if not YEAR_RE.match(t.group(0)) and norm(t.group(0)) not in seg:
                    add("fail", "figures", "图 %s 图注数值 %s 未在来源 %s 出现" % (fid, t.group(0), f.get("source")))
    invp = os.path.join(mdir, "figure_inventory.json") if mdir else None
    if invp and os.path.exists(invp):
        for base, lst in load(invp).items():
            for it in lst:
                nm = re.search(r"[0-9]+", unicodedata.normalize("NFKC", it["ref"]))
                if nm and nm.group(0) not in figs:
                    add("warn", "figures", "材料 %s %s 的「%s」未登记进 figures 清单" % (base, it["line"], it["ref"]))

    nfail = sum(1 for i in items if i["level"] == "fail")
    rep = {"fails": nfail, "warns": sum(1 for i in items if i["level"] == "warn"),
           "infos": sum(1 for i in items if i["level"] == "info"), "items": items}
    if report_path:
        with open(report_path, "w", encoding="utf-8") as w:
            json.dump(rep, w, ensure_ascii=False, indent=1)
    print("check: %d fail / %d warn / %d info%s" % (nfail, rep["warns"], rep["infos"],
          (" -> " + report_path) if report_path else ""))
    for i in items:
        if i["level"] == "fail":
            print("  FAIL [%s] %s" % (i["check"], i["msg"]))
    sys.exit(1 if nfail else 0)

def main():
    a = sys.argv[1:]
    if not a:
        die(__doc__)
    cmd = a[0]

    def opt(name, default=None):
        return a[a.index(name) + 1] if name in a else default

    if cmd == "extract":
        if not (opt("--src") and opt("--dst")):
            die("extract --src <文件或目录> --dst <work目录>")
        cmd_extract(opt("--src"), opt("--dst"))
    elif cmd == "build":
        if not opt("--draft"):
            die("build --draft draft.json [--outdir /app/output]")
        cmd_build(opt("--draft"), opt("--outdir", "/app/output"))
    elif cmd == "check":
        if not opt("--draft"):
            die("check --draft draft.json [--report r.json] [--materials <extract目录>]")
        cmd_check(opt("--draft"), opt("--report"), opt("--materials"))
    else:
        die("未知子命令: " + cmd)


if __name__ == "__main__":
    main()
