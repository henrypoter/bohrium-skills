#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基金申请书七要素工具 v3（仅标准库）。init=证据台账(S#/P#)+骨架+矩阵+partial result.json（幂等）；
check=引文覆盖/创新点禁用词与锚定/缺口↔研究内容双向映射/[S#][P#]越界/章节齐全/要素对齐/待补充；
pack=打包+回填 used_in。自测：python3 bench/bench_run.py（正向零误杀+变异必命中）。"""
import argparse, csv, json, re, sys, time
from pathlib import Path

BANNED = ["首次", "国际领先", "国内领先", "世界领先", "填补空白", "世界首创", "国内首创", "重大突破", "原创性"]
FILL = re.compile(r"填补[^，。；]{0,6}空白")
CUE = re.compile(r"(表明|显示|证明|报道|达到|提升至|降低至|\d+(\.\d+)?\s*(%|倍|℃|K|nm|mm|MPa|GPa|篇|项))")
EREF = re.compile(r"\[[SP]\d+\]")
PREF = re.compile(r"\[P\d+\]")
GAP_RE = re.compile(r"缺口\s*G\s*(\d+)")
CONT_ITEM = re.compile(r"(?m)^\s*(?:[-*]\s*)?C(\d+)\b")
INNO_ITEM = re.compile(r"创新点\s*(\d+)")
PRIOR = re.compile(r"前期|本课题组|申请人(?:已|团队)|已(?:发表|制备|建立|获得|合成|采集|完成|开发|建成)|预实验")

def load_case(p):
    try:
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {"materials": d}
    except Exception as e:
        return {"_parse_error": str(e)}

def walk_texts(obj, prefix="case.json"):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items(): out += walk_texts(v, f"{prefix}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj): out += walk_texts(v, f"{prefix}[{i}]")
    elif isinstance(obj, str) and len(obj.strip()) >= 30:
        out.append((prefix, obj.strip()))
    return out

def classify(path, text):
    p = path.lower()
    if any(w in p for w in ("applicant", "preliminary", "prior", "申请人", "前期", "成果")):
        return "申请人前期基础"
    if re.search(r"(doi|et al|\(\d{4}\)|journal|vol\.)", text, re.I): return "文献"
    return "领域材料"

def section(text, name):
    m = re.search(rf"^#+\s*.*{name}.*$([\s\S]*?)(?=^#+\s|\Z)", text, re.M)
    return m.group(1) if m else ""

def sections_map(text):
    return {n: section(text, n) for n in
            ["立项依据", "科学问题", "研究目标", "研究内容", "技术路线", "创新点", "研究基础", "考核指标"]}

def blocks(sec, mr):
    ms = list(mr.finditer(sec)); out = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(sec)
        out.setdefault(m.group(1), sec[m.start():end])
    return out

def cmd_init(a):
    work, out = Path(a.work), Path(a.out)
    work.mkdir(parents=True, exist_ok=True); out.mkdir(parents=True, exist_ok=True)
    case = load_case(a.case)
    task = Path(a.task).read_text(encoding="utf-8") if Path(a.task).exists() else ""
    texts = walk_texts(case)
    ledger, gaps, ns, np_ = [], [], 0, 0
    if "_parse_error" in case: gaps.append(f"case.json 解析失败: {case['_parse_error']}")
    if not texts: gaps.append("未从 case.json 抽取到有效材料文本")
    for path, text in texts[:60]:
        t = classify(path, text)
        if t == "申请人前期基础": np_ += 1; sid = f"P{np_}"
        else: ns += 1; sid = f"S{ns}"
        ledger.append({"id": sid, "source": path, "type": t, "excerpt": text[:400]})
    (work / "evidence_ledger.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")
    if not ledger or not any(s["type"] == "申请人前期基础" for s in ledger):
        gaps.append("缺少申请人前期成果材料：研究基础与可行性章节须标注【待补充】")
    skel = Path(__file__).resolve().parent.parent / "templates" / "skeleton.md"
    if skel.exists() and not (work / "skeleton.md").exists():
        (work / "skeleton.md").write_text(skel.read_text(encoding="utf-8"), encoding="utf-8")
    if not (work / "matrix.csv").exists():
        with open(work / "matrix.csv", "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows([["goal_id", "content_id", "route_step", "metric"],
                                     ["G1", "", "", ""], ["G2", "", "", ""], ["G3", "", "", ""]])
    cid = str(case.get("case_id") or case.get("id") or "unknown")
    res = {"case_id": cid, "status": "partial",
           "deliverables": {"proposal_sections": None, "route_map": None, "consistency_report": None,
                            "note": "骨架已生成，章节待撰写"},
           "source_mapping": [{"evidence_id": s["id"], "source": s["source"], "type": s["type"], "used_in": []}
                              for s in ledger],
           "version_boundary": {"change_records": ["init: 生成证据台账/骨架/矩阵"], "manual_confirmation": [],
                                "material_gaps": gaps, "conflicts": [], "anomalies": []},
           "sources": [a.case, a.task], "uncertainty": gaps,
           "meta": {"skill": "grant-proposal-writer", "ts": int(time.time()), "task_excerpt": task[:200]}}
    rp = out / "result.json"
    if rp.exists():  # 幂等：复跑不覆盖已交付结果（含 pack 后的 complete 版）
        print(f"init ok: {len(ledger)} 条证据(S{ns}/P{np_})；result.json 已存在，保留不覆盖（幂等）")
        return
    rp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"init ok: {len(ledger)} 条证据(S{ns}/P{np_}) -> {work}; gaps={len(gaps)}")

def cmd_check(a):
    work = Path(a.work)
    dp, sp = work / "draft.md", work / "skeleton.md"
    text = dp.read_text(encoding="utf-8") if dp.exists() else (sp.read_text(encoding="utf-8") if sp.exists() else "")
    secs = sections_map(text)
    rep = ["# 一致性检查报告"]; ok = True
    lines = [l.strip() for l in secs["立项依据"].splitlines() if CUE.search(l) and len(l.strip()) > 8]
    uncited = [l for l in lines if not EREF.search(l)]
    cov = 1.0 if not lines else (len(lines) - len(uncited)) / len(lines)
    rep.append(f"## 1 引文覆盖：{len(lines)} 条论断，未挂来源 {len(uncited)} 条，覆盖率 {cov:.0%}")
    for l in uncited[:10]: rep.append(f"- [缺引] {l[:80]}")
    if uncited: ok = False
    inno = secs["创新点"]
    hits = [w for w in BANNED if w in inno]
    if FILL.search(inno): hits.append("填补空白")
    hits = list(dict.fromkeys(hits))
    rep.append(f"## 2 创新点：禁用词{'命中 ' + '、'.join(hits) if hits else '未命中'}")
    if hits: ok = False
    ib = blocks(inno, INNO_ITEM)
    for k, b in ib.items():
        if not EREF.search(b): rep.append(f"- [锚定] 创新点{k} 未挂对比证据[S#]/[P#]"); ok = False
    if not ib: rep.append("- [缺失] 创新点未编号，无法逐条锚定"); ok = False
    gdefs = set(GAP_RE.findall(secs["立项依据"]))  # 缺口只在立项依据段尾定义，全文收集会漏抓"引用未定义缺口"
    csec = secs["研究内容"]; cb = blocks(csec, CONT_ITEM); refd = set(GAP_RE.findall(csec))
    rep.append(f"## 3 缺口↔内容：缺口G{'/'.join(sorted(gdefs)) or '—'}；内容C{'/'.join(sorted(cb)) or '—'}")
    if not gdefs: rep.append("- [缺口] 立项依据未编号化缺口（写「缺口G1…」）"); ok = False
    for g in sorted(gdefs - refd): rep.append(f"- [孤儿缺口] 缺口G{g} 无内容承接"); ok = False
    for c, b in cb.items():
        if not GAP_RE.search(b): rep.append(f"- [孤儿内容] C{c} 未注明回应缺口Gx"); ok = False
        for g in set(GAP_RE.findall(b)) - gdefs: rep.append(f"- [未定义] C{c} 引用未定义缺口G{g}"); ok = False
    if not cb: rep.append("- [缺失] 研究内容未编号（C1/C2…）"); ok = False
    lp = work / "evidence_ledger.json"
    ledger = json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else []
    np_ = len([s for s in ledger if s["type"] == "申请人前期基础"])
    ns_ = len(ledger) - np_
    pbad = sorted(set(int(x) for x in re.findall(r"\[P(\d{1,2})\]", text)) - set(range(1, np_ + 1)))
    sbad = sorted(set(int(x) for x in re.findall(r"\[S(\d{1,2})\]", text)) - set(range(1, ns_ + 1)))
    rep.append(f"## 4 证据编号：[P#]清单 {np_} 条，[S#]清单 {ns_} 条")
    if pbad: rep.append(f"- [越界] [P{'/P'.join(map(str, pbad))}] 不在清单，疑似虚构"); ok = False
    if sbad: rep.append(f"- [越界] [S{'/S'.join(map(str, sbad))}] 不在清单，引用无法核实"); ok = False
    for ln in secs["研究基础"].splitlines():
        s = ln.strip()
        if PRIOR.search(s) and not PREF.search(s) and "【待补充" not in s and "拟" not in s and "[→]" not in s:
            rep.append(f"- [未挂P] 前期论断未挂[P#]：{s[:60]}"); ok = False
    counts = {n: len(re.findall(r"^\s*(?:[-*]\s+|[（(]?\d+[）).、])\S", secs[n], re.M))
              for n in ("研究目标", "研究内容", "技术路线", "考核指标")}
    rep.append(f"## 5 要素数量：{counts}")
    missing = [n for n, b in secs.items() if not b.strip()]
    if missing: rep.append("- [缺失] 章节缺失或无内容：" + "、".join(missing)); ok = False
    nz = [v for v in counts.values() if v > 0]
    if nz and len(set(nz)) > 1: rep.append("- [不齐] 要素条目数不一致"); ok = False
    if any(v == 0 for v in counts.values()): rep.append("- [缺失] 存在空章节"); ok = False
    todo = re.findall(r"【待补充[^】]*】", text)
    rep.append(f"## 6 待补充 {len(todo)} 处：" + ("；".join(todo[:6]) if todo else "无"))
    rep.append(f"## 7 已完成[✓]{text.count('[✓]')} / 拟开展[→]{text.count('[→]')}")
    if text.count("[→]") == 0 and text.count("[✓]") > 0:
        rep.append("- [提示] 未见拟开展标记")
    mmd = render_routemap(work)
    rep.insert(1, f"总体：{'通过' if ok else '存在须修复问题'}")
    (work / "check_report.md").write_text("\n".join(rep), encoding="utf-8")
    (work / "check_state.json").write_text(json.dumps(
        {"passed": ok, "coverage": cov, "gaps": sorted(gdefs), "contents": sorted(cb),
         "n_priors": np_, "n_sources": ns_, "missing_sections": missing,
         "counts": counts, "issues": rep.count("- [")}, ensure_ascii=False), encoding="utf-8")
    rp = Path(a.out) / "result.json"
    if rp.exists():
        res = json.loads(rp.read_text(encoding="utf-8"))
        vb = res.setdefault("version_boundary", {}); vb.setdefault("conflicts", [])
        gaps = vb.setdefault("material_gaps", [])
        for t in todo:
            if t not in gaps: gaps.append(t)
        rp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(rep[:12])); print(f"check {'PASS' if ok else 'FAIL'} -> {work/'check_report.md'}; routemap={bool(mmd)}")

def render_routemap(work):
    mp = work / "matrix.csv"
    if not mp.exists(): return None
    rows = list(csv.reader(open(mp, encoding="utf-8")))[1:]
    lines, prev = ["flowchart TD"], None
    for i, r in enumerate(rows):
        if len(r) < 4 or not r[1].strip(): continue
        node = f"n{i}[\"{r[0].strip()} {r[1].strip()[:24]} → {r[2].strip()[:24]} → 指标:{r[3].strip()[:16]}\"]"
        lines.append(f"  {node}")
        if prev: lines.append(f"  {prev} --> n{i}")
        prev = f"n{i}"
    if prev is None: return None
    (work / "route_map.mmd").write_text("\n".join(lines), encoding="utf-8")
    return True

def cmd_pack(a):
    work, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rp = out / "result.json"
    res = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    dp, final = work / "draft.md", out / "proposal_sections.md"
    if dp.exists(): final.write_text(dp.read_text(encoding="utf-8"), encoding="utf-8")
    chk, mmd = work / "check_report.md", work / "route_map.mmd"
    if mmd.exists(): (out / "route_map.mmd").write_text(mmd.read_text(encoding="utf-8"), encoding="utf-8")
    if chk.exists(): (out / "consistency_report.md").write_text(chk.read_text(encoding="utf-8"), encoding="utf-8")
    text = dp.read_text(encoding="utf-8") if dp.exists() else ""
    smap = sections_map(text)
    for sm in res.get("source_mapping", []):
        eid = sm.get("evidence_id", ""); sm["used_in"] = [n for n, b in smap.items() if f"[{eid}]" in b]
    cs = work / "check_state.json"
    if cs.exists():
        c = json.loads(cs.read_text(encoding="utf-8"))
        checks = {"passed": c.get("passed"), "coverage": c.get("coverage"), "n_priors": c.get("n_priors"),
                  "counts": c.get("counts"), "issues_count": c.get("issues")}
    else:
        checks = {"passed": None, "note": "未运行 check，一致性未回检"}
    vb = res.get("version_boundary", {})
    res.update({"case_id": a.case_id or res.get("case_id", "unknown"),
                "status": "complete" if final.exists() else "partial",
                "deliverables": {"proposal_sections": str(final) if final.exists() else None,
                                 "route_map": str(out / "route_map.mmd") if mmd.exists() else None,
                                 "consistency_report": str(out / "consistency_report.md") if chk.exists() else None},
                "checks": checks,
                "version_boundary": {**vb, "change_records": vb.get("change_records", []) + ["pack: 汇总终稿，回填 used_in"],
                                     "material_gaps": vb.get("material_gaps", []), "conflicts": vb.get("conflicts", []),
                                     "anomalies": vb.get("anomalies", [])}})
    if not final.exists(): res.setdefault("uncertainty", []).append("章节稿未生成，仅交付骨架与台账")
    rp.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"pack ok: status={res['status']} -> {rp}")

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--case", default="/input/case.json")
    p.add_argument("--task", default="/input/task.md"); p.add_argument("--work", default="/app/work")
    p.add_argument("--out", default="/app/output"); p.set_defaults(f=cmd_init)
    p = sub.add_parser("check"); p.add_argument("--work", default="/app/work")
    p.add_argument("--out", default="/app/output"); p.set_defaults(f=cmd_check)
    p = sub.add_parser("pack"); p.add_argument("--work", default="/app/work")
    p.add_argument("--out", default="/app/output"); p.add_argument("--case-id", default=None); p.set_defaults(f=cmd_pack)
    a = ap.parse_args(); a.f(a)

if __name__ == "__main__":
    sys.exit(main())
