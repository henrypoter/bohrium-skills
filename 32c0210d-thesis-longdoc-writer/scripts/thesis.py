#!/usr/bin/env python3
"""长文档管线（纯标准库，一致性 advisory 不阻断）。"""
import argparse, glob, json, os, re, subprocess, sys, time

DEFAULT = [
    (1, "摘要", "概括问题/方法/结果/结论", .03, 0),
    (0, "绪论", "背景、研究问题、论文结构", .15, 1),
    (0, "文献综述", "围绕研究问题组织文献", .2, 1),
    (0, "研究方法", "对象/数据/步骤可复现", .2, 1),
    (0, "结果与分析", "按研究问题报告结果", .2, 1),
    (0, "讨论", "解释结果、对话文献、局限", .1, 1),
    (0, "结论与展望", "逐条回答研究问题", .08, 0),
    (1, "参考文献", "只收正文引用且材料存在的条目", 0, 1),
    (1, "附录", "补充材料", .04, 0),
]
PH = "【占位：待写——只用给定材料，缺材料记【缺口】不编造】"
REQUIRED = ["case_id", "status", "status_reason", "deliverables", "source_map",
            "gaps", "review_items", "sources", "uncertainty"]
STATUS = ("success", "partial", "undeterminable", "refused")

def read(p):
    try:
        with open(p, encoding="utf-8", errors="ignore") as f: return f.read()
    except Exception: return ""

def wc(txt):
    """字数：非空白字符数（中文按字计）。"""
    return len(re.sub(r'\s', '', txt))

def min_words(title, budget):
    """篇幅下限：正文章 max(600, 预算×60%)；参考文献/致谢/附录类降为 max(150, 预算//2)。"""
    if any(k in title for k in ("参考文献", "致谢", "附录")):
        return max(150, budget // 2)
    return max(600, int(budget * 0.6))

def dump(p, obj):
    os.makedirs(os.path.dirname(os.path.abspath(p)) or ".", exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

ITEM_RE = re.compile(r'^\s*(?:[-*+]|\d+[.、)]|第[一二三四五六七八九十0-9]+章)\s*(.+?)\s*$')

def parse_outline(task):
    lines = task.splitlines()
    grab, items = False, []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not grab:
            if re.search(r'(提纲|大纲|章节结构|目录)', ln): grab = True
            i += 1; continue
        m = ITEM_RE.match(ln)
        if m: items.append(re.sub(r'^第[一二三四五六七八九十0-9]+章\s*', '', m.group(1)))
        elif re.match(r'^#{1,3}\s', ln):
            if items: break
        elif not ln.strip() and items:
            # 条目间空行不结束提纲：向后看，下一个非空行仍是条目则继续
            j = i + 1
            while j < len(lines) and not lines[j].strip(): j += 1
            if j >= len(lines) or not ITEM_RE.match(lines[j]): break
        i += 1
    if not items:
        m = re.search(r'(?:提纲|大纲|章节结构|目录)[:：]?(.+)', task)
        if m: items = re.findall(r'\d+[.、)]\s*([一-鿿A-Za-z][^0-9，,；;]{0,18}?)(?=\s*\d+[.、)]|$)', m.group(1))
    return [re.sub(r'[#*`]', '', t.strip()) for t in items][:12]

def scan_materials(dirs):
    mats = []
    for d in dirs or []:
        for p in sorted(glob.glob(os.path.join(d, "**", "*"), recursive=True)):
            if os.path.isfile(p) and os.path.splitext(p)[1].lower() in (".md", ".txt", ".tex", ".json", ".csv", ".pdf", ".docx"):
                head = "" if p.lower().endswith((".pdf", ".docx")) else read(p)[:1500]
                mats.append({"path": p, "head": os.path.basename(p) + "\n" + head})
    return mats

def map_materials(ch, mats):
    keys = set(re.findall(r'[一-鿿]{2,4}|[A-Za-z]{4,}', ch["title"] + ch["purpose"]))
    scored = [(sum(1 for k in keys if k in m["head"]), m["path"]) for m in mats]
    return [p for s, p in sorted(scored, key=lambda x: -x[0]) if s > 0][:4]

def ordered(plan): return sorted(plan["chapters"], key=lambda c: c["order"])

def load_plan(wd):
    pj = os.path.join(wd, "plan.json")
    if not os.path.exists(pj): print("MISSING: 先运行 --plan"); sys.exit(2)
    return json.load(open(pj, encoding="utf-8"))

def cmd_plan(a):
    task = read(a.task) if a.task else ""
    m = re.search(r'(\d+(?:\.\d+)?)\s*(万)?\s*字', task)
    total = int(float(m.group(1)) * (10000 if m.group(2) else 1)) if m else 30000
    outline = parse_outline(task)
    os.makedirs(os.path.join(a.workdir, "chapters"), exist_ok=True)
    chapters = []
    if outline:
        per = max(total // len(outline), 500)
        for i, t in enumerate(outline, 1):
            chapters.append({"order": i, "title": t, "purpose": "按task.md提纲撰写本章",
                             "word_budget": per, "need_material": 1, "numbered": 1})
    else:
        for i, (nn, t, pur, ratio, need) in enumerate(DEFAULT, 1):
            chapters.append({"order": i, "title": t, "purpose": pur,
                             "word_budget": int(total * ratio), "need_material": need,
                             "numbered": 0 if nn else 1})
    mats = scan_materials(a.materials)
    for ch in chapters:
        ch["materials"] = map_materials(ch, mats) if ch["need_material"] else []
        ch["gaps"] = [] if (ch["materials"] or not ch["need_material"]) else ["材料未见本章素材"]
        ch["min_words"] = min_words(ch["title"], ch["word_budget"])
        ch["file"] = "chapters/%02d_%s.md" % (ch["order"], re.sub(r'[^\w一-鿿]+', '_', ch["title"])[:20])
        head = "# 第%d章 %s" % (ch["order"], ch["title"]) if ch["numbered"] else "# " + ch["title"]
        body = [head, "", "<!-- budget=%d字 -->" % ch["word_budget"],
                "> 任务：%s。数字/引用/图表只用材料；图N-M/表N-M先引后出连续；缩写首现全称（ABBR）；缺材料记【缺口】。" % ch["purpose"],
                "", PH, ""]
        for g in ch["gaps"]:
            body.append("【缺口：%s；需人工补充，禁编造】" % g)
        with open(os.path.join(a.workdir, ch["file"]), "w", encoding="utf-8") as f:
            f.write("\n".join(body) + "\n")
    plan = {"total_words": total, "min_total_words": total,
            "length_policy": "总字数>=min_total_words；每章>=min_words；禁占位/待补充/本章略",
            "outline_source": "task.md" if outline else "default-thesis",
            "materials_scanned": len(mats), "chapters": chapters}
    dump(os.path.join(a.workdir, "plan.json"), plan)
    print("PLAN OK: %d章/%d字/%s/材料=%d/缺口章=%d" % (len(chapters), total, plan["outline_source"], len(mats), sum(1 for c in chapters if c["gaps"])))
    print("LENGTH POLICY: 总>=%d字；正文章每章>=max(600,预算60%%)，参考文献/附录类>=max(150,预算50%%)；禁占位/待补充/本章略" % total)
    return 0

def cmd_assemble(a):
    plan = load_plan(a.workdir)
    parts, notes, lens = ["# " + (a.title or "论文草稿"), ""], [], []
    for ch in ordered(plan):
        txt = read(os.path.join(a.workdir, ch["file"]))
        if not txt:
            notes.append(ch["file"] + ": 文件缺失")
            parts.append("## %s\n\n【缺口：本章文件缺失，需补写】" % ch["title"]); continue
        n_ph, n_gap = txt.count("【占位"), txt.count("【缺口")
        if n_ph: notes.append(ch["file"] + ": %d处占位未清" % n_ph)
        if n_gap: notes.append(ch["file"] + ": %d处缺口未确认" % n_gap)
        n = wc(txt)
        lens.append((ch, n))
        if n < ch.get("min_words", 0):
            notes.append("SHORT %s: %d/%d字（只补这一章，勿重写他章）" % (ch["file"], n, ch["min_words"]))
        parts.append(txt.strip())
    out = "\n\n".join(parts) + "\n"
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    open(a.out, "w", encoding="utf-8").write(out)
    total, target = wc(out), plan.get("min_total_words") or plan.get("total_words") or 0
    short = [x for x in lens if x[1] < x[0].get("min_words", 0)]
    print("ASSEMBLE OK: %s (总%d字/目标%d字 达标=%s 短章=%d)" % (
        a.out, total, target, "yes" if total >= target else "no", len(short)))
    print("LENGTH: " + " | ".join("%s:%d" % (c["title"], n) for c, n in lens))
    for n in notes[:20]: print(" NOTE:", n)
    if notes: print("ADVISORY=%d（不阻断，照常交付）" % len(notes))
    if a.render:
        return cmd_render(argparse.Namespace(src=a.out, title=a.title, cjk=a.cjk))
    return 0

def cmd_render(a):
    src = a.src or "/app/output/manuscript.md"
    if not os.path.exists(src):
        print("RENDER: 源缺失（跳过）"); return 0
    base, made = os.path.splitext(src)[0], []
    jobs = [("html", ["--metadata", "title=" + (a.title or "论文草稿")]),
            ("docx", []),
            ("pdf", ["--pdf-engine=xelatex", "-V", "CJKmainfont=" + (a.cjk or "Noto Sans CJK SC")])]
    for ext, args in jobs:
        out = base + "." + ext
        try:
            rc = subprocess.run(["pandoc", src, "-o", out] + args,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
        except (FileNotFoundError, OSError): rc = 127
        if rc == 0 and os.path.exists(out) and os.path.getsize(out) > 0: made.append(out)
        else: print("RENDER: 无 %s（跳过）" % ext)
    print("RENDER OK: %s" % (", ".join(made) if made else "仅 Markdown 直出"))
    return 0

def cmd_init(a):
    if os.path.exists(a.out):
        print("EXISTS: 不覆盖"); return 0
    case = {}
    if a.case:
        try: case = json.load(open(a.case, encoding="utf-8"))
        except Exception: print("WARN: case 读取失败")
    r = {k: None for k in REQUIRED}
    r.update({"case_id": case.get("case_id") or case.get("id") or "unknown",
              "status": "partial", "status_reason": "P0 骨架已落盘",
              "deliverables": {}, "source_map": [], "gaps": [], "review_items": [],
              "sources": [], "uncertainty": []})
    oc, n = case.get("output_contract"), 0
    keys = list(oc) if isinstance(oc, dict) else \
        [k if isinstance(k, str) else (k or {}).get("name") for k in oc] if isinstance(oc, list) else []
    for k in keys:
        if k and k not in r: r[k] = None; n += 1
    dump(a.out, r)
    print("INIT OK: %s (%s contract+%d)" % (a.out, r["case_id"], n)); return 0

def cmd_changelog(a):
    if not (a.file and a.rule): print("MISSING: 需 --file 与 --rule"); return 2
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "file": a.file,
           "rule": a.rule, "before": a.before, "after": a.after, "reason": a.reason}
    os.makedirs(os.path.dirname(os.path.abspath(a.log)) or ".", exist_ok=True)
    open(a.log, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("LOG OK"); return 0

def cmd_finalize(a):
    if not os.path.exists(a.out):
        print("MISSING: %s 不存在" % a.out); return 1
    r = json.load(open(a.out, encoding="utf-8"))
    notes = []
    for k in REQUIRED:
        if k not in r: r[k] = None; notes.append("补字段:%s" % k)
    if r.get("status") not in STATUS:
        notes.append("status 非法 %r，置 partial" % r.get("status")); r["status"] = "partial"
    for p in (r.get("deliverables") or {}).values():
        if isinstance(p, str) and p and not os.path.exists(p):
            r.setdefault("uncertainty", []).append("deliverable 缺文件: %s" % p)
    if a.consistency and os.path.exists(a.consistency):
        try:
            rep = json.load(open(a.consistency, encoding="utf-8"))
            for x in (rep.get("issues") or [])[:50]:
                r.setdefault("uncertainty", []).append("[%s] %s:%s %s" % (
                    x.get("severity"), os.path.basename(x.get("file", "")), x.get("line"), x.get("evidence", "")))
        except Exception: pass
    r["finalized_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    dump(a.out, r)
    print("FINALIZE: status=%s notes=%d（不阻断）" % (r["status"], len(notes)))
    for n in notes[:10]: print(" NOTE:", n)
    return 0

def main():
    ap = argparse.ArgumentParser()
    for f in ("plan", "assemble", "render", "init", "changelog", "finalize"):
        ap.add_argument("--" + f, action="store_true")
    ap.add_argument("--task"); ap.add_argument("--materials", nargs="*", default=["/input"])
    ap.add_argument("--workdir", default="/app/work"); ap.add_argument("--out")
    ap.add_argument("--title"); ap.add_argument("--src"); ap.add_argument("--cjk")
    ap.add_argument("--case"); ap.add_argument("--file"); ap.add_argument("--rule")
    ap.add_argument("--before"); ap.add_argument("--after"); ap.add_argument("--reason")
    ap.add_argument("--consistency"); ap.add_argument("--log", default="/app/output/changes.jsonl")
    ap.add_argument("--no-render", action="store_true", help="--assemble 时跳过预览")
    a = ap.parse_args()
    if a.plan: return cmd_plan(a)
    if a.assemble:
        a.out = a.out or "/app/output/manuscript.md"
        a.render = (not a.no_render) if not a.render else True
        return cmd_assemble(a)
    if a.render:
        a.src = a.src or "/app/output/manuscript.md"; return cmd_render(a)
    if a.changelog: return cmd_changelog(a)
    if a.finalize:
        a.out = a.out or "/app/output/result.json"; return cmd_finalize(a)
    if a.init:
        a.out = a.out or "/app/output/result.json"; return cmd_init(a)
    ap.print_help(); return 2

if __name__ == "__main__":
    sys.exit(main())
