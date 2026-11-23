#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开题写作辅助脚本 v2（仅标准库，Python>=3.8）。
init 解析 case/task 抽取文献[R#]/前期基础[P#]/周期/经费/事实行并生成八章骨架；gantt 生成带 RQ 列的甘特表；
check 结构/引用防编造/缺口↔RQ 双向映射/[P#]绑定/进度↔RQ 覆盖/禁用词；finalize 写 result.json 与证据台账。
"""
import argparse, json, os, re, shutil, sys

SECTIONS = [
    ("背景", ["选题背景与意义", "研究背景"]),
    ("综述", ["文献综述", "研究现状"]),
    ("问题", ["研究问题与目标", "研究问题"]),
    ("内容方法", ["研究内容与方法", "研究内容"]),
    ("路线", ["技术路线"]),
    ("创新", ["创新点", "特色与创新"]),
    ("进度", ["进度安排", "阶段计划"]),
    ("成果", ["预期成果", "预期结果"]),
]
DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.I)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
PRIOR_RE = re.compile(r"前期(实验|研究|工作|数据|基础)|预实验|已(发表|合成|完成|建立|采集|获得|开发)|本课题组|团队已|pilot", re.I)
GAP_RE = re.compile(r"缺口\s*G\s*(\d+)")
RQ_RE = re.compile(r"RQ\s*[-_]?\s*(\d+)", re.I)
CLAIM_RE = re.compile(r"前期(实验|研究|工作)|本课题组|申请人已|我们已|预实验")
BANNED = ["国际领先", "国内领先", "世界领先", "首创", "首次提出", "填补空白", "重大突破", "原创性"]
FREE_TAGS = ("公共", "管理", "-")

def load_texts(case_path, task_path):
    rows = []  # [(来源路径, 行)]，递归展开 case.json 所有字符串
    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, "%s.%s" % (path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))
        elif isinstance(node, str):
            for ln in node.splitlines():
                if ln.strip():
                    rows.append((path, ln.strip()))
        elif isinstance(node, (int, float)):
            rows.append((path, str(node)))
    if case_path and os.path.exists(case_path):
        raw = open(case_path, encoding="utf-8", errors="replace").read()
        try:
            walk(json.loads(raw), "case")
        except json.JSONDecodeError:
            for i, ln in enumerate(raw.splitlines()):
                if ln.strip():
                    rows.append(("case.line%d" % i, ln.strip()))
    if task_path and os.path.exists(task_path):
        for i, ln in enumerate(open(task_path, encoding="utf-8", errors="replace")):
            if ln.strip():
                rows.append(("task.line%d" % i, ln.strip()))
    return rows

def cmd_init(a):
    rows = load_texts(a.case, a.task)
    os.makedirs(a.work, exist_ok=True)
    refs, priors, seen = [], [], set()
    for src, ln in rows:  # 文献：含 DOI 或 (作者+年份+标点) 的行
        if len(ln) < 12:
            continue
        key = re.sub(r"\s+", " ", ln)[:120]
        if key in seen:
            continue
        if DOI_RE.search(ln) or (YEAR_RE.search(ln) and re.search(r"[A-Za-z一-鿿]{2,}", ln)
                                 and re.search(r"[，,。.．]|et\s+al|等", ln)):
            seen.add(key)
            refs.append({"id": "R%d" % (len(refs) + 1), "text": ln, "source": src})
        elif len(priors) < 20 and PRIOR_RE.search(ln):  # 前期基础[P#]清单
            seen.add(key)
            priors.append({"id": "P%d" % (len(priors) + 1), "text": ln, "source": src})
    blob = "\n".join(ln for _, ln in rows)
    months = None
    m = re.search(r"(\d{1,3})\s*(?:个)?月", blob) or re.search(r"(\d(?:\.\d)?)\s*年", blob)
    if m:
        months = int(float(m.group(1)) * (1 if "月" in m.group(0) else 12))
    m = re.search(r"(\d+(?:\.\d+)?)\s*万(?:元)?", blob)
    budget = m.group(1) + "万元" if m else None
    facts = [{"source": s, "text": l} for s, l in rows if re.search(r"\d", l)][:60]
    case_id = "unknown"
    if a.case and os.path.exists(a.case):
        try:
            cj = json.load(open(a.case, encoding="utf-8", errors="replace"))
            if isinstance(cj, dict):
                case_id = str(cj.get("case_id") or cj.get("id") or "unknown")
        except Exception:
            pass
    json.dump({"case_id": case_id, "duration_months": months, "budget": budget,
               "refs": refs, "priors": priors, "facts": facts},
              open(os.path.join(a.work, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    guide = {
        "背景": "收束到缺口并编号缺口G1..；前期工作挂[P#]",
        "综述": "主题式2~4段：已知/争议/缺口Gx；引用[n]",
        "问题": "RQ1..（1~3个可证伪），各注明回应缺口Gx",
        "内容方法": "每RQ一内容块：方法/输入/输出/依据[n][P#]",
        "路线": "步骤→输入→输出→依赖；标关键路径",
        "创新": "差异陈述：相比[n]的X在Y维度不同；禁最高级词",
        "进度": "gantt生成：任务@RQx:起:止；止月<=周期",
        "成果": "与RQ对应的可考核成果（无依据写[待确认]）",
    }
    skel = ["# 开题报告（骨架，按 SKILL.md 填写）\n"]
    for i, (name, kws) in enumerate(SECTIONS, 1):
        skel.append("\n## %d. %s\n\n<!-- %s -->\n" % (i, kws[0], guide[name]))
    skel.append("\n## 9. 风险与备选方案\n\n<!-- 数据/方法/进度/伦理四类，各写触发信号与备选方案 -->\n")
    skel.append("\n## 参考文献（只列材料中出现的条目，逐字照录）\n")
    for r in refs:
        skel.append("[%s] %s\n" % (r["id"][1:], r["text"]))
    open(os.path.join(a.work, "skeleton.md"), "w", encoding="utf-8").write("".join(skel))
    print("init ok: refs=%d priors=%d months=%s budget=%s"
          % (len(refs), len(priors), months, budget))

def cmd_gantt(a):
    tasks = []
    for it in a.items.split(";"):
        m = re.match(r"^(.+)@([^:@\s]+):(\d{1,3}):(\d{1,3})$", it.strip())
        if not m:
            sys.exit("格式须为 任务@RQx:起:止（非研究任务@公共），出错项: %s" % it)
        name, tag, s, e = m.group(1).strip(), m.group(2).strip(), int(m.group(3)), int(m.group(4))
        if not (1 <= s <= e <= a.months):
            sys.exit("任务 %s 月份越界(1..%d)" % (name, a.months))
        tasks.append((name, tag, s, e))
    w = max(4, max(len(t[0]) for t in tasks))
    head = ("| 任务%s | RQ | 起 | 止 |" % (" " * (w - 2))) + "".join("%d|" % (x % 10) for x in range(1, a.months + 1))
    lines = [head, "|" + "---|" * (4 + a.months)]
    for name, tag, s, e in tasks:
        bar = "".join("#" if s <= x <= e else "." for x in range(1, a.months + 1))
        lines.append("| %s%s | %s | %d | %d |%s|" % (name, " " * (w - len(name)), tag, s, e, bar))
    print("\n".join(lines))

def _spans(draft):
    heads = [(m.start(), m.group(0)) for m in re.finditer(r"(?m)^#{1,4}.*$", draft)]
    spans = {}
    for i, (pos, h) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(draft)
        for name, kws in SECTIONS:
            if any(k in h for k in kws):
                spans.setdefault(name, draft[pos:end])
    return spans

def _rq_blocks(sec):  # 问题章每个 RQ 的文本块
    ms = list(RQ_RE.finditer(sec))
    out = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(sec)
        out.setdefault(m.group(1), sec[m.start():end])
    return out

def cmd_check(a):
    draft = open(a.draft, encoding="utf-8", errors="replace").read()
    meta = json.load(open(os.path.join(a.work, "meta.json"), encoding="utf-8"))
    refs, priors = meta["refs"], meta.get("priors", [])
    issues, gaps = [], []
    spans = _spans(draft)
    present = {}
    for name, kws in SECTIONS:
        ok = name in spans or any(k in draft for k in kws)
        present[name] = ok
        if not ok:
            issues.append("缺章节: %s" % kws[0])
    # 1 引用防编造
    n = len(refs)
    for num in sorted(set(int(x) for x in re.findall(r"\[(\d{1,3})\]", draft))):
        if num > n:
            issues.append("引用[%d]越界（材料仅%d篇，疑似编造）" % (num, n))
    refblob = " ".join(r["text"] for r in refs)
    for au, yr in set(re.findall(r"[（(]([A-Za-z一-鿿][\w一-鿿·]*(?:\s+et\s+al\.?|等)?)[,， ]*\s*((?:19|20)\d{2})[）)]", draft)):
        if not (re.search(r"[A-Za-z]", au) or au.endswith("等")):
            continue  # 非引用括注（如“（预计 2027）”）不误杀；纯中文名(无"等")不校验作者-年份
        if yr not in refblob or au.split()[0][:4] not in refblob:
            issues.append("引用(%s,%s)不在材料中，疑似编造" % (au, yr))
    if n < 3:
        gaps.append("材料文献仅%d篇，难撑主题式综述" % n)
    # 2 缺口↔RQ 双向映射
    gdefs = set(GAP_RE.findall(draft))
    rqsec = spans.get("问题", "")
    blocks = _rq_blocks(rqsec)
    rqs = sorted(set(RQ_RE.findall(draft)) | set(re.findall(r"研究问题\s*(\d+)", draft)), key=int)
    if not gdefs:
        issues.append("未编号化缺口（综述/背景须写“缺口G1…”），映射无法校验")
    for g in sorted(gdefs - set(re.findall(r"G\s*(\d+)", rqsec)), key=int):
        issues.append("孤儿缺口G%s：无RQ承接" % g)
    for q in rqs:
        gq = set(re.findall(r"G\s*(\d+)", blocks.get(q, "")))
        if rqsec and not gq:
            issues.append("孤儿RQ%s：未注明回应的缺口Gx" % q)
        for g in sorted(gq - gdefs, key=int):
            issues.append("RQ%s引用未定义缺口G%s" % (q, g))
    if not rqs:
        issues.append("未发现编号化研究问题RQ1..")
    elif len(rqs) > 4:
        issues.append("研究问题%d个，超出1~4合理体量" % len(rqs))
    # 3 RQ 方法/成果闭环
    cm, oc = spans.get("内容方法", ""), spans.get("成果", "")
    for q in rqs:
        pats = ["RQ%s" % q, "RQ-%s" % q, "研究问题%s" % q]
        if not any(p in cm for p in pats):
            issues.append("RQ%s未在“内容与方法”闭环" % q)
        if not any(p in oc for p in pats):
            issues.append("RQ%s未在“预期成果”闭环" % q)
    # 4 前期基础[P#]绑定
    np_ = len(priors)
    for num in sorted(set(int(x) for x in re.findall(r"\[P(\d{1,2})\]", draft))):
        if num > np_:
            issues.append("[P%d]越界（前期清单仅%d条，疑似虚构）" % (num, np_))
    heads_all = [(m.start(), m.group(0)) for m in re.finditer(r"(?m)^#{1,4}.*$", draft)]
    risk_ranges = [(pos, heads_all[i + 1][0] if i + 1 < len(heads_all) else len(draft))
                   for i, (pos, h) in enumerate(heads_all) if "风险" in h]
    off = 0
    for ln in draft.splitlines():
        start = off
        off += len(ln) + 1
        if any(s <= start < e for s, e in risk_ranges):
            continue  # 风险章中“预实验样本量偏小”等是风险描述，非前期论断，不误杀
        if CLAIM_RE.search(ln) and "[P" not in ln and "材料缺口" not in ln and "待确认" not in ln:
            issues.append("前期论断未挂[P#]/缺口标注：%s…" % ln.strip()[:20])
    # 5 甘特存在性/越界/进度↔RQ 覆盖
    prog = spans.get("进度", "")
    rows = []
    for ln in prog.splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")] if ln.strip().startswith("|") else []
        if len(cells) >= 4 and cells[2].isdigit() and cells[3].isdigit():
            rows.append((cells[0], cells[1], int(cells[2]), int(cells[3])))
    dmax = meta.get("duration_months")
    if prog and not rows:
        issues.append("进度章缺标准甘特表（gantt子命令生成）")
    covered = set()
    for name, tag, s, e in rows:
        if dmax and e > dmax:
            issues.append("任务「%s」止月%d超周期%d月" % (name, e, dmax))
        tqs = set(RQ_RE.findall(tag))
        covered |= tqs
        if not tqs and tag not in FREE_TAGS:
            issues.append("任务「%s」未挂有效RQ（孤儿任务）" % name)
        for q in sorted(tqs - set(rqs), key=int):
            issues.append("任务「%s」挂在未定义RQ%s" % (name, q))
    if rows:
        for q in sorted(set(rqs) - covered, key=int):
            issues.append("RQ%s无进度任务覆盖" % q)
    if not dmax:
        gaps.append("材料未给出项目周期，进度无法校验")
    # 6 禁用词
    for w in BANNED:
        if w in draft:
            issues.append("禁用词「%s」：改差异陈述" % w)
    if re.search(r"TODO|待补|XXX", draft):
        issues.append("草稿含TODO/占位残留")
    # RQ 闭环矩阵
    matrix = {}
    for q in rqs:
        pats = ["RQ%s" % q, "RQ-%s" % q, "研究问题%s" % q]
        matrix["RQ" + q] = {
            "gaps": sorted(set(re.findall(r"G\s*(\d+)", blocks.get(q, ""))), key=int),
            "in_content": any(p in cm for p in pats),
            "in_outcome": any(p in oc for p in pats),
            "tasks": [nm for nm, tg, _, _ in rows if q in RQ_RE.findall(tg)],
        }
    report = {"passed": not issues, "issues": issues, "gaps": gaps,
              "sections_present": present, "rqs": rqs, "n_refs": n,
              "n_priors": np_, "matrix": matrix}
    out = os.path.join(a.work, "check_report.json")
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))

def cmd_finalize(a):
    meta = json.load(open(os.path.join(a.work, "meta.json"), encoding="utf-8"))
    chk_p = os.path.join(a.work, "check_report.json")
    chk = json.load(open(chk_p, encoding="utf-8")) if os.path.exists(chk_p) else \
        {"passed": False, "issues": ["未运行 check"], "gaps": [], "sections_present": {}}
    notes = {}
    nt = os.path.join(a.work, "notes.json")
    if os.path.exists(nt):
        notes = json.load(open(nt, encoding="utf-8"))
    os.makedirs(a.out, exist_ok=True)
    shutil.copy(a.draft, os.path.join(a.out, "proposal.md"))
    if os.path.exists(chk_p):
        shutil.copy(chk_p, os.path.join(a.out, "check_report.json"))
    sources = notes.get("sources") or [
        {"claim": "引用 %s" % r["id"], "source": r["source"], "location": "参考文献"} for r in meta["refs"]]
    gaps = list(dict.fromkeys(chk.get("gaps", []) + notes.get("gaps", [])))
    status = notes.get("status") or ("complete" if chk.get("passed") and not gaps else "partial")
    led = ["# 证据台账\n\n## 文献证据 [R#]\n"]
    for r in meta["refs"]:
        led.append("- [%s] %s（来源：%s）\n" % (r["id"], r["text"], r["source"]))
    led.append("\n## 前期基础 [P#]\n")
    if meta.get("priors"):
        for p in meta["priors"]:
            led.append("- [%s] %s（来源：%s）\n" % (p["id"], p["text"], p["source"]))
    else:
        led.append("- 材料无前期基础清单；相关论断须标【材料缺口】，禁止虚构\n")
    led.append("\n## 论断-来源映射\n")
    for s in sources:
        led.append("- %s ← %s（%s）\n" % (s.get("claim", ""), s.get("source", ""), s.get("location", "")))
    open(os.path.join(a.out, "evidence_ledger.md"), "w", encoding="utf-8").write("".join(led))
    result = {
        "case_id": meta.get("case_id", "unknown"),
        "status": status,
        "deliverables": {"proposal_md": "proposal.md", "check_report": "check_report.json",
                         "evidence_ledger": "evidence_ledger.md"},
        "sections_present": chk.get("sections_present", {}),
        "sources": sources,
        "uncertainty": notes.get("uncertainty", []),
        "gaps": gaps,
        "change_log": notes.get("change_log", []),
        "checks": {"passed": chk.get("passed", False), "issues": chk.get("issues", []),
                   "matrix": chk.get("matrix", {})},
    }
    p = os.path.join(a.out, "result.json")
    json.dump(result, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("finalize ok: status=%s -> %s" % (status, p))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--case"); p.add_argument("--task")
    p.add_argument("--work", default="/app/work"); p.set_defaults(f=cmd_init)
    p = sub.add_parser("gantt"); p.add_argument("--months", type=int, required=True)
    p.add_argument("--items", required=True)
    p.set_defaults(f=cmd_gantt)
    p = sub.add_parser("check"); p.add_argument("--work", default="/app/work")
    p.add_argument("--draft", required=True); p.set_defaults(f=cmd_check)
    p = sub.add_parser("finalize"); p.add_argument("--work", default="/app/work")
    p.add_argument("--draft", required=True); p.add_argument("--out", default="/app/output")
    p.set_defaults(f=cmd_finalize)
    a = ap.parse_args()
    a.f(a)

if __name__ == "__main__":
    main()
