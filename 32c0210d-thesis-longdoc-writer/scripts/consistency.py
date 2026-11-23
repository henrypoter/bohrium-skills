#!/usr/bin/env python3
"""跨章节一致性检查 —— 5 条核心规则（纯标准库，advisory：只记 issue/warn，退出码恒 0）。

设计原则：成稿优先。检查器**只报告**，不阻断导出，不要求重写已完成章节；
结果只进 result.json 的 uncertainty。规则只保留三类最核心、最低误杀率的判据：
  引用（cite-missing）/ 图表编号（float-missing, float-number）/ 术语缩写（term-abbr）
外加一条数据分析项 number-unsourced（摘要与结论的数字须见于结果章）。
"""
import argparse, glob, json, os, re, sys

RULES = ["cite-missing", "float-missing", "float-number", "term-abbr", "number-unsourced"]

RE_CAP  = re.compile(r'^\s*(?:\*\*|>\s*)?(图|表)\s*(\d+)\s*[-–.]\s*(\d+)')
RE_FT   = re.compile(r'(图|表)\s*(\d+)\s*[-–.]\s*(\d+)')
RE_ABD  = re.compile(r'([一-鿿][一-鿿·\-]{1,18}?)（([A-Z][A-Za-z0-9]{1,11})）')
RE_ABU  = re.compile(r'(?<![A-Za-z0-9])([A-Z][A-Z0-9]{1,9})(?![A-Za-z0-9])')
RE_CK   = re.compile(r'\[@([A-Za-z0-9_:\-]+)\]|\\cite\{([^}]*)\}|\\bibitem\{([^}]*)\}|@(\w+)\{')
RE_CNUM = re.compile(r'\[(\d{1,3}(?:\s*[-,，]\s*\d{1,3})*)\](?!\()')
RE_BN   = re.compile(r'^\s*\[(\d{1,3})\]\s*\S')
RE_NUM  = re.compile(r'\d+(?:\.\d+)?\s*(?:%|％|ms|mM|mol|kJ|℃|°C|Hz|GB|MB|kPa)')

ABBR_LEAD = ("本文", "本研究", "本工作", "我们", "采用", "基于", "使用", "利用", "通过",
             "提出", "引入", "模型", "方法", "系统", "算法", "技术", "即", "称为", "简称", "是", "为")
ABBR_SKIP = ("OK", "A3", "A4", "GB", "ISO", "NOTE", "PDF", "CPU", "GPU2")


def norm(s):
    return s.replace(" ", "").replace("％", "%").replace("℃", "°C").strip('。，;')


def term(full):
    """剥离全称前的引导动词/主语，使『采用卷积神经网络』与『基于卷积神经网络』归一。"""
    full = full.strip()
    changed = True
    while changed:
        changed = False
        for w in ABBR_LEAD:
            if full.startswith(w) and len(full) > len(w) + 1:
                full = full[len(w):]; changed = True
    return full


def iss(t, sev, f, ln, ev, sug):
    return {"type": t, "severity": sev, "file": f, "line": ln, "evidence": ev, "suggestion": sug}


def kind(p, lines):
    h = os.path.basename(p) + "\n" + next((l for l in lines if l.startswith("#")), "")
    for ks, v in ((("参考文献", "References"), "bib"), (("结果", "实验", "Result"), "result"),
                  (("摘要", "结论", "Abstract", "Conclusion"), "claim")):
        if any(k in h for k in ks): return v
    return "body"


def check(files):
    R = []; order = {p: n for n, (p, _) in enumerate(files)}
    cap, ref = {}, {}          # 题注编号 / 正文引用编号
    abd, abu = {}, {}          # 缩写全称 / 缩写使用
    cited, bibk, bibn, citn = {}, set(), set(), set()
    claims, rt = [], []
    for p, ls in files:
        k = kind(p, ls)
        for i, ln in enumerate(ls, 1):
            c = RE_CAP.match(ln)
            for m in RE_FT.finditer(ln):
                lab = "%s%s-%s" % (m.group(1), m.group(2), m.group(3))
                (cap if c and c.start(1) == m.start(1) else ref).setdefault(lab, []).append((p, i))
            for m in RE_ABD.finditer(ln): abd.setdefault(m.group(2), []).append((m.group(1), p, i))
            for m in RE_ABU.finditer(ln):
                if m.group(1) not in ABBR_SKIP: abu.setdefault(m.group(1), []).append((p, i))
            for m in RE_CK.finditer(ln):
                if m.group(1): cited.setdefault(m.group(1), (p, i))
                elif m.group(2):
                    for kk in m.group(2).split(','): cited.setdefault(kk.strip(), (p, i))
                else: bibk.add((m.group(3) or m.group(4)).strip())
            m = RE_BN.match(ln)
            if m: bibn.add(int(m.group(1)))
            else:
                for m in RE_CNUM.finditer(ln):
                    vals = []
                    for pt in re.split(r'[,，]', m.group(1)):
                        vals += [int(x) for x in pt.split('-', 1)] if '-' in pt else [int(pt)]
                    if 0 in vals: continue      # [0,1] 等区间记号，非文献引用
                    for pt in re.split(r'[,，]', m.group(1)):
                        if '-' in pt:
                            a, b = pt.split('-', 1); citn.update(range(int(a), int(b) + 1))
                        else: citn.add(int(pt))
            if k == "claim": claims += [(norm(m.group(0)), p, i) for m in RE_NUM.finditer(ln)]
            if k == "result": rt.append(norm(ln))

    # 1) 引用：正文引用了但文献章没有条目（含「有引用无文献章」）
    if (cited or citn) and not bibk and not bibn:
        p, i = list(cited.values())[0] if cited else ("", 0)
        R.append(iss("cite-missing", "issue", p, i, "有引用但无参考文献条目", "补条目或删引用"))
    for kk, (p, i) in sorted(cited.items()):
        if bibk and kk not in bibk:
            R.append(iss("cite-missing", "issue", p, i, "引用键%s无条目" % kk, "补或删条目"))
    if bibn:
        for n in sorted(citn - bibn):
            R.append(iss("cite-missing", "issue", "", "", "引用[%d]无条目" % n, "补或删条目"))

    # 2) 图表编号：引用了却没有题注 / 同章重号或断号
    for lab in sorted(ref):
        if lab not in cap:
            R.append(iss("float-missing", "issue", *ref[lab][0], "引用了未定义的%s" % lab, "补题注或删引用"))
    for lab in sorted(cap):
        if len(cap[lab]) > 1:
            R.append(iss("float-number", "warn", cap[lab][1][0], cap[lab][1][1],
                         "%s题注重复%d次" % (lab, len(cap[lab])), "重排编号"))
    for pre in "图表":
        per = {}
        for lab in cap:
            if lab.startswith(pre):
                c, _, n = lab[1:].partition('-'); per.setdefault(c, set()).add(int(n))
        for c, ns in per.items():
            sn = sorted(ns)
            for a, b in zip(sn, sn[1:]):
                if b != a + 1:
                    R.append(iss("float-number", "warn", "", "", "%s%s系列%d→%d不连续" % (pre, c, a, b), "查编号"))

    # 3) 术语缩写：多全称 / 先用后定义 / 未给全称
    for ab, locs in sorted(abu.items()):
        if ab in abd:
            fulls = {term(f) for f, _, _ in abd[ab]}
            if len(fulls) > 1:
                R.append(iss("term-abbr", "warn", abd[ab][1][1], abd[ab][1][2],
                             "%s有多个全称:%s" % (ab, "/".join(sorted(fulls))), "统一全称"))
            if (order[locs[0][0]], locs[0][1]) < (order[abd[ab][0][1]], abd[ab][0][2]):
                R.append(iss("term-abbr", "warn", locs[0][0], locs[0][1], "%s先用后定义" % ab, "首现写全称"))
        elif len(locs) >= 2:
            R.append(iss("term-abbr", "warn", locs[0][0], locs[0][1], "%s×%d 未给全称" % (ab, len(locs)), "补全称"))

    # 4) 数据：摘要/结论里的数字须能在结果章找到
    rt = "".join(rt)
    if rt:
        for v, p, i in claims:
            if v not in rt:
                R.append(iss("number-unsourced", "warn", p, i, "结论数字%s未见于结果章" % v, "与结果章核对"))
    return R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapters", nargs="+")
    ap.add_argument("--out", default="/app/output/consistency.json")
    a = ap.parse_args()
    paths = []
    for c in a.chapters:
        paths += sorted(glob.glob(os.path.join(c, "*.md"))) if os.path.isdir(c) else [c]
    files = []
    for p in sorted(set(paths)):
        try:
            with open(p, encoding="utf-8", errors="ignore") as f: files.append((p, f.read().splitlines()))
        except Exception: pass
    R = check(files)
    sev = {"issue": 0, "warn": 0, "info": 0}
    for x in R: sev[x["severity"]] += 1
    rep = {"chapters": [p for p, _ in files], "rules": RULES, "rule_count": len(RULES),
           "summary": sev, "advisory": True,
           "note": "advisory：只报告不阻断，不要求重写已完成章节；结果仅进 uncertainty。",
           "issues": sorted(R, key=lambda x: ({"issue": 0, "warn": 1, "info": 2}[x["severity"]], x["file"], x["line"]))}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f: json.dump(rep, f, ensure_ascii=False, indent=2)
    print("CONSISTENCY(advisory, %d rules): issue=%d warn=%d" % (len(RULES), sev["issue"], sev["warn"]))
    print("NOTICE: 只报告不阻断，照常导出；不要为此重写已完成章节。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
