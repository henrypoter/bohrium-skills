#!/usr/bin/env python3
# skeleton.py: 论文逻辑骨架提取器(仅标准库)。用法: python3 skeleton.py <稿件> [-o skeleton.json]；信号均为候选，复述命中只记 warning。
import json, re, sys, os

HEDGE = ["可能","或许","一定程度上","在一定条件下","初步","may","might","suggest"]
CAUSE = ["导致","根本原因","决定了","必然","causes","leads to","hence","thereby","therefore","thus"]
CORR = ["相关","关联","相关性","正相关","负相关","correlation","correlated","associated","association"]
ARG = ["提出","证明","表明","优于","提升","降低","贡献","发现",
       "propose","show","demonstrate","find","outperform","improve","reduce","achieve"]
ZONE = {
  "goal": ["研究问题","目的","旨在","目标","本文","this paper","we aim","objective","goal"],
  "claim": ["我们提出","我们证明","我们表明","贡献","创新","we propose","we show","we demonstrate","contribution","novel"],
  "evidence": ["如表","如图","数据显示","实验结果","消融","table","figure","fig.","data show","ablation"],
  "method": ["方法","模型","算法","框架","采用","设计","approach","method","model","framework","algorithm","we design"],
  "result": ["结果表明","表现","性能","精度","准确率","提升","降低","优于","results","performance","accuracy","outperforms","improves"],
  "contrast": ["然而","但是","相比","不同于","however","but","whereas","compared","unlike","in contrast"],
  "background": ["已有","现有","此前","背景","近年来","随着","prior work","previous","existing","background","recently"],
  "conclusion": ["综上","总之","结论","未来工作","conclusion","in summary","we conclude","future work"]}
SEC_KEYS = {"abstract":["摘要","abstract"],"introduction":["引言","绪论","introduction"],
  "method":["方法","模型","method","approach","model","methodology"],
  "results":["结果","实验","results","experiment","evaluation"],
  "discussion":["讨论","discussion","analysis"],"conclusion":["结论","总结","conclusion"],
  "references":["参考文献","references","bibliography"]}
SEC_ZONE = {"abstract":"background","introduction":"background","method":"method",
  "results":"result","discussion":"conclusion","conclusion":"conclusion"}
STOP_CJK = "的了和是在与及或被把之其该中上下内外为就以都而者所于并等更很也又"
STOP_EN = {"a","an","the","of","and","or","to","in","on","for","with","by","at","as","is","are",
  "be","been","that","this","these","those","we","our","their","it","its","can","may"}

def split_sections(text):
    lines = text.split("\n")
    heads = []
    pmd = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    pnum = re.compile(r"^(\d+(?:\.\d+){0,3})[\.、\s]+(\S.{0,60})$")
    for i, ln in enumerate(lines):
        s = ln.strip()
        m = pmd.match(s) or pnum.match(s)
        if m and len(s) < 80 and not s.endswith(("。", ".", "；")):
            heads.append((i, m.group(2), len(m.group(1))))
    if not heads:
        ps = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return [("UNTITLED", ps, 1)]
    secs = []
    for k, (i, t, lv) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        ps = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines[i + 1:end])) if p.strip()]
        secs.append((t, ps, lv))
    return secs

ABBR = ("Fig", "Figs", "Table", "Tab", "Eq", "Eqs", "Sec", "Sect", "al", "cf", "vs",
        "Dr", "Mr", "Ms", "Prof", "Vol", "pp", "No", "Nos", "ca", "approx", "etc")

def split_sents(p):
    # 保护缩写与 (2023). 型引用中的句点，防英文断句锚点偏移
    p = re.sub(r"\b(%s)\." % "|".join(ABBR), lambda m: m.group(1) + "<DOT>", p)
    p = re.sub(r"\b(e\.g|i\.e)\.", lambda m: m.group(1) + "<DOT>", p)
    parts = [x.strip() for x in re.split(r"(?<=[。！？!?；;])|(?<=[a-z0-9\)][\.])\s+", p) if x.strip()]
    return [x.replace("<DOT>", ".") for x in parts]

def shingles(t, cjk, n):
    if cjk:
        t = re.sub(r"[^\w一-鿿]", "", t)
        return {t[i:i + n] for i in range(max(0, len(t) - n + 1))}
    t = re.sub(r"[^\w ]", "", t.lower()).split()
    return {" ".join(t[i:i + n]) for i in range(max(0, len(t) - n + 1))}

def zone_of(text, sec_z):
    low = text.lower()
    best, bs = sec_z, 0
    for z in ZONE:
        s = sum(1 for c in ZONE[z] if c in low)
        if s > bs:
            best, bs = z, s
    return best

def tokens_of(t, cjk):
    if cjk:
        for ch in STOP_CJK:
            t = t.replace(ch, "")
        t = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", t)
        return {t[i:i + 2] for i in range(max(0, len(t) - 1))}
    ws = re.sub(r"[^\w ]", " ", t.lower()).split()
    return {w for w in ws if len(w) > 1 and w not in STOP_EN}

def dice(a, b):
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0

def lcs(a, b):
    # 标准库 difflib 的 Gestalt/LCSS 近似相似度（C 加速）；超长对放弃
    if not a or not b:
        return 0.0
    if len(a) * len(b) > 1000000:
        return 0.0
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b, autojunk=False).ratio()

def main():
    path = sys.argv[1]
    out = sys.argv[sys.argv.index("-o") + 1] if "-o" in sys.argv else "skeleton.json"
    text = open(path, encoding="utf-8", errors="replace").read()
    secs = split_sections(text)
    untitled = len(secs) == 1 and secs[0][0] == "UNTITLED"
    skel, found, sents = [], set(), []
    for si, (title, paras, lv) in enumerate(secs, 1):
        low = title.lower()
        key = "other"
        for k, ws in SEC_KEYS.items():
            if any(w in low or w in title for w in ws):
                found.add(k)
                key = k
                break
        sz = SEC_ZONE.get(key, "other")
        srole = "front" if any(w in low for w in SEC_KEYS["introduction"] + SEC_KEYS["abstract"]) else ("back" if any(w in low for w in SEC_KEYS["conclusion"] + SEC_KEYS["discussion"]) else "mid")
        ps = []
        for pi, p in enumerate(paras, 1):
            pid = "S%d.P%d" % (si, pi)
            sents_p = split_sents(p)
            low_p = p.lower()
            z = zone_of(p, sz)
            ps.append({"id": pid, "chars": len(p), "n_sent": len(sents_p), "zone": z,
                       "claim": z in ("claim","goal","conclusion") or any(c in low_p for c in ZONE["claim"]),
                       "evidence": z in ("evidence","result") or any(c in low_p for c in ZONE["evidence"]),
                       "hedge": any(c in low_p for c in HEDGE),
                       "cause": any(c in low_p for c in CAUSE),
                       "corr": any(c in low_p for c in CORR)})
            for qi, s in enumerate(sents_p, 1):
                cjk = bool(re.search(r"[\u4e00-\u9fff]", s))
                norm = re.sub(r"[^\w一-鿿]", "", s) if cjk else re.sub(r"[^\w ]", "", s.lower())
                if len(norm) >= (8 if cjk else 20):
                    sents.append({"id": "%s.s%d" % (pid, qi), "sec": si, "stitle": title,
                                  "grp": pi if untitled else si,
                                  "srole": srole, "norm": norm, "zone": zone_of(s, sz),
                                  "arg": any(c in s.lower() for c in ARG),
                                  "tok": tokens_of(s, cjk),
                                  "sh": shingles(s, cjk, 5 if cjk else 3),
                                  "text": s[:40].replace("\n", " ")})
        skel.append({"sec_id": "S%d" % si, "title": title, "level": lv, "n_para": len(paras),
                     "chars": sum(len(p) for p in paras), "paragraphs": ps})
    # 复述召回：词汇倒排预筛（零共词句对 dice=0 且现实语料中 lcs 不可能>=0.5，跳过），
    # 防长稿 O(n^2) 爆炸；空词集句对不参与（词表外全停用词句）。高频词(>60 句)防爆。
    inv = {}
    for idx, s in enumerate(sents):
        for t in s["tok"]:
            inv.setdefault(t, []).append(idx)
    cand = set()
    for ids in inv.values():
        if len(ids) > 60:
            continue
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                cand.add((ids[x], ids[y]))
    scan_capped = len(cand) > 200000
    if scan_capped:
        cand = set(sorted(cand)[:200000])
    dup, seen = [], set()
    for i, j in sorted(cand):
        a, b = sents[i], sents[j]
        if a["grp"] == b["grp"]:
            continue
        sh = len(a["sh"] & b["sh"]) / min(len(a["sh"]), len(b["sh"])) if a["sh"] and b["sh"] else 0.0
        sem = dice(a["tok"], b["tok"])
        if sh >= 0.3:
            chan = "shingle"
        else:
            if sem < 0.5:
                sem = max(sem, lcs(a["norm"], b["norm"]))
            chan = "semantic_proxy" if sem >= 0.5 else ""
        if not chan:
            continue
        key = (a["id"], b["id"])
        if key in seen:
            continue
        seen.add(key)
        dup.append({"pair": [a["id"], b["id"]], "channel": chan, "similarity": round(sh, 2),
                    "semantic": round(sem, 2), "roles": [a["zone"], b["zone"]],
                    "position": "echo" if a["srole"] + b["srole"] in ("frontback", "backfront") else "cross",
                    "secs": [a["stitle"], b["stitle"]], "arbitration": chan != "shingle", "level": "warning"})
    dup.sort(key=lambda x: -(x["similarity"] + x["semantic"]))
    role, rseen = [], set()
    for i in range(len(sents)):
        a = sents[i]
        if a["zone"] not in ("claim", "conclusion", "goal") or not a["arg"]:
            continue
        for j in range(i + 1, len(sents)):
            b = sents[j]
            if a["grp"] == b["grp"] or b["zone"] not in ("claim", "conclusion", "goal") or not b["arg"]:
                continue
            key = tuple(sorted([a["id"], b["id"]]))
            if key in rseen or key in seen:
                continue
            rseen.add(key)
            role.append({"pair": [a["id"], b["id"]], "roles": [a["zone"], b["zone"]],
                         "texts": [a["text"], b["text"]], "secs": [a["stitle"], b["stitle"]],
                         "note": "需 LLM 判定重复或必要呼应", "level": "warning"})
    total_chars_all = sum(s["chars"] for s in skel)
    # 体裁信号：无学术节标题 且 正文无任何学术功能词命中(zone 全为 other) → 疑似非学术体裁
    acad_paras = sum(1 for s in skel for p in s["paragraphs"] if p["zone"] != "other")
    non_academic = total_chars_all > 0 and not found and acad_paras == 0
    bound = []
    targets = []
    for s in skel:
        low = s["title"].lower()
        if any(w in low or w in s["title"] for w in SEC_KEYS["conclusion"] + SEC_KEYS["abstract"]):
            targets.append((s, s["paragraphs"], ""))
    if not targets and not non_academic and skel and skel[-1]["paragraphs"]:
        targets.append((skel[-1], skel[-1]["paragraphs"][-1:], "（无结论/摘要节标题，按结尾段启发式处理）"))
    for s, paras, tag in targets:
        sec_hedge = any(p["hedge"] for p in s["paragraphs"])
        for p in paras:
            if p["cause"] and not p["hedge"]:
                bound.append({"para": p["id"], "sec": s["title"], "reason": tag + "强因果且无限定词，需核对证据范围"})
            if p["corr"] and p["cause"]:
                bound.append({"para": p["id"], "sec": s["title"], "reason": tag + "相关+因果并存，需核对是否相关写成因果"})
        if not sec_hedge:
            bound.append({"para": s["sec_id"], "sec": s["title"], "reason": tag + "结论/摘要节无限定词，需核对是否缺限制声明"})
    last = secs[-1][1][-1] if secs and secs[-1][1] else ""
    truncated = bool(last) and not re.search(r"[。！？.!?]\s*$|\[\d+\]\s*$", last)
    zc = {}
    for s in skel:
        for p in s["paragraphs"]:
            zc[p["zone"]] = zc.get(p["zone"], 0) + 1
    total = total_chars_all
    warnings = [d["pair"] for d in dup[:30]] + [r["pair"] for r in role[:20]]
    if total == 0:
        warnings.append(["empty_input"])
    if non_academic:
        warnings.append(["no_academic_structure"])
    res = {"input": os.path.basename(path), "total_chars": total, "n_sections": len(skel),
           "sections": skel, "zone_stats": zc,
           "missing_sections": sorted(set(SEC_KEYS) - found - {"discussion"}),
           "redundancy_candidates": dup[:30], "role_redundancy_candidates": role[:20],
           "boundary_candidates": bound, "truncation_suspect": truncated,
           "dup_scan_capped": scan_capped, "warnings": warnings,
           "note": "信号均为候选告警(level=warning)，需模型核实后入 diagnosis。复述召回经词汇倒排预筛，空词集句对不参与。"}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("sec=%d para=%d dup=%d role=%d bound=%d missing=%s trunc=%s -> %s"
          % (len(skel), sum(s["n_para"] for s in skel), len(dup), len(role), len(bound),
             ",".join(res["missing_sections"]) or "none", truncated, out))

if __name__ == "__main__":
    main()
