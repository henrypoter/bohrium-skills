#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_claims.py — 论断-证据对齐核验辅助脚本 v3（仅标准库）。判据外置，可复跑：
  prep     解析 claims+源文本：复合论断拆分、逐子论断候选证据、三重对齐检查表与 machine_hint
  finalize 引文逐字回查(硬门槛) + advisory 提示 R1-R4（数值/范围/外推/冲突）只记 rule_flags、不强制改判
  selftest 正向+变异双夹具自测（10 项，见 SKILL.md）
用法见 SKILL.md；claims 允许 [str,...] 或 [{"id","claim"},...]；源文件须为纯文本。
"""
import argparse, json, os, re, sys, tempfile

VERDICTS = {"supported", "partially_supported", "contradicted", "insufficient_evidence"}
CJK = r"一-鿿"
WORD_RE = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*|[%s]" % CJK)
NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\s*(%|ppm|ppb|k?Pa|k?MPa|GPa|m?s|kg|g|mg|mL|L|mol|mM|M|nm|mm|cm|km|Hz|kHz|MHz|GHz|K|°C|V|mA|A|W|h|min|s|×10\^?[-+]?\d+)?")
SPLIT_CUE = re.compile(r"并且|以及|同时|此外|而且|且|；|;|, and | and | while | whereas | but also")
TYPE_CUE = [
    ("comparison", re.compile(r"高于|低于|优于|劣于|更大|更小|更快|更慢|倍|超过|higher|lower|better|worse|more than|less than|outperform|exceed|≥|≤|>|<")),
    ("causal", re.compile(r"导致|因此|使得|源于|由于|因为|归因|because|due to|leads? to|cause|result in|therefore|attribute")),
    ("scope", re.compile(r"所有|任何|仅|只|全部|从未|总是|范围|适用于|all|only|never|always|every|any|within|limited to")),
]
SENT_RE = re.compile(r"[^。！？!?\n]{6,}?[。！？!?]|[^。！？!?\n]{6,}$", re.M)
STOP = set("the a an of to in is are was were and or for on with by at from as it this that we our be has have not no".split())
SCOPE_ALL_RE = re.compile(r"所有|任何|全部|每个|各个|\ball\b|\bany\b|\bevery\b", re.I)
SCOPE_LIM_RE = re.compile(r"仅|只|限于|局限于|仅限|only|limited to|restricted to|solely", re.I)
UNVERIFIED_RE = re.compile(r"尚未|未验证|未研究|未考察|尚不清楚|有待|未见报道|not yet|untested|unverified|not been (?:tested|verified|studied)|unknown|remains? un", re.I)
HEDGE_RE = re.compile(r"可能|也许|推测|提示|或许|有望|may|might|suggest|possibly|potentially|likely", re.I)


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def load_claims(path):
    data = json.load(open(path, encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("claims", data.get("items", [data]))
    out = []
    for i, c in enumerate(data):
        if isinstance(c, str):
            c = {"claim": c}
        out.append({"id": str(c.get("id", "C%d" % (i + 1))),
                    "claim": c.get("claim") or c.get("text") or c.get("question") or ""})
    return out


def load_sources(paths):  # 返回段落索引 [{file,para,page,text}] 与来源清单
    units, srcs = [], []
    for p in paths:
        text = open(p, encoding="utf-8", errors="replace").read()
        name = os.path.basename(p)
        srcs.append({"file": name, "chars": len(text)})
        page, pi = 1, 0
        for chunk in text.split("\f"):  # 支持换页符与 [[page N]] 标记
            for para in re.split(r"\n\s*\n", chunk):
                for m in re.finditer(r"\[\[page\s+(\d+)\]\]", para):
                    page = int(m.group(1))
                para = re.sub(r"\[\[page\s+\d+\]\]", "", para)
                if para.strip():
                    pi += 1
                    units.append({"file": name, "para": pi, "page": page, "text": norm(para)})
            page += 1
    return units, srcs


def sentences(units):
    sents = []
    for u in units:
        for m in SENT_RE.finditer(u["text"]):
            s = norm(m.group(0))
            if len(s) >= 8:
                sents.append({"file": u["file"], "page": u["page"], "para": u["para"], "sentence": s})
    return sents


def tokens(s):
    toks = WORD_RE.findall(s.lower())
    return [t for t in toks if t not in STOP and not (len(t) == 1 and ord(t) < 128)]


def nums(s):  # [(规范化数值串, 是否带单位)]
    out = []
    for m in NUM_RE.finditer(s):
        v = re.sub(r"\s+", "", m.group(0))
        if v not in ("-", "+"):
            out.append((v, bool(m.group(1))))
    return out


def num_strs(s):
    return [v for v, _ in nums(s)]


def claim_type(text):
    types = [t for t, r in TYPE_CUE if r.search(text)]
    return types or ["fact"]


def split_hint(text):
    parts = [p.strip(" ，,。") for p in SPLIT_CUE.split(text) if len(p.strip(" ，,。")) >= 6]
    return parts if len(parts) > 1 else [text]


def rank(query, sents, topk):
    ct, cn = set(tokens(query)), num_strs(query)
    scored = []
    for s in sents:
        ov = len(ct & set(tokens(s["sentence"]))) / (len(ct) ** 0.5) if ct else 0
        if ov < 1.2:  # 过滤纯主题相关的弱重叠
            continue
        num_hit = sum(1 for n in cn if n in num_strs(s["sentence"]))
        scored.append((round(ov + 0.5 * num_hit, 2), s))
    scored.sort(key=lambda x: -x[0])
    return scored[:topk]


def align(sub_text, sent_text):
    """实体/数值/范围三重对齐检查表 + 机器支持度建议（初筛，终判由模型读原文给出）。"""
    st, qt = set(tokens(sub_text)), set(tokens(sent_text))
    ent = round(len(st & qt) / max(1, len(st)), 2)
    flags, checks = [], {"entity_overlap": ent}
    missing = [v for v, _ in nums(sub_text) if v not in num_strs(sent_text)]
    if ent < 0.5:
        flags.append("entity_weak")
    if missing:
        flags.append("number_missing:" + ",".join(missing))
        checks["numbers_missing_in_quote"] = missing
    if SCOPE_ALL_RE.search(sub_text) and (SCOPE_LIM_RE.search(sent_text)
                                          or not SCOPE_ALL_RE.search(sent_text)):
        flags.append("scope_overreach?")
    if HEDGE_RE.search(sent_text) and not HEDGE_RE.search(sub_text):
        flags.append("hedged_evidence")
    if UNVERIFIED_RE.search(sent_text):
        flags.append("says_unverified")
    hint = ("not_supported" if "entity_weak" in flags else
            "partial_or_contradicted" if missing else
            "partially_supported" if flags else "supported")
    checks["flags"], checks["machine_hint"] = flags, hint
    return checks


def cmd_prep(a):
    claims = load_claims(a.claims)
    units, srcs = load_sources(a.source)
    sents = sentences(units)
    draft = {"case_id": a.case_id or "", "sources": srcs, "claims": []}
    for c in claims:
        subs = []
        for i, t in enumerate(split_hint(c["claim"])):
            cand = [{"score": sc, "file": s["file"], "page": s["page"], "para": s["para"],
                     "sentence": s["sentence"], "alignment": align(t, s["sentence"])}
                    for sc, s in rank(t, sents, a.topk)]
            subs.append({"sub_id": "%s.%d" % (c["id"], i + 1), "text": t,
                         "types": claim_type(t), "candidates": cand})
        draft["claims"].append({
            "id": c["id"], "claim": c["claim"],
            "claim_numbers": num_strs(c["claim"]),
            "split_hint": subs,
            "verdict": "", "evidence": [], "reasoning": "",
            "numeric_check": "", "limits": ""})
    os.makedirs(a.out, exist_ok=True)
    fp = os.path.join(a.out, "verdicts.draft.json")
    json.dump(draft, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_cand = sum(len(s["candidates"]) for c in draft["claims"] for s in c["split_hint"])
    print("prep ok: %d claims, %d sentences, %d cands -> %s"
          % (len(claims), len(sents), n_cand, fp))
    for c in draft["claims"]:
        for s in c["split_hint"]:
            if not s["candidates"]:
                print("WARN: no candidate for %s (换关键词或判 insufficient)" % s["sub_id"])


def verbatim_ok(quote, haystacks):
    q = norm(quote)
    return any(q in h for h in haystacks)


def apply_rules(c, v, evs, flags):
    """advisory 提示层 R1-R4：仅记 rule_flags，不强制改判（终判留给模型）；只依据逐字命中的引文。"""
    qs = [e["quote"] for e in evs if e.get("quote_verbatim")]
    if not qs:
        return v
    allnums = [n for q in qs for n in num_strs(q)]
    for n, has_unit in nums(c.get("claim", "")):  # R1 带单位数值未逐字出现在引文
        if has_unit and n not in allnums:
            same = [m for q in qs for m, u in nums(q) if u and m != n and
                    re.sub(r"^[-+\d.eE]+", "", m) == re.sub(r"^[-+\d.eE]+", "", n)]
            tag = "R1b_mismatch(%s vs quote %s)" % (n, same[0]) if same else "R1a_missing(%s)" % n
            flags.append("advice:%s:复核数值/单位是否与原文一致" % tag)
    if SCOPE_ALL_RE.search(c.get("claim", "")) and any(SCOPE_LIM_RE.search(q) for q in qs):
        # R2 论断全称量化而引文有限定语 → 提示复核范围夸大，不改判
        flags.append("advice:R2_scope_overreach:复核全称量化是否超出原文限定语")
    if v == "contradicted" and any(UNVERIFIED_RE.search(q) for q in qs) \
            and not any(n in allnums for n, _ in nums(c.get("claim", ""))):
        # R3 外推≠否证：引文仅称「尚未验证」→ 提示或应 insufficient_evidence，不改判
        flags.append("advice:R3_extrapolation_not_disproof:引文仅称尚未验证，考虑改为 insufficient_evidence")
    sup = {e.get("support") for e in evs}  # R4 证据标签冲突并列 → 提示 limits 并列双方
    if "supported" in sup and "contradicted" in sup:
        flags.append("advice:R4_conflict:证据标签并列 supported+contradicted，建议 limits 并列双方定位"
                     + ("（当前 limits 为空）" if not c.get("limits") else ""))
    return v


def cmd_finalize(a):
    d = json.load(open(a.draft, encoding="utf-8"))
    units, _ = load_sources(a.source)
    hay = [u["text"] for u in units] + [s["sentence"] for s in sentences(units)]
    problems, done = [], 0
    out_claims = []
    for c in d.get("claims", []):
        v = c.get("verdict", "")
        if v not in VERDICTS:
            problems.append("%s: verdict 非法或缺失(%r)" % (c.get("id"), v))
            v = "insufficient_evidence"
        evs = []
        for e in c.get("evidence", []):
            q = e.get("quote", "")
            found = verbatim_ok(q, hay)
            if not found:
                problems.append("%s: 引文未逐字命中原文: %s..." % (c.get("id"), q[:40]))
            evs.append({"quote": q, "file": e.get("file", ""), "page": e.get("page"),
                        "para": e.get("para"), "quote_verbatim": found,
                        "support": e.get("support", v)})
        flags = []
        v = apply_rules(c, v, evs, flags)  # R1-R4 仅记 advice 提示，不强制改判
        if v != "insufficient_evidence":
            if not evs:
                problems.append("%s: verdict=%s 但无证据" % (c.get("id"), v))
            else:
                done += 1
        out_claims.append({
            "id": c.get("id"), "claim": c.get("claim"),
            "sub_claims": [{k: s[k] for k in ("sub_id", "text", "types") if k in s}
                           for s in c.get("split_hint", [])],
            "verdict": v, "evidence": evs,
            "reasoning": c.get("reasoning", ""),
            "numeric_check": c.get("numeric_check", ""),
            "limits": c.get("limits", ""),
            "rule_flags": flags})
    n = len(out_claims)
    cnt = lambda v: sum(1 for c in out_claims if c["verdict"] == v)
    status = ("failed" if problems and done == 0 else
              "partial" if problems or cnt("insufficient_evidence") else "success")
    result = {
        "case_id": a.case_id or d.get("case_id", ""), "status": status,
        "claims": out_claims, "sources": d.get("sources", []),
        "uncertainty": [c["limits"] for c in out_claims if c.get("limits")] + problems,
        "summary": {"total": n, "supported": cnt("supported"),
                    "partially_supported": cnt("partially_supported"),
                    "contradicted": cnt("contradicted"),
                    "insufficient_evidence": cnt("insufficient_evidence")},
        "change_records": d.get("change_records", []),
    }
    os.makedirs(a.out, exist_ok=True)
    fp = os.path.join(a.out, "result.json")
    json.dump(result, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("finalize: status=%s, %d/%d 判定完成, %d 个问题 -> %s" % (status, done, n, len(problems), fp))
    for p in problems:
        print("ISSUE:", p)


PAPER = """[[page 3]]
本研究 2024 年采集 128 份水稻样本，平均产量 7.2 t/ha。

新施肥方案使产量较对照组提高了 15%，差异显著（p < 0.05）。

[[page 5]]
该方法仅适用于粳稻品种，对籼稻的效果尚未验证。
"""


def cmd_selftest(a):  # 正向+变异双夹具：正确流程不误伤；典型误判记 advisory 提示，硬错误仍拦截
    tmp = tempfile.mkdtemp(prefix="vct")
    sp = os.path.join(tmp, "paper.txt")
    open(sp, "w", encoding="utf-8").write(PAPER)
    cp = os.path.join(tmp, "claims.json")
    c1 = "新方案使产量提高了 15% 且对所有水稻品种有效"
    json.dump([{"id": "A1", "claim": c1}, {"id": "A2", "claim": "样本量为 200 份"}],
              open(cp, "w", encoding="utf-8"), ensure_ascii=False)
    ns = argparse.Namespace
    cmd_prep(ns(claims=cp, source=[sp], out=tmp, topk=3, case_id="SELFTEST"))
    draft = json.load(open(os.path.join(tmp, "verdicts.draft.json"), encoding="utf-8"))
    ok = []

    def check(name, cond):
        ok.append(cond)
        print("%s %s" % ("PASS" if cond else "FAIL", name))

    a1 = draft["claims"][0]
    check("P1 prep 复合拆分(A1≥2 子论断)", len(a1["split_hint"]) >= 2)
    check("P2 prep 范围子论断检出 scope_overreach",
          any("scope_overreach?" in f for cd in a1["split_hint"][-1]["candidates"]
              for f in cd["alignment"]["flags"]))
    q128, q15, qlim = [norm(re.sub(r"\[\[page \d+\]\]", "", p)) for p in PAPER.split("\n\n")]

    def run(claims, tag):
        d = {"case_id": "SELFTEST", "sources": [], "claims": claims}
        dp = os.path.join(tmp, "v_%s.json" % tag)
        json.dump(d, open(dp, "w", encoding="utf-8"), ensure_ascii=False)
        op = os.path.join(tmp, "o_%s" % tag)
        cmd_finalize(ns(draft=dp, source=[sp], out=op, case_id="SELFTEST"))
        return json.load(open(os.path.join(op, "result.json"), encoding="utf-8"))

    def mk(cid, claim, verdict, evs):
        return {"id": cid, "claim": claim, "verdict": verdict, "reasoning": "t",
                "evidence": [{"quote": q, "file": "paper.txt", "page": pg, "para": 1,
                              "support": s} for q, pg, s in evs]}

    def advice(tag, claim, verdict, evs, flag, note):
        """变异夹具：R1-R4 只记 advice 提示、不强制改判；verdict 保持模型原判。"""
        r = run([mk(tag, claim, verdict, evs)], tag)["claims"][0]
        check("%s 变异·%s(advisory 不阻断)" % (tag, note),
              r["verdict"] == verdict and any(flag in f for f in r["rule_flags"]))

    r = run([mk("A1", c1, "partially_supported",
                [(q15, 3, "supported"), (qlim, 5, "contradicted")]),
             mk("A2", "样本量为 200 份", "contradicted", [(q128, 3, "contradicted")])], "pos")
    check("P3 正向夹具不被误降级(A1)", r["claims"][0]["verdict"] == "partially_supported")
    check("P4 正向夹具矛盾判定保留(A2)", r["claims"][1]["verdict"] == "contradicted")
    r = run([mk("P5", "新方案使产量提高了 15%", "supported", [(q15, 3, "supported")])], "p5")
    check("P5 干净 supported 无误伤", r["claims"][0]["verdict"] == "supported"
          and r["claims"][0]["rule_flags"] == [])
    advice("M1", "该方法对所有作物都有效", "supported", [(qlim, 5, "supported")],
           "R2", "主题相关≠支持")
    advice("M2", "新方案使产量提高了 25%", "supported", [(q15, 3, "supported")],
           "R1b", "数值抄错")
    advice("M3", "该方法对籼稻无效", "contradicted", [(qlim, 5, "contradicted")],
           "R3", "外推≠否证")
    advice("M5", "新方案使产量提高了 15%", "supported",
           [(q15, 3, "supported"), (qlim, 5, "contradicted")],
           "R4", "冲突并列")
    r = run([mk("M4", "样本量为 200 份", "contradicted",
                [("本研究采集了 200 份水稻样本。", 3, "contradicted")])], "m4")
    check("M4 变异·编造引文(硬门槛拦截+partial)",
          r["claims"][0]["evidence"][0]["quote_verbatim"] is False and r["status"] == "partial")
    n_pass = sum(ok)
    print("SELFTEST %s (%d/%d)" % ("PASS" if n_pass == len(ok) else "FAIL", n_pass, len(ok)))
    if n_pass != len(ok):
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prep", "finalize"):
        sp = sub.add_parser(name)
        sp.add_argument("--source", action="append", required=True)
        sp.add_argument("--out", required=True)
        sp.add_argument("--case-id", dest="case_id", default="")
        if name == "prep":
            sp.add_argument("--claims", required=True)
            sp.add_argument("--topk", type=int, default=3)
        else:
            sp.add_argument("--draft", required=True)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"prep": cmd_prep, "finalize": cmd_finalize, "selftest": cmd_selftest}[a.cmd](a)


if __name__ == "__main__":
    main()
