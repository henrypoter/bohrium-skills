#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rd_check.py v3 - 结果与讨论章节一致性核查(仅标准库)。

用法: python3 rd_check.py <draft.md> <sources.json> [report.json]
核查 structure/discussion_block/purity/fig_ref/number/claim/statcheck/
source_consistency; 退出码 0=无 fail,1=有 fail,2=文件错误。
统计量重算仅 t/z(近似), 只 warn 不 fail。
v3 修复(均由 bench/cases 夹具复现后修复):
 - 数值匹配容差改按正文书写精度, 多候选取最接近者(v2 会把 4.8 错配到 n=5);
 - spin 词表剥离术语"有效数字"(v2 误杀), 补"改善/有益";
 - "结果与讨论"合并标题不再把讨论段当结果段扫 purity(v2 假阳性), 改为结构 warn;
 - NEG 补"无法判断显著"等诚实降调写法; 支持负统计量; ±窗口放宽。
"""
import json, math, re, sys

NUM_RE = re.compile(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(%|[a-zA-Zμ°/·²³]+)?')
FIG_RE = re.compile(r'(?:图|表)\s*S?\d+[A-Za-z]?|(?:Fig(?:ure)?|Table)\.?\s*S?\d+[A-Za-z]?', re.I)
TEST_RE = re.compile(r'(?i)(?<![A-Za-z])(t|z)\s*(?:\(\s*(\d+)\s*\))?\s*=\s*(-?\d+(?:\.\d+)?)')
P_RE = re.compile(r'(?i)p\s*(<|≤|>|≥|=)\s*(0?\.\d+)')
SRC_RE = re.compile(r'[\[(]([A-Za-z]{1,5}\d+)[\])]')  # 来源标注 id 前缀不限于 S(v2 只认 S# 误伤 P#/D#)
DISP_TYPE_RE = re.compile(r'(?i)(SD|SEM|SE|CI|95%[ ]?CI|IQR|MAD)')
DISP_TYPES = {"SD", "SEM", "SE", "CI", "95% CI", "95%CI", "IQR", "MAD"}

CAUSAL = ["证明", "证实", "导致", "因果", "决定性",
          "prove", "demonstrat", "caus", "determin"]
SIGNIF = ["显著", "significant"]
SPIN = ["获益", "明显改善", "显著改善", "明显优于", "疗效", "有效", "趋好",
        "改善", "有益", "benefit", "improvement", "superior", "efficac"]
# 术语剥离: 含 SPIN 子串但非获益宣称的固定术语, 扫描前剔除
TERM = ["有效数字", "显著性水平", "显著性检验"]
HEDGE = ["提示", "可能", "推测", "关联", "相关", "倾向", "趋势",
         "suggest", "associat", "may", "might", "likely", "trend",
         "appear", "possibly", "probab"]
NEG = ["未达显著", "未达到显著", "未达统计学显著", "无显著差异", "未见显著",
       "差异无统计学意义", "无统计学意义", "不显著", "未显著", "无显著",
       "no significant", "not significant", "non-significant", "nonsignificant",
       "不能确定因果", "无法确定因果", "因果性无法", "不能推断因果",
       "无因果", "不存在因果", "非因果", "not causal", "non-causal",
       "无法判断显著", "不能判断显著", "难以判断显著", "是否显著",
       "显著性无法", "显著性尚不", "尚不显著", "未见统计学意义"]

PURITY_VERB = ["表明", "说明", "提示", "暗示", "因为", "由于", "归因于",
               "推断", "意味着", "机制", "implies", "indicates",
               "suggests", "attribut", "because", "due to"]
PURITY_CITE = [re.compile(r'\[C\d+\]'), re.compile(r'et al', re.I),
               re.compile(r'报道'), re.compile(r'文献')]

DIM = {"structure": "任务完成度", "discussion_block": "结果完整性",
       "purity": "结果正确性", "fig_ref": "结果完整性",
       "number": "结果可核验性", "claim": "结果正确性",
       "statcheck": "结果正确性", "source_consistency": "结果正确性"}

BLOCK = {"主要发现复述": ["主要发现", "本研究发现", "综上", "main finding"],
         "文献对比": ["文献", "一致", "不一致", "报道", "既往", "literature"],
         "机制解释": ["机制", "推测", "可能原因", "mechanism", "hypothes"],
         "局限性": ["局限", "限制", "不足", "limitation"]}


def norm_fig(s):
    m = re.search(r'(S)?\s*(\d+)', s, re.I)
    return ("S" if m and m.group(1) else "") + str(int(m.group(2))) if m else s.strip().lower()


def tok_dec(tok):
    """正文数字字面量的小数位数(书写精度)。"""
    return len(tok.split(".")[1]) if "." in tok else 0


def close_tok(tok, src_val):
    """容差按正文书写精度: 四舍五入误差 <= 0.5*10^-dec。
    (v2 以来源精度定容差, 整数来源容差±0.5 会把 4.8 错配到 5。)"""
    try:
        v = float(tok)
    except ValueError:
        return False
    return abs(v - src_val) <= 0.5 * 10 ** (-tok_dec(tok)) + abs(src_val) * 1e-12 + 1e-12


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


SENT_END = re.compile(r'.*?(?:[。．!?；;]|(?<!\d)\.(?!\d))', re.S)


def clean(s):
    lines = [ln for ln in s.split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    return " ".join(ln.strip() for ln in lines)


def iter_sentences(text):
    pos = 0
    for m in SENT_END.finditer(text):
        s = clean(m.group(0))
        if s:
            yield s, line_of(text, m.start())
        pos = m.end()
    base = line_of(text, pos)
    for j, ln in enumerate(text[pos:].split("\n")):
        if ln.strip() and not ln.lstrip().startswith("#"):
            yield ln.strip(), base + j


def split_sections(text):
    """返回 (结果段, 讨论段, 合并标题标志)。
    "结果与讨论"合并标题时两节不可区分: 返回合并标志, 由调用方告警并跳过
    purity/discussion_block, 避免把讨论内容当结果段误扫。"""
    lines, res_idx, disc_idx = text.split("\n"), None, None
    merged = False
    for i, ln in enumerate(lines):
        if not re.match(r'^#{1,6}\s', ln):
            continue
        t = ln.strip().strip('#').strip()
        low = t.lower()
        has_res = '结果' in t or 'result' in low
        has_disc = '讨论' in t or 'discussion' in low
        if has_res and has_disc:
            merged = True
            continue
        if res_idx is None and has_res:
            res_idx = i
        if disc_idx is None and has_disc:
            disc_idx = i
    if merged and res_idx is None and disc_idx is None:
        return "", "", True
    if res_idx is None and disc_idx is None:
        return "", "", merged
    if res_idx is None:
        res = ""
    else:
        end = disc_idx if (disc_idx is not None and res_idx < disc_idx) else len(lines)
        res = "\n".join(lines[res_idx:end])
    disc = "" if disc_idx is None else "\n".join(lines[disc_idx:])
    return res, disc, merged


def betacf(a, b, x):
    EPS, FPMIN = 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d, h = 1.0 / d, 1.0 / d
    for m in range(1, 101):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        dsc = d * c
        h *= dsc
        if abs(dsc - 1.0) < EPS:
            break
    return h


def betai(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                  + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * betacf(a, b, x) / a
    return 1.0 - bt * betacf(b, a, 1.0 - x) / b


def pval(test, stat, df):
    t = (test or "").lower()
    if t == "z":
        return math.erfc(abs(stat) / math.sqrt(2.0))
    if t == "t" and df:
        return betai(df / 2.0, 0.5, df / (df + stat * stat))
    return None


def p_ok(op, rep, calc):
    if op == "=":
        return abs(rep - calc) <= 0.05
    if op in ("<", "≤"):
        return calc <= rep + 0.02
    return calc >= rep - 0.02


def check_structure(text):
    items = []
    if not re.search(r'结果|Result', text):
        items.append({"level": "fail", "kind": "structure", "msg": "缺结果(Results)部分"})
    if not re.search(r'讨论|Discussion', text):
        items.append({"level": "fail", "kind": "structure", "msg": "缺讨论(Discussion)部分"})
    if not re.search(r'局限|Limitation', text):
        items.append({"level": "warn", "kind": "structure", "msg": "缺局限性小节"})
    return items


def check_discussion_blocks(disc):
    items = []
    for b, anchors in BLOCK.items():
        if disc.strip() and not any(a in disc for a in anchors):
            items.append({"level": "warn", "kind": "discussion_block",
                          "loc": line_of(disc, 0), "msg": "讨论缺%s落位" % b})
    return items


def check_purity(res):
    items = []
    for s, ln in iter_sentences(res):
        v = next((x for x in PURITY_VERB if x in s), None)
        if v:
            items.append({"level": "warn", "kind": "purity", "loc": ln,
                          "msg": "结果段含解释词'%s'，请移至讨论: %s" % (v, s[:40])})
        if any(r.search(s) for r in PURITY_CITE):
            items.append({"level": "warn", "kind": "purity", "loc": ln,
                          "msg": "结果段出现文献引用，请移至讨论: %s" % s[:40]})
    return items


def check_fig_refs(text, src):
    declared = {norm_fig(x) for x in src.get("figures", []) + src.get("tables", [])}
    items, seen = [], set()
    for m in FIG_RE.finditer(text):
        c = norm_fig(m.group(0))
        if c not in declared:
            items.append({"level": "fail", "kind": "fig_ref", "loc": line_of(text, m.start()),
                          "msg": "正文引用不存在的图表: %s" % m.group(0)})
        seen.add(c)
    for d in sorted(declared - seen):
        items.append({"level": "warn", "kind": "fig_ref", "msg": "材料图表未被正文引用: %s" % d})
    return items


def mask(text):
    text = FIG_RE.sub(lambda m: " " * len(m.group(0)), text)
    text = TEST_RE.sub(lambda m: " " * len(m.group(0)), text)
    return re.sub(r'(?m)^(#{1,6}\s*)[\d.]+(\s*)',
                  lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), text)


def check_numbers(orig, vals):
    text = mask(orig)
    items, used, prev = [], set(), None
    for m in NUM_RE.finditer(text):
        try:
            v = float(m.group(1))
        except ValueError:
            continue
        if 1900 <= v <= 2100:
            continue
        unit = (m.group(2) or "").strip()
        if "±" in text[max(0, m.start() - 4):m.start()] and prev:
            e = next((x for x in vals if x["id"] == prev), None)
            if e and "disp" in e and close_tok(m.group(1), float(e["disp"])):
                # 误差棒类型核验：±值后若标注 SD/SEM/CI 等且与来源不一致则 warn
                after = orig[m.end():m.end() + 24]
                dm = DISP_TYPE_RE.search(after)
                if dm and e.get("disp_type") and \
                        dm.group(1).upper().replace(" ", "") != str(e["disp_type"]).strip().upper().replace(" ", ""):
                    items.append({"level": "warn", "kind": "number", "loc": line_of(orig, m.start()),
                                  "src": prev, "msg": "离差类型不符：来源 %s 标注 %s，正文写 %s" %
                                  (prev, e["disp_type"], dm.group(1))})
                continue
            items.append({"level": "warn", "kind": "number", "loc": line_of(orig, m.start()),
                          "src": prev, "msg": "离差 ±%s%s 未在 %s 记录 disp: ...%s..." %
                          (m.group(1), unit, prev,
                           orig[max(0, m.start() - 20):m.end() + 8].replace("\n", " "))})
            continue
        cands = [e for e in vals if close_tok(m.group(1), e["value"]) and
                 (not e.get("unit") or not unit or e["unit"] == unit)]
        # 多候选取与正文值最接近者, 避免低精度来源抢占(v2 错配 4.8->n=5)
        hit = min(cands, key=lambda e: abs(v - e["value"])) if cands else None
        if hit:
            used.add(hit["id"])
            prev = hit["id"]
        else:
            items.append({"level": "warn", "kind": "number", "loc": line_of(orig, m.start()),
                          "msg": "数值 %s%s 未回溯到来源: ...%s..." %
                          (m.group(1), unit,
                           orig[max(0, m.start() - 25):m.end() + 10].replace("\n", " "))})
    return items, used


def check_claims(text, src):
    vals = src.get("values", [])
    sig = {v["id"] for v in vals if v.get("significant") is True}
    insig = {v["id"] for v in vals if v.get("significant") is False}
    items = []
    for s, ln in iter_sentences(text):
        cited = set(SRC_RE.findall(s))
        scan = s
        for t in TERM:
            scan = scan.replace(t, "")
        for n in NEG:
            scan = scan.replace(n, "")
        spin = any(w in scan for w in SPIN)
        signif_word = any(w in scan for w in SIGNIF)
        causal_word = any(w in scan for w in CAUSAL)
        if not (spin or signif_word or causal_word):
            continue
        hedge = any(w in s for w in HEDGE)
        neg = any(n in s for n in NEG)
        c_sig = cited & sig
        c_insig = cited & insig
        if cited and c_insig and not c_sig:
            items.append({"level": "fail", "kind": "claim", "loc": ln,
                          "src": ",".join(sorted(c_insig)),
                          "msg": "对不显著数据用强/获益表述: %s" % s[:50]})
        elif signif_word and not c_sig:
            items.append({"level": "warn", "kind": "claim", "loc": ln,
                          "msg": "宣称显著但未挂显著来源[S#]: %s" % s[:50]})
        elif spin and not c_sig:
            items.append({"level": "warn", "kind": "claim", "loc": ln,
                          "msg": "获益类表述请核对证据: %s" % s[:50]})
        elif causal_word and not hedge and not neg:
            items.append({"level": "warn", "kind": "claim", "loc": ln,
                          "msg": "强因果表述无缓冲词: %s" % s[:50]})
    return items


def check_stat_inline(text):
    items = []
    for s, ln in iter_sentences(text):
        for tm in TEST_RE.finditer(s):
            pm = P_RE.search(s)
            if not pm:
                continue
            calc = pval(tm.group(1), float(tm.group(3)),
                        int(tm.group(2)) if tm.group(2) else None)
            if calc is not None and not p_ok(pm.group(1), float(pm.group(2)), calc):
                items.append({"level": "warn", "kind": "statcheck", "loc": ln,
                              "msg": "重算 p≈%.4f 与正文 p%s%s 不一致: %s" %
                              (calc, pm.group(1), pm.group(2), s[:50])})
    return items


def check_source_consistency(src):
    items = []
    for v in src.get("values", []):
        p = v.get("p")
        try:
            pv = float(p) if p is not None else None
        except (TypeError, ValueError):
            pv = None
        sig = v.get("significant")
        if sig in (True, False) and pv is not None:
            if (sig is True and pv > 0.05) or (sig is False and pv < 0.05):
                items.append({"level": "warn", "kind": "source_consistency", "src": v["id"],
                              "msg": "%s 的 significant=%s 与 p=%s 矛盾" % (v["id"], sig, p)})
        # 误差棒含义：有离差必须标注类型 SD/SEM/CI 等，类型非法或缺失即无法核验
        if v.get("disp") is not None:
            dt = str(v.get("disp_type", "")).strip()
            if dt.upper() not in DISP_TYPES:
                items.append({"level": "warn", "kind": "source_consistency", "src": v["id"],
                              "msg": "%s 有离差 %s 但 disp_type 缺失或非法(%r)，误差棒含义无法核验" %
                              (v["id"], v["disp"], v.get("disp_type"))})
        if v.get("test") and v.get("stat") is not None and pv is not None:
            calc = pval(v["test"], float(v["stat"]), v.get("df"))
            if calc is not None and abs(pv - calc) > 0.05:
                items.append({"level": "warn", "kind": "statcheck", "src": v["id"],
                              "msg": "%s 记录 p=%s 与 %s=%s(df=%s) 重算≈%.4f 不一致" %
                              (v["id"], p, v["test"], v["stat"], v.get("df", "-"), calc)})
    return items


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    try:
        text = open(sys.argv[1], encoding="utf-8").read()
        src = json.load(open(sys.argv[2], encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("读入失败: %s" % e, file=sys.stderr)
        return 2
    vals = src.get("values", [])
    res, disc, merged = split_sections(text)
    items = check_structure(text)
    if merged:
        items.append({"level": "warn", "kind": "structure",
                      "msg": "结果与讨论合并为一节, 请拆分为独立标题(合并时纯净度/落位检查跳过)"})
    else:
        items += check_discussion_blocks(disc) + check_purity(res)
    items += check_fig_refs(text, src)
    num_items, used = check_numbers(text, vals)
    items += num_items + check_claims(text, src) + check_stat_inline(text) + \
        check_source_consistency(src)
    for v in vals:
        if v["id"] not in used and not (v.get("test") and v.get("stat") is not None):
            items.append({"level": "info", "kind": "number", "src": v["id"],
                          "msg": "来源数值未使用: %s (%s)" % (v["id"], v.get("desc", ""))})
    n_fail = sum(1 for i in items if i["level"] == "fail")
    n_warn = sum(1 for i in items if i["level"] == "warn")
    by_kind, by_dim = {}, {}
    for i in items:
        by_kind[i["kind"]] = by_kind.get(i["kind"], 0) + 1
        d = by_dim.setdefault(DIM.get(i["kind"], "其他"), {"fail": 0, "warn": 0, "info": 0})
        d[i["level"]] += 1
    report = {"summary": {"fail": n_fail, "warn": n_warn, "total_values": len(vals),
                          "used_values": len(used), "by_kind": by_kind,
                          "by_score_dimension": by_dim}, "items": items}
    blob = json.dumps(report, ensure_ascii=False, indent=1)
    if len(sys.argv) > 3:
        open(sys.argv[3], "w", encoding="utf-8").write(blob)
    print(blob)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
