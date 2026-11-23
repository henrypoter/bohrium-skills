#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_tools.py — 科研成果转化写作事实台账提取与改写稿核验，仅标准库。
台账含数值/图表/引用/缩写/强度词/限定语/因果相关词/建议词/研究对象层级；check 另报限定语丢失、建议/因果/外推越级、体裁结构（--genre）。
v3 修复（tests/run_tests.py 夹具验证，正向零误杀、变异必命中）：
1. 数值台账剔除图表/引用编号（图 2、[3] 有专门字段核对，不再误入数字 diff 造成正向误报）；
2. 限定语按句级留存判定：对应论断被整体删除（数字键与四字片段均不残留）时不强制保留限定语；
3. 弱承接词“使得”移出因果词表（与源文同义改述时误报；仍由工作流第 2 步人工通读把关）；
4. 文件缺失/非法 JSON/参数不足友好退出（exit 2，不抛 traceback）。
"""
import re, sys, json, pathlib

UNITS = (r"%|‰|℃|°C|K|nm|μ[mgl]|u[mgl]|mm|cm|km|kg|mg|ng|mL|μL|m[s]?|ms|min|h|Hz|kHz|MHz|GHz|"
         r"eV|keV|MeV|GeV|kJ|J|kW|MW|W|mV|kV|V|mA|A|kPa|MPa|GPa|Pa|bar|atm|mM|μM|nM|M|rpm|fps|"
         r"分?钟|小时|天|年|倍|个百分点|次|个|种|组|例|轮|批|篇")
NUM = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?(?:\s*(?:" + UNITS + r"))?(?![0-9A-Za-z%])")
SAMPLE = re.compile(r"[nN]\s*[=＝]\s*\d+")
FIGREF = re.compile(r"(?:图|表|附图|Fig\.?|Figure|Table|Supplementary(?:\s+Fig\.?)?)\s*S?\d+(?:\.\d+)?", re.I)
CITE = re.compile(r"\[\d+(?:[-–,，]\s*\d+)*\]|\([A-Z][A-Za-z\-]+(?:\s+et\s+al\.?)?,?\s*(?:19|20)\d{2}[a-z]?\)")
ABBR = re.compile(r"\b[A-Z][A-Z0-9\-]{1,7}\b")
ABBR_DEF = re.compile(r"([A-Za-z\u4e00-\u9fff][A-Za-z0-9\s\-/\u4e00-\u9fff]{1,60}?)\s*[（(]\s*([A-Z][A-Z0-9\-]{1,7})\s*[)）]")
STRONG = ["证明", "首次", "突破", "革命性", "颠覆", "国际领先", "世界领先", "填补空白", "完全解决", "彻底解决",
          "proves", "breakthrough"]
STOP = {"OK", "ID", "OR", "AND", "THE", "FOR", "WITH", "FROM"}

CAVEATS = [
    ("待验证", ["尚待", "有待", "尚未", "仍需", "需要进一步", "进一步研究"]),
    ("初步/小样本", ["初步", "小样本", "样本量小", "样本量较小", "样本有限", "数据有限", "证据有限"]),
    ("仅限/范围", ["仅限于", "仅适用于", "仅在", "只在", "只适用于", "不适用于"]),
    ("未同行评议", ["未同行评议", "未经同行评议", "预印本", "preprint"]),
]
CAUSAL = ["导致", "引起", "造成", "治愈", "治疗", "预防", "疗效", "cause", "cure", "treat", "prevent"]
CORREL = ["相关", "关联", "associated", "correlated", "linked"]
ADVICE = ["应当", "应该", "建议", "推荐", "recommend", "should"]
NEG = ["没有", "不能", "并未", "尚未", "尚无", "缺乏", "无法", "未能", "不会", "不足"]
SUBJECT_TIERS = [
    ("体外/实验室", ["体外", "细胞", "实验室", "模拟", "in vitro", "cell line"]),
    ("动物/活体", ["动物", "小鼠", "大鼠", "动物模型", "in vivo", "mice", "rats", "rabbit"]),
    ("人体/临床", ["人体", "临床", "患者", "human", "patient", "clinical", "trial"]),
    ("实际应用/产业化", ["工业", "规模化", "量产", "产业化", "商业", "市场", "实际应用",
                     "commercial", "industrial", "manufacturing"]),
]
GENRE_SECTIONS = {
    "科普文章": {"场景引入": ["场景", "痛点", "想象"], "核心发现": ["发现", "实现", "达到"], "局限": ["局限", "不过", "尚待"], "来源": ["来源", "发表"]},
    "技术转移报告": {"成果概述": ["成果概述"], "技术要点": ["技术要点", "技术方案"], "性能指标": ["性能指标"],
                 "成熟度": ["成熟度", "TRL"], "应用场景": ["应用场景", "应用"], "风险": ["风险", "待确认"]},
    "项目申报": {"立项依据": ["立项依据", "立项"], "研究基础": ["研究基础"], "技术路线": ["技术路线"],
               "考核指标": ["考核指标"], "效益前景": ["前景", "效益"]},
    "新闻稿": {"首段导语": ["本报讯", "记者", "讯"], "意义": ["意义", "价值"], "团队出处": ["团队", "单位", "大学"], "背景": ["背景"]},
}


def norm_num(s):
    s = s.replace(",", "").replace("μ", "u").strip().lower()
    s = re.sub(r"\s+", " ", s)
    m = re.match(r"^(\d+(?:\.\d+)?)(.*)$", s)
    if m:
        v = m.group(1).rstrip("0").rstrip(".") if "." in m.group(1) else m.group(1)
        return v + m.group(2).strip()
    return s


CN = dict(zip("零一二三四五六七八九", "0123456789"))
CN_NUM = re.compile(r"[零一二三四五六七八九十]{1,3}(?=[次个种组例篇天年小时分钟步批只名位轮篇倍])")


def cn2digit(s):
    def rep(m):
        t = m.group(0)
        if t == "十":
            return "10"
        if t.startswith("十"):
            return "1" + CN[t[1]]
        if t.endswith("十"):
            return CN[t[0]] + "0"
        if "十" in t:
            a, b = t.split("十")
            return CN[a] + CN[b]
        return "".join(CN[c] for c in t)
    return CN_NUM.sub(rep, s)


def sentences(text):
    parts = re.split(r"(?<=[。！？!?;；])|(?<![0-9])\.(?![0-9])|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def in_caveat(s):
    return any(any(w in s for w in words) for _, words in CAVEATS)


def in_neg(s):
    return any(w in s for w in NEG)


def asserted(words, text):
    out = {}
    for w in words:
        if w not in text:
            continue
        for s in sentences(text):
            if w in s and not in_caveat(s) and not in_neg(s):
                out[w] = s[:100]
                break
    return out


def subject_tiers(text):
    t = re.sub(r"pre[-\s]?clinical", "PRECLIN", text, flags=re.I)
    idx = set()
    for i, (_, words) in enumerate(SUBJECT_TIERS):
        for w in words:
            if w in t and any(w in s and not in_caveat(s) and not in_neg(s) for s in sentences(t)):
                idx.add(i)
                break
    return idx


def scan(text):
    led = {
        "numbers": {},
        "sample_sizes": sorted(set(m.group(0) for m in SAMPLE.finditer(text))),
        "fig_refs": sorted(set(m.group(0) for m in FIGREF.finditer(text))),
        "citations": sorted(set(m.group(0) for m in CITE.finditer(text))),
        "abbreviations": sorted({m.group(0) for m in ABBR.finditer(text)} - STOP),
        "abbr_definitions": {m.group(2): m.group(1).strip() for m in ABBR_DEF.finditer(text)},
        "strong_claim_words": [w for w in STRONG if w in text],
    }
    for sent in sentences(text):
        sent_num = FIGREF.sub(" ", CITE.sub(" ", sent))  # 图表/引用编号有专门字段核对，不进数值台账
        for m in NUM.finditer(cn2digit(sent_num)):
            key = norm_num(m.group(0))
            if not key:
                continue
            led["numbers"].setdefault(key, [])
            if len(led["numbers"][key]) < 2:
                led["numbers"][key].append(sent[:100])
    led["caveats"] = {}
    for name, words in CAVEATS:
        if any(w in text for w in words):
            led["caveats"][name] = [s[:100] for s in sentences(text) if any(w in s for w in words)][:2]
    led["causal_words"] = sorted(asserted(CAUSAL, text).keys())
    led["correl_words"] = [w for w in CORREL if w in text]
    led["advice_words"] = sorted(asserted(ADVICE, text).keys())
    led["asserted_subject_tier_idx"] = sorted(subject_tiers(text))
    return led


def num_keys(text):
    keys = set()
    for m in NUM.finditer(cn2digit(FIGREF.sub(" ", CITE.sub(" ", text)))):
        k = norm_num(m.group(0))
        if k:
            keys.add(k)
    return keys


def cn_4grams(text):
    chars = re.findall(r"[一-鿿]", text)
    return {"".join(chars[i:i + 4]) for i in range(len(chars) - 3)}


def claim_retained(sent, draft_numkeys, draft_4grams):
    if num_keys(sent) & draft_numkeys:
        return True
    return bool(cn_4grams(sent) & draft_4grams)


def read_text_or_exit(p):
    try:
        return pathlib.Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"错误：无法读取 {p}（{e.strerror or e}）", file=sys.stderr)
        sys.exit(2)


def cmd_extract(paths, out):
    merged = {"sources": [str(p) for p in paths], "numbers": {}, "sample_sizes": set(),
              "fig_refs": set(), "citations": set(), "abbreviations": set(), "abbr_definitions": {},
              "strong_claim_words": set(), "caveats": {}, "causal_words": set(), "correl_words": set(),
              "advice_words": set(), "asserted_subject_tier_idx": set()}
    for p in paths:
        d = scan(read_text_or_exit(p))
        for k, v in d["numbers"].items():
            merged["numbers"].setdefault(k, []).extend(v)
        for key in ("sample_sizes", "fig_refs", "citations", "abbreviations", "strong_claim_words",
                    "causal_words", "correl_words", "advice_words", "asserted_subject_tier_idx"):
            merged[key].update(d[key])
        merged["abbr_definitions"].update(d["abbr_definitions"])
        for name, exs in d["caveats"].items():
            merged["caveats"].setdefault(name, []).extend(exs)
    for key in ("sample_sizes", "fig_refs", "citations", "abbreviations", "strong_claim_words",
                "causal_words", "correl_words", "advice_words", "asserted_subject_tier_idx"):
        merged[key] = sorted(merged[key])
    pathlib.Path(out).write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"台账已写入 {out}：数字 {len(merged['numbers'])}，图表 {len(merged['fig_refs'])}，"
          f"引用 {len(merged['citations'])}，限定语 {len(merged['caveats'])} 组")


def genre_compliance(genre, text):
    if genre not in GENRE_SECTIONS:
        return {"genre": genre, "pass": None, "note": "未知体裁，跳过结构检查"}
    missing = [name for name, words in GENRE_SECTIONS[genre].items() if not any(w in text for w in words)]
    if not re.search(r"^#+", text, re.M):
        missing.append("标题")
    return {"genre": genre, "missing_required": missing, "pass": not missing}


def cmd_check(ledger_path, draft_path, out, genre=None):
    try:
        led = json.loads(read_text_or_exit(ledger_path))
    except json.JSONDecodeError as e:
        print(f"错误：台账不是合法 JSON：{ledger_path}（{e}）", file=sys.stderr)
        sys.exit(2)
    draft = read_text_or_exit(draft_path)
    d = scan(draft)
    digits = lambda keys: {re.match(r"^(\d+(?:\.\d+)?)", k).group(1) for k in keys if re.match(r"^\d", k)}
    src_nums, drf_nums = set(led["numbers"].keys()), set(d["numbers"].keys())
    src_dig, drf_dig = digits(src_nums), digits(drf_nums)
    added = sorted(k for k in drf_nums - src_nums if re.match(r"^\d", k) and
                   re.match(r"^(\d+(?:\.\d+)?)", k).group(1) not in src_dig)
    missing = sorted(k for k in src_nums - drf_nums if re.match(r"^\d", k) and
                     re.match(r"^(\d+(?:\.\d+)?)", k).group(1) not in drf_dig)

    drf_numkeys, drf_4g = num_keys(draft), cn_4grams(draft)
    caveats_missing = []
    for name, words in CAVEATS:
        exs = led.get("caveats", {}).get(name, [])
        if not exs:
            continue
        kept = [s for s in exs if claim_retained(s, drf_numkeys, drf_4g)]
        if kept and not any(w in draft for w in words):
            caveats_missing.append([name, kept])

    src_causal = set(led.get("causal_words", []))
    causal_escalation = [[w, ex, bool(led.get("correl_words"))]
                         for w, ex in sorted(asserted(CAUSAL, draft).items()) if w not in src_causal]
    src_advice = set(led.get("advice_words", []))
    advice_escalation = [[w, ex] for w, ex in sorted(asserted(ADVICE, draft).items()) if w not in src_advice]

    src_max = max(led.get("asserted_subject_tier_idx", [])) if led.get("asserted_subject_tier_idx") else -1
    subj_draft = re.sub(r"pre[-\s]?clinical", "PRECLIN", draft, flags=re.I)
    extrapolation_escalation = []
    for i in sorted(subject_tiers(draft)):
        if i in (1, 2, 3) and i > src_max:
            tier = SUBJECT_TIERS[i][0]
            for w in SUBJECT_TIERS[i][1]:
                if w in subj_draft:
                    for s in sentences(subj_draft):
                        if w in s and not in_caveat(s) and not in_neg(s):
                            extrapolation_escalation.append([tier, w, s[:100]])
                            break

    report = {
        "added_numbers_not_in_source": [[k, d["numbers"][k]] for k in added],
        "source_numbers_missing_in_draft": [[k, led["numbers"][k]] for k in missing],
        "fig_refs_missing": sorted(set(led["fig_refs"]) - set(d["fig_refs"])),
        "citations_missing": sorted(set(led["citations"]) - set(d["citations"])),
        "strong_word_escalation": sorted(set(w for w in STRONG if w in draft) - set(led.get("strong_claim_words", []))),
        "unexplained_abbreviations": sorted(a for a in (set(d["abbreviations"]) - STOP)
            if a not in d["abbr_definitions"] and a not in led.get("abbr_definitions", {})),
        "caveats_missing": caveats_missing,
        "advice_escalation": advice_escalation,
        "causal_escalation": causal_escalation,
        "extrapolation_escalation": extrapolation_escalation,
        "genre_compliance": genre_compliance(genre, draft) if genre else None,
    }
    pathlib.Path(out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    gc = report["genre_compliance"]
    print(f"核验报告已写入 {out}：新增数字 {len(added)}，遗漏 {len(missing)}，强度越级 "
          f"{len(report['strong_word_escalation'])}，限定语丢失 {len(caveats_missing)}，"
          f"建议/因果/外推越级 {len(advice_escalation)}/{len(causal_escalation)}/{len(extrapolation_escalation)}")
    if gc and gc["pass"] is False:
        print("体裁结构缺项：" + "、".join(gc["missing_required"]))
    if added:
        print("警告：改写稿含源文之外的数字，须删除或改写后重核。", file=sys.stderr)


def main(argv):
    if len(argv) < 3 or argv[1] not in ("extract", "check"):
        print(__doc__)
        return 2
    mode, rest = argv[1], argv[2:]
    out = "fact_ledger.json" if mode == "extract" else "check_report.json"
    genre, pos, i = None, [], 0
    while i < len(rest):
        a = rest[i]
        if a == "-o":
            out, i = rest[i + 1], i + 2
        elif a == "--genre":
            genre, i = rest[i + 1], i + 2
        else:
            pos.append(a)
            i += 1
    if mode == "extract":
        if not pos:
            print("用法：fact_tools.py extract <材料文件...> [-o out.json]", file=sys.stderr)
            return 2
        cmd_extract(pos, out)
    else:
        if len(pos) < 2:
            print("用法：fact_tools.py check <台账.json> <改写稿> [--genre 体裁] [-o out.json]", file=sys.stderr)
            return 2
        cmd_check(pos[0], pos[1], out, genre)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
