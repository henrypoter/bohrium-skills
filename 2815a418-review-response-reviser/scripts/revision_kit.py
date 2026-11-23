#!/usr/bin/env python3
"""revision_kit.py — 审稿返修辅助工具（仅标准库）。分类仅是建议，最终判断由 Agent 确认。
  inventory <基线稿> <意见清单> <out_dir> -> comments_parsed.json+anchors.json（类型/严重度/处置级别L1-L4/引文mismatch/锚点行号）
  matrix <comments_parsed.json> <matrix.md> -> 意见-回复-修改三列闭环矩阵骨架
  verify <修订稿> <回复信> <comments_parsed.json> <report.json> -> 五查报告, fail 退出码 1
  trace <基线稿> <修订稿> <changes.diff> -> unified diff
"""
import sys, re, json, os, difflib, bisect

HEAD_RE = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:(?:Reviewer|审稿人|评审)\s*([A-Za-z0-9一二三四五六]+))?'
    r'[\s:：,，.-]*(?:(?:Major|Minor|major|minor)\s+)?(?:Comment|意见|comment)?\s*'
    r'(?:R(\d+)[.\-_](\d+)|(\d+(?:\.\d+)*))\s*[.、\)）:：]?\s*(.*)$')
BULLET_RE = re.compile(r'^\s*(?:[-*•]|\(\d+\)|（\d+）|[a-z]\)|\d+[\.、\)）])\s*(.+)$')
ANCHOR_RE = re.compile(r'[「『]([^」』]{6,120})[」』]|`([^`]{6,120})`')
PAIR_Q_RE = re.compile(r'[「『“]([^」』”]{6,120})[」』”]|`([^`]{6,120})`')


def extract_quotes(text):
    """抽取引文片段：成对引号直接配对；直双引号按出现顺序两两配对，
    避免 `"a"......"b"` 中把两段引文之间的正文误配成一段引文。"""
    out = [m.group(1) or m.group(2) for m in PAIR_Q_RE.finditer(text)]
    parts = text.split('"')
    out += [p for p in parts[1:-1:2] if 6 <= len(p) <= 120]
    return out

TYPE_KW = [
    ("方法", ["方法", "设计", "method", "approach", "protocol", "模型", "算法"]),
    ("数据", ["数据", "实验", "图", "表", "统计", "样本", "data", "experiment",
              "figure", "table", "sample", "result"]),
    ("伦理", ["伦理", "ethic", "consent", "知情同意", "利益冲突"]),
    ("格式", ["格式", "参考文献", "引用格式", "format", "citation"]),
    ("写作", ["写作", "语言", "表述", "语法", "typo", "grammar", "writing",
              "clarity", "措辞", "摘要", "标题"]),
]
SEV_KW = [
    ("重大", ["重大", "major", "fatal", "flaw", "重做", "缺实验", "补充实验", "补实验", "补做",
              "missing experiment", "more data", "invalid", "不成立", "严重",
              "样本量太小", "样本不足", "sample size", "insufficient"]),
    ("澄清", ["澄清", "clarif", "解释", "为何", "why", "how ", "不清楚", "unclear"]),
    ("次要", ["次要", "minor", "typo", "建议", "suggest", "格式", "润色", "polish"]),
]
DISP_KW = [
    ("L4", ["拒绝执行", "无法执行", "无法补做", "超出", "impossible", "not feasible", "out of scope"]),
    ("L3", ["反驳", "误解", "不成立", "错误", "质疑", "reject", "disagree", "incorrect"]),
    ("L2", ["部分", "酌情", "考虑", "建议", "可", "partially", "consider", "suggest", "would", "could"]),
]
DIRECTIVE = re.compile(r'(请|应|需要|建议|补充|修改|删除|增加|解释|说明|核对|引用|重做|'
                       r'please|add|clarify|explain|remove|revise|cite|provide|expand|should|must)', re.I)
REVIEWER_ONLY_RE = re.compile(
    r'^\s*(?:#{1,6}\s*)?(?:Reviewer|审稿人|评审)\s*([A-Za-z0-9一二三四五六]+)\s*[:：]?\s*$')
REBUT = ("不采纳", "礼貌反驳", "无法执行", "无法补做", "拒绝执行")
EVID = ("证据", "依据", "理由", "原因", "替代", "文献", "材料", "稿件", "数据", "说明", "节", "图", "表")
BUFF = ("感谢", "谢谢", "尊重", "理解", "关切", "认同", "认可", "建议", "考虑", "请编辑")
TONE = ["审稿人错了", "理解有误", "显然错误", "显然不成立", "无须修改", "无需修改",
        "没有必要", "荒谬", "莫名其妙", "不可理喻", "没读懂",
        "you are wrong", "obviously wrong", "ridiculous", "nonsense", "wrong about"]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def norm(s):
    return re.sub(r'\s+', '', s)


def parse_comments(text):
    items, cur, cur_rev = [], None, ""
    for line in text.splitlines():
        rm = REVIEWER_ONLY_RE.match(line)
        if rm:
            cur_rev, cur = rm.group(1), None
            continue
        m = HEAD_RE.match(line)
        if m and (m.group(2) or m.group(4)) and (m.group(5) or "").strip():
            rev = m.group(1) or cur_rev
            rid = ("R%s.%s" % (m.group(2), m.group(3))) if m.group(2) else (
                ("R%s.%s" % (rev, m.group(4))) if rev else m.group(4))
            cur = {"id": str(rid), "reviewer": rev, "head": m.group(5).strip(), "raw": [], "subs": []}
            items.append(cur)
            continue
        if cur is None:
            continue
        cur["raw"].append(line)
        b = BULLET_RE.match(line)
        if b:
            cur["subs"].append(b.group(1).strip())
    for it in items:
        body = " ".join(x.strip() for x in it["raw"] if x.strip())
        if not it["subs"]:
            sents = [s.strip() for s in re.split(r'[。；;！？!?]|(?<=[.!?])\s+', body) if len(s.strip()) >= 4]
            it["subs"] = [s for s in sents if DIRECTIVE.search(s)] or ([body] if body else [it["head"]])
        it["raw"] = body or it["head"]
        del it["head"]
    return items


def classify(text):
    t = text.lower()
    typ = next((k for k, kws in TYPE_KW if any(w.lower() in t for w in kws)), "写作")
    sev = next((k for k, kws in SEV_KW if any(w.lower() in t for w in kws)), "次要")
    disp = next((k for k, kws in DISP_KW if any(w.lower() in t for w in kws)), "L1")
    return {"type": typ, "severity_suggestion": sev, "disposition": disp}


def build_anchors(text):
    anchors, para_no = [], 0
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            anchors.append({"kind": "heading", "line": i, "text": s.lstrip("# ").strip()})
        else:
            para_no += 1
            anchors.append({"kind": "para", "line": i, "para": para_no, "text": s[:40]})
    return anchors


def locate(rev_lines, q):
    # 全文去空白后检索，锚点跨行（修订稿换行拆开）也能命中，再映射回行号
    qn = norm(q)
    joined, starts = [], []
    for l in rev_lines:
        starts.append(sum(len(x) for x in joined))
        joined.append(norm(l))
    joined = "".join(joined)
    idx = joined.find(qn)
    if idx < 0:
        return None, None
    i = bisect.bisect_right(starts, idx)  # 1-based 行号
    h = ""
    for j in range(i - 1, -1, -1):
        s = rev_lines[j].strip()
        if s.startswith("#"):
            h = s.lstrip("# ").strip()
            break
    return i, h


def id_pattern(cid):
    # 编号边界匹配：R1.1 不被 R1.10 / R11.1 误命中；无审稿人前缀的裸编号允许信中带 R 前缀
    core = re.escape(cid)
    if not cid.upper().startswith("R"):
        core = r"[Rr]?" + core
    return re.compile(r"(?<![\d.])" + core + r"(?![\d.])", re.I)


def blocks_by_id(letter):
    heads = [(m.start(), m.group(1)) for m in re.finditer(
        r'(?m)^\s{0,3}#{1,6}\s*(?:回复|Response)\s*[\[【]?([Rr]?\d+(?:[.\-]\d+)*[a-zA-Z]?)[\]】]?', letter)]
    out = {}
    for k, (pos, rid) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(letter)
        out[rid.upper().lstrip("R")] = letter[pos:end]
    return out


def cmd_inventory(ms_path, cm_path, out_dir):
    ms, cm = read(ms_path), read(cm_path)
    ms_norm = norm(ms)
    items = parse_comments(cm)
    for it in items:
        subs = []
        for s in it["subs"]:
            c = classify(it["raw"] + " " + s)
            subs.append({"text": s, "type": c["type"],
                         "severity_suggestion": c["severity_suggestion"],
                         "disposition": c["disposition"]})
        it["subs"] = subs
        it.update(classify(it["raw"]))
        it["quoted_missing"] = [q for q in extract_quotes(it["raw"])
                                if norm(q) not in ms_norm]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "comments_parsed.json"), "w", encoding="utf-8") as f:
        json.dump({"comment_count": len(items),
                   "sub_requirement_count": sum(len(i["subs"]) for i in items),
                   "items": items}, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, "anchors.json"), "w", encoding="utf-8") as f:
        json.dump(build_anchors(ms), f, ensure_ascii=False, indent=1)
    print("items=%d subs=%d mismatch_quotes=%d" % (
        len(items), sum(len(i["subs"]) for i in items),
        sum(len(i["quoted_missing"]) for i in items)))


def cmd_matrix(parsed_path, out_path):
    items = json.load(open(parsed_path, encoding="utf-8"))["items"]
    rows = []
    for it in items:
        for s in it["subs"]:
            rows.append((it["id"], s["type"], s.get("severity_suggestion", ""),
                         s.get("disposition", ""), s["text"][:48]))
    lines = ["| 原子意见（编号[类别/严重度/处置级别]） | 回复条目（决策+摘要） | 修改位置锚点（修订稿原文） |",
             "|---|---|---|"]
    for rid, typ, sev, disp, txt in rows:
        lines.append("| %s[%s/%s/%s] %s | [待填] | [待填] |" % (rid, typ, sev, disp, txt))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# 意见-回复-修改三列闭环矩阵\n\n"
                "> 机器生成骨架：回复/锚点列由 Agent 从真实改稿与 diff 回填；"
                "锚点须为修订稿原文片段并被 verify 检索。\n\n" + "\n".join(lines) + "\n")
    print("matrix rows=%d -> %s" % (len(rows), out_path))


def cmd_verify(rev_path, letter_path, parsed_path, report_path):
    rev_raw = read(rev_path)
    rev, letter = norm(rev_raw), read(letter_path)
    items = json.load(open(parsed_path, encoding="utf-8"))["items"]
    fails, warns = [], []
    for it in items:
        if not id_pattern(it["id"]).search(letter):
            fails.append({"check": "coverage", "item": it["id"], "msg": "回复信未覆盖该意见编号"})
    rev_lines = rev_raw.splitlines()
    claims, locs = [], []
    anchor_lines = [l for l in letter.splitlines() if "锚点" in l]
    if anchor_lines:
        claims = [q for l in anchor_lines for q in extract_quotes(l)]
    else:
        claims = [a or b for a, b in ANCHOR_RE.findall(letter)]
    for q in claims:
        line, heading = locate(rev_lines, q)
        if line is None:
            fails.append({"check": "location", "anchor": q[:60],
                          "msg": "锚点在修订稿中检索不到(不得虚构修改)"})
        else:
            locs.append({"anchor": q[:60], "line": line, "heading": heading})
    subs_total = sum(len(it.get("subs", [])) for it in items)
    dec = re.findall(r'(采纳|部分采纳|不采纳|无法执行|礼貌反驳|澄清)', letter)
    if len(dec) < subs_total:
        warns.append({"check": "decision", "msg": "决策词 %d 少于子要求总数 %d：确认每个子要求都有明确结论（答得全）" % (len(dec), subs_total)})
    elif len(dec) < len(items):
        warns.append({"check": "decision", "msg": "决策词少于意见数，确认每条都有采纳/部分采纳/不采纳结论"})
    blocks = blocks_by_id(letter)
    reb = []
    for it in items:
        bid = it["id"].upper().lstrip("R")
        b = blocks.get(bid, "")
        if not b:
            continue
        if any(w in b for w in REBUT):
            miss = []
            if not any(w in b for w in EVID):
                miss.append("证据/替代方案")
            if not any(w in b for w in BUFF):
                miss.append("缓冲语")
            if miss:
                reb.append({"item": it["id"], "missing": "+".join(miss)})
                fails.append({"check": "rebuttal_compliance", "item": it["id"],
                              "msg": "反驳/无法执行条目缺" + "+".join(miss)})
    # 逐意见核查：每个回复块须含明确决策词（答得全），比全局计数更精确
    for it in items:
        bid = it["id"].upper().lstrip("R")
        b = blocks.get(bid, "")
        if b and not any(w in b for w in ("采纳", "无法执行", "礼貌反驳", "澄清")):
            warns.append({"check": "decision", "item": it["id"],
                          "msg": "该意见回复块缺少明确决策词（采纳/部分采纳/不采纳/澄清等）"})
    tone = [w for w in TONE if w in letter]
    if tone:
        warns.append({"check": "tone", "hits": tone,
                      "msg": "对抗性措辞，建议改写为'表述责任+已澄清'句式"})
    report = {"comments_total": len(items), "sub_requirements_total": subs_total,
              "location_claims": len(claims),
              "anchor_locations": locs, "rebuttal_compliance": reb, "tone_hits": tone,
              "fail": fails, "warn": warns,
              "status": "fail" if fails else ("warn" if warns else "pass")}
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({"status": report["status"], "fail": len(fails), "warn": len(warns),
                      "anchors_located": len(locs)}, ensure_ascii=False))
    return 1 if fails else 0


def cmd_trace(base_path, rev_path, out_path):
    a, b = read(base_path).splitlines(True), read(rev_path).splitlines(True)
    diff = difflib.unified_diff(a, b, fromfile="baseline", tofile="revised", n=2)
    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(diff)
    print("diff lines=%d -> %s" % (sum(1 for _ in open(out_path, encoding='utf-8')), out_path))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "inventory":
        cmd_inventory(*sys.argv[2:5])
    elif cmd == "matrix":
        cmd_matrix(*sys.argv[2:4])
    elif cmd == "verify":
        sys.exit(cmd_verify(*sys.argv[2:6]))
    elif cmd == "trace":
        cmd_trace(*sys.argv[2:5])
    else:
        print("unknown command: " + cmd)
        sys.exit(2)
