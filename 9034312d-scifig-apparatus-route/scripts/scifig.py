#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scifig.py 装置/路线图渲染与校验(纯标准库)。

v5 新增(对齐 q3 实体关系型矢量图骨架):
A. source 双通道锚定 {locator, quote}: quote 归一化后须在材料中(找不到=疑似编造 fail),
   且落在 locator 区间(他处找到=位置错配 fail); 旧字符串格式降级 warn; 边与节点同款。
B. 箭头方向来源依据: 每条边在 locator 段落内 from 端实体先于 to 端=supported;
   反序=contradicted(fail); 依据缺失=降级 unknown(warn, 不臆造)并在 result.json 登记。
C. SVG 分层命名: layer-lanes/edges/entities/labels/legend/title, 边带 data-from/to/source/quote。
D. 六类检查点(实体逐字/连接语义/方向/图例/布局/导出)+渲染回读+figure.score 0-100;
   verdict=issues 仍 advisory(exit 0), 仅 SVG 硬伤 exit 1。
E. figure_map.md 人可读映射表(组件/连线 -> quote+定位+命中+方向依据状态)。
F. result.json 标准化: outputs 按角色、sources 覆盖率摘要、changes 取舍与人工确认。
另: 实体逐字核验(difflib top-3 建议)与 required 覆盖审计(缺失时 status 强制 partial)。
"""
import argparse, datetime, difflib, hashlib, json, os, platform, re, shlex, shutil, subprocess, sys, unicodedata
from xml.sax.saxutils import escape

NODE_FILL = {"default": "#e3f2fd", "milestone": "#fff3e0", "source": "#e8f5e9", "sink": "#efebe9"}
LAYERS = ["lanes", "edges", "entities", "labels", "legend", "title"]
FONT = "Arial,Helvetica,'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',sans-serif"
NUM_UNIT = re.compile(r"-?\d+(?:\.\d+)?\s?(?:µ|u|μ|m|n|k|M)?(?:g|L|mL|s|min|h|°C|%|MPa|kPa|bar|Hz|V|A|K)\b")
EDGE_RE = re.compile(r'<path id="edge-(\d+)"[^>]*?data-style="(\w+)"[^>]*?d="([^"]+)"[^>]*?fill="none"[^>]*?stroke="([^"]+)"([^>]*?)marker-end="url\(#ar-(\w+)\)"/>')
NUM_RE = re.compile(r'<g id="edge-(\d+)-num">.*?<text[^>]*>(\d+)</text></g>', re.S)
LEGEND_RE = re.compile(r'<g id="layer-legend">(.*?)</g>', re.S)
LAYER_RE = re.compile(r'<g id="(layer-[a-z]+)"')
PT_RE = re.compile(r"[ML]\s*(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
LOC_LINE = re.compile(r"^L?0*(\d+)(?:\s*[-–—~]\s*L?0*(\d+))?$", re.I)
LOC_SENT = re.compile(r"^(?:句|S)\s*0*(\d+)(?:\s*[-–—~]\s*(?:句|S)?\s*0*(\d+))?$", re.I)
BRACKETS = str.maketrans("", "", "（）()【】[]〈〉《》")

def load_rules():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "connection_rules.json")
    fb = {"sequence": {"stroke": "#37474f", "dash": ""}, "material": {"stroke": "#1565c0", "dash": ""},
          "energy": {"stroke": "#ef6c00", "dash": "7 4"}, "info": {"stroke": "#2e7d32", "dash": "2 3"},
          "reflux": {"stroke": "#757575", "dash": "6 3 2 3"}}
    try:
        d = json.load(open(p, encoding="utf-8")).get("rules")
        return d if isinstance(d, dict) and d else fb
    except Exception:
        return fb

STYLES = load_rules()

def esc(s):
    return escape(str(s), {'"': "&quot;"})

def norm(t):
    return re.sub(r"\s+", " ", str(t)).strip().lower()

def qnorm(t):
    """quote/实体核验归一化: NFKC + µ→μ + −→- + 连字符换行合并 + 空白折叠 + 小写。"""
    s = unicodedata.normalize("NFKC", str(t)).replace("µ", "μ").replace("−", "-")
    s = s.replace("-\r\n", "").replace("-\n", "")
    return re.sub(r"\s+", " ", s).strip().lower()

def toks(s):
    return re.findall(r"[一-鿿]{2,}|[A-Za-z][A-Za-z0-9./\-]{1,}", str(s))

def src_locator(s):
    return str(s.get("locator", "")) if isinstance(s, dict) else (str(s) if s else "")

def src_quote(s):
    return str(s.get("quote", "")) if isinstance(s, dict) else ""

def last_pt(d):
    p = PT_RE.findall(d)
    return (float(p[-1][0]), float(p[-1][1])) if p else None

def d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2

def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def xml_parse(p):
    import xml.dom.minidom
    return xml.dom.minidom.parse(p)

def read_materials(paths):
    raw = ""
    for p in paths or []:
        try:
            raw += "\n" + open(p, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print("WARN %s: %s" % (p, e), file=sys.stderr)
    return raw

def material_spans(raw):
    lines = raw.split("\n")
    sents = [s for s in re.split(r"(?<=[。；;！!？?])|\n", raw) if s.strip()]
    return lines, sents

def resolve_locator(loc, lines, sents):
    """locator 解析为材料片段: '句N'/'SN'=第N句; '句N-句M'=第N..M句区间;
    'L0003'/'L0003-L0005'/'3-5'=行区间。无法解析返回 None。"""
    m = LOC_SENT.match(loc.strip())
    if m:
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        if 1 <= a <= len(sents):
            return "".join(sents[a - 1:b])
        return None
    m = LOC_LINE.match(loc.strip())
    if m:
        a, b = int(m.group(1)), int(m.group(2) or m.group(1))
        tagged = [(int(re.match(r"^L(\d+)", ln).group(1)), ln) for ln in lines if re.match(r"^L\d{3,}\s", ln)]
        if tagged:
            sel = [ln for n, ln in tagged if a <= n <= b]
            return "\n".join(sel) if sel else None
        return "\n".join(lines[a - 1:b]) if 1 <= a <= len(lines) else None
    return None

def quote_audit(spec, raw, lines, sents):
    """双通道锚定: ①quote 归一化后在材料中存在(找不到=quote_missing fail=疑似编造);
    ②quote 落在 locator 解析出的区间内(他处找到=quote_misplaced fail=位置错配)。
    旧字符串 source 降级 legacy(warn)。返回行(供 figure_map)与各级问题列表。"""
    rows, missing, misplaced, legacy, toolong, unresolved = [], [], [], [], [], []
    have_mat = bool(raw.strip())
    hay = qnorm(raw)
    def one(kind, eid, label, s):
        base = {"element": "%s:%s(%s)" % (kind, eid, str(label).replace("\n", " ")[:24]),
                "kind": kind, "locator": "", "quote": "", "status": "—(未标来源)"}
        if not s:
            rows.append(base); return
        if not isinstance(s, dict):
            legacy.append(eid)
            rows.append(dict(base, locator=src_locator(s), status="旧格式字符串(warn,建议升级为{locator,quote})")); return
        loc, q = src_locator(s), src_quote(s)
        base.update(locator=loc, quote=q)
        if len(re.sub(r"\s+", "", q)) > 30:
            toolong.append(eid)
        nq = qnorm(q)
        if not nq:
            rows.append(dict(base, status="空quote(warn)")); unresolved.append(eid); return
        if not have_mat:
            rows.append(dict(base, status="无材料未核")); return
        if nq not in hay:
            missing.append(eid); rows.append(dict(base, status="未找到(fail,疑似编造)")); return
        span = resolve_locator(loc, lines, sents) if loc else None
        if span is None:
            unresolved.append(eid)
            rows.append(dict(base, status="命中(定位未解析,warn)"))
        elif nq not in qnorm(span):
            misplaced.append(eid); rows.append(dict(base, status="错配(fail,quote在%s他处)" % loc))
        else:
            rows.append(dict(base, status="命中"))
    for n in spec.get("nodes") or []:
        one("组件", n.get("id"), n.get("label", ""), n.get("source"))
    for i, e in enumerate(spec.get("edges") or []):
        one("连线", "edge-%d" % i, e.get("label") or "%s→%s" % (e.get("from"), e.get("to")), e.get("source"))
    return {"rows": rows, "missing": missing, "misplaced": misplaced, "legacy": legacy,
            "too_long": toolong, "unresolved": unresolved}

def entity_frags(label):
    """label/caption 拆为待核实体片段: 按换行/斜杠/顿号/逗号/空白切分,去括号与步骤编号,
    纯数值+单位片段豁免,长度<2 豁免。"""
    out = []
    for p in re.split(r"[\n/、，,\s]+", str(label)):
        p = re.sub(r"^\d+\s+(?=\S)", "", p).translate(BRACKETS).strip("：:;；。. ")
        if len(p) >= 2 and not NUM_UNIT.fullmatch(p):
            out.append(p)
    return out

def edge_frags(spec):
    """边端点 → 归一化实体片段列表(用于方向依据定位)。"""
    nodes = {n.get("id"): n for n in spec.get("nodes") or []}
    out = {}
    for nid, n in nodes.items():
        fs = [qnorm(f) for f in entity_frags(n.get("label", nid or "")) if qnorm(f)]
        out[nid] = fs
    return out

def direction_audit(spec, raw, lines, sents):
    """箭头流向来源依据: 每条边在其 source.locator 解析出的段落(不可解析则退全材料)中,
    from 端与 to 端的实体片段按 from→to 顺序出现=supported(有依据);
    反序(to 先于 from)=contradicted(fail, 疑似方向反了); 任一端/两端无法定位=降级 unknown(warn, 不臆造);
    无 source=unsourced(warn)。返回 by_edge(i->status) 供 result.json 登记。"""
    frags = edge_frags(spec)
    rows, by_edge, contradicted, unknown, unsourced = [], {}, [], [], []
    for i, e in enumerate(spec.get("edges") or []):
        f, t = e.get("from"), e.get("to")
        tag = "edge-%d" % i
        src = e.get("source")
        loc, q = src_locator(src), src_quote(src)
        base = {"element": "%s:%s→%s" % (tag, f, t), "locator": loc, "quote": q}
        if not isinstance(src, dict) or not q:
            unsourced.append(tag); by_edge[i] = "unsourced"
            rows.append(dict(base, status="未标来源(warn, 方向不可回溯)")); continue
        span = resolve_locator(loc, lines, sents) if loc else None
        text = span if span is not None else raw
        tn = qnorm(text)
        def first(fs):
            best = None
            for fr in fs:
                p = tn.find(fr)
                if p >= 0 and (best is None or p < best):
                    best = p
            return best
        if f == t:
            rows.append(dict(base, status="自环(方向检查跳过)")); by_edge[i] = "self"; continue
        fp, tp = first(frags.get(f, [])), first(frags.get(t, []))
        if fp is None and tp is None:
            unknown.append(tag); by_edge[i] = "unknown"
            rows.append(dict(base, status="方向依据缺失→降级 unknown(warn, 不臆造)"))
        elif fp is None or tp is None:
            unknown.append(tag); by_edge[i] = "unknown"
            rows.append(dict(base, status="仅一端可定位→降级 unknown(warn)"))
        elif fp < tp:
            by_edge[i] = "supported"
            rows.append(dict(base, status="supported(段落内 from 先于 to)"))
        else:
            contradicted.append(tag); by_edge[i] = "contradicted"
            rows.append(dict(base, status="矛盾(fail, 段落内 to 先于 from)"))
    return {"rows": rows, "by_edge": by_edge, "contradicted": contradicted,
            "unknown": unknown, "unsourced": unsourced}

def suggest(target, raw, n=3):
    """difflib top-3 建议: 材料按标点切段 + 等长滑窗候选。"""
    L = len(target); cands = set()
    for s in re.split(r"[^一-鿿A-Za-z0-9.%≥\-]+", raw):
        s = s.strip()
        if not s:
            continue
        if 2 <= len(s) <= L + 2:
            cands.add(s)
        for i in range(0, max(0, len(s) - L + 1)):
            cands.add(s[i:i + L])
    best = difflib.get_close_matches(target, sorted(cands), n=n, cutoff=0.4)
    return best or difflib.get_close_matches(target, sorted(cands), n=n, cutoff=0.0)

def entity_audit(spec, raw):
    """实体逐字核验: 节点 label / caption_steps 每个片段(去括号)归一化后须逐字出现在材料;
    未命中给 difflib top-3 建议。warn 级。需材料,无材料跳过。"""
    hay = qnorm(raw).translate(BRACKETS)
    mm = []
    def probe(owner, text):
        for f in entity_frags(text):
            if qnorm(f).translate(BRACKETS) not in hay:
                mm.append({"element": owner, "fragment": f, "suggestions": suggest(qnorm(f), raw)})
    for nd in spec.get("nodes") or []:
        probe(nd.get("id"), nd.get("label", ""))
        if nd.get("note"):
            probe(nd.get("id") + ":note", nd["note"])
    cap = spec.get("caption_steps") or spec.get("caption")
    if isinstance(cap, list):
        for j, c in enumerate(cap):
            probe("caption_steps[%d]" % j, c)
    return {"mismatch": mm}

def required_audit(spec):
    """required 覆盖审计: 题面点名必做项(spec.required)须被节点/连线 label 或图注逐字覆盖
    (归一化去空白)。缺失项禁止 status=success/complete(在 result 强制 partial)。"""
    req = [str(r) for r in spec.get("required") or []]
    pool = [n.get("label", "") for n in spec.get("nodes") or []]
    pool += [e.get("label", "") for e in spec.get("edges") or []]
    cap = spec.get("caption_steps") or spec.get("caption")
    pool += cap if isinstance(cap, list) else []
    hay = re.sub(r"\s+", "", qnorm(" ".join(str(x) for x in pool)))
    missing = [r for r in req if re.sub(r"\s+", "", qnorm(r)) not in hay]
    return {"required": req, "covered": len(req) - len(missing), "missing": missing}

def figure_score(rep):
    """figure.score 扣分配比(满分 100,下限 0;SVG 硬伤 invalid 直接 0):
    fail 级: required_missing 15/条; quote_missing 12/条; semantic/direction/dangling 10/条;
             quote_misplaced 8/条; numbering 8/条; trace(no_token/num_missing) 6/条; legend 5/条。
    warn 级: entity_mismatch 4/条; orphan 3/条; direction_unknown/unsourced 2/条;
             export 分层/字体缺 2/类; legacy_source 2/条; quote 过长/定位未解析 1/条。
    停止条件(写死): 先修 fail 再修 warn; score>=90 或剩余 warn 均可解释即停。"""
    q, tr, clo = rep.get("quote") or {}, rep.get("trace") or {}, rep.get("closure") or {}
    dr = rep.get("direction") or {}
    ex = rep.get("export") or {}
    d = {"semantic": 10 * len(rep.get("semantic", {}).get("bad", [])),
         "direction": 10 * len(dr.get("bad", [])),
         "numbering": 8 * len(rep.get("numbering", {}).get("bad", [])),
         "legend": 5 * len(rep.get("legend", {}).get("bad", [])),
         "dangling": 10 * len(clo.get("dangling", [])),
         "orphan": 3 * len(clo.get("orphans", [])),
         "direction_unknown": 2 * (len(dr.get("unknown", [])) + len(dr.get("unsourced", []))),
         "export_layer_font": 2 * (len(ex.get("layers_missing", [])) + (not ex.get("font_stack_ok", True))),
         "trace": 6 * (len(tr.get("no_token", [])) + len(tr.get("num_missing", []))) if tr else 0,
         "quote_missing": 12 * len(q.get("missing", [])),
         "quote_misplaced": 8 * len(q.get("misplaced", [])),
         "required_missing": 15 * len((rep.get("required") or {}).get("missing", [])),
         "entity_mismatch": 4 * len((rep.get("entity") or {}).get("mismatch", [])),
         "legacy_source": 2 * len(q.get("legacy", [])),
         "quote_minor": 1 * (len(q.get("too_long", [])) + len(q.get("unresolved", []))),
         "workorder_error": 10 * len((rep.get("workorder") or {}).get("errors", [])),
         "workorder_limitation": 2 * len((rep.get("workorder") or {}).get("limitations", []))}
    d = {k: v for k, v in d.items() if v}
    return max(0, 100 - sum(d.values())), d

def check_spec(spec):
    errs, warns = [], []
    kind = spec.get("kind")
    if kind not in ("apparatus", "route"):
        errs.append("bad kind: %r" % kind)
    nodes = spec.get("nodes") or []
    ids = {}
    for n in nodes:
        nid = n.get("id")
        if not nid:
            errs.append("node no id"); continue
        if nid in ids:
            errs.append("dup id: %s" % nid)
        ids[nid] = n
        if not n.get("label"): warns.append("no label: %s" % nid)
        s = n.get("source")
        if not s:
            warns.append("no source: %s" % nid)
        elif isinstance(s, dict) and (not s.get("locator") or not s.get("quote")):
            warns.append("source 缺 locator/quote: %s" % nid)
        elif not isinstance(s, dict):
            warns.append("legacy source string(warn): %s" % nid)
    seq = 0
    for i, e in enumerate(spec.get("edges") or []):
        st = e.get("style", "sequence")
        if st not in STYLES:
            errs.append("bad style e%d: %r" % (i, st))
        seq += st == "sequence"
        for k in ("from", "to"):
            if e.get(k) not in ids:
                errs.append("dangling e%d %s=%r" % (i, k, e.get(k)))
        s = e.get("source")
        if not s:
            warns.append("no source(方向不可回溯): e%d" % i)
        elif isinstance(s, dict) and (not s.get("locator") or not s.get("quote")):
            warns.append("source 缺 locator/quote: e%d" % i)
        elif not isinstance(s, dict):
            warns.append("legacy source string(warn): e%d" % i)
    if kind == "route":
        lanes = [l.get("id") for l in spec.get("lanes") or []]
        if not lanes: errs.append("no lanes")
        for n in nodes:
            if n.get("lane") not in lanes: errs.append("bad lane %s=%r" % (n.get("id"), n.get("lane")))
            if "order" not in n: warns.append("no order: %s" % n.get("id"))
    if kind == "apparatus":
        c = spec.get("canvas") or {}
        cw, ch = c.get("w", 1200), c.get("h", 800)
        for n in nodes:
            x, y = n.get("x"), n.get("y")
            if x is None or y is None:
                errs.append("no x/y: %s" % n.get("id")); continue
            w, h = n.get("w", 150), n.get("h", 56)
            if min(x - w / 2, y - h / 2) < 0 or x + w / 2 > cw or y + h / 2 > ch:
                warns.append("overflow %s" % n["id"])
    req = required_audit(spec)
    for r in req["missing"]:
        warns.append("required uncovered: %s" % r)
    return {"ok": not errs, "errors": errs, "warnings": warns, "node_count": len(ids),
            "edge_count": len(spec.get("edges") or []), "sequence_edges": seq,
            "required_missing": req["missing"]}

def layout(spec):
    if spec.get("kind") == "apparatus":
        pos = {n["id"]: (n.get("x", 80), n.get("y", 60), n.get("w", 150), n.get("h", 56)) for n in spec["nodes"]}
        c = spec.get("canvas") or {}
        W = c.get("w") or max([x + w / 2 for x, y, w, h in pos.values()] + [420]) + 60
        H = c.get("h") or max([y + h / 2 for x, y, w, h in pos.values()] + [300]) + 130
        return pos, int(W), int(H)
    lanes = spec.get("lanes") or [{"id": "L1", "label": "阶段1"}]
    by = {l["id"]: [] for l in lanes}
    for n in spec["nodes"]:
        by.setdefault(n.get("lane") or lanes[0]["id"], []).append(n)
    pos, maxc = {}, 1
    for li, l in enumerate(lanes):
        row = sorted(by.get(l["id"], []), key=lambda n: n.get("order", 0))
        maxc = max(maxc, len(row))
        for ci, n in enumerate(row):
            pos[n["id"]] = (180 + ci * 200, 70 + li * 105, n.get("w", 150), n.get("h", 58))
    c = spec.get("canvas") or {}
    W = c.get("w") or max(560, 130 + maxc * 200 + 60)
    H = c.get("h") or 30 + len(lanes) * 105 + 115
    return pos, int(W), int(H)

def border_pt(x, y, w, h, dx, dy):
    if abs(dx) * h >= abs(dy) * w:
        return (x + (w / 2 if dx >= 0 else -w / 2), y)
    return (x, y + (h / 2 if dy >= 0 else -h / 2))

def used_styles(edges):
    u = []
    for e in edges:
        s = e.get("style", "sequence")
        if s not in u:
            u.append(s)
    return u

def render_svg(spec):
    pos, W, H = layout(spec)
    lanes = spec.get("lanes") or []
    edges = spec.get("edges") or []
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="%s">' % (W, H, W, H, FONT)]
    out.append("<defs>")
    for st, s in STYLES.items():
        out.append('<marker id="ar-%s" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="%s"/></marker>' % (st, s["stroke"]))
    out.append("</defs>")
    out.append('<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    if spec.get("kind") == "route":
        out.append('<g id="layer-lanes">')
        for li, l in enumerate(lanes):
            y0 = 20 + li * 105
            out.append('<rect id="lane-%s" x="8" y="%d" width="%d" height="100" fill="%s" stroke="#b0bec5"/><text x="16" y="%d" font-size="12" fill="#455a64">%s</text>' % (esc(l["id"]), y0, W - 16, "#f5f7fa" if li % 2 == 0 else "#eceff1", y0 + 55, esc(l.get("label", l["id"]))))
        out.append("</g>")
    out.append('<g id="layer-edges">')
    mids, seq_i = [], 0
    for i, e in enumerate(edges):
        st = e.get("style", "sequence")
        a, b = pos[e["from"]], pos[e["to"]]
        dx, dy = b[0] - a[0], b[1] - a[1]
        p1 = border_pt(a[0], a[1], a[2], a[3], dx, dy)
        p2 = border_pt(b[0], b[1], b[2], b[3], -dx, -dy)
        s = STYLES[st]
        if abs(p1[0] - p2[0]) > 1 and abs(p1[1] - p2[1]) > 1:
            if abs(dx) * a[3] >= abs(dy) * a[2]:
                d = "M%g,%g L%g,%g L%g,%g L%g,%g" % (p1[0], p1[1], p2[0], p1[1], p2[0], p2[1], p2[0], p2[1])
            else:
                my = (p1[1] + p2[1]) / 2
                d = "M%g,%g L%g,%g L%g,%g L%g,%g" % (p1[0], p1[1], p1[0], my, p2[0], my, p2[0], p2[1])
        else:
            d = "M%g,%g L%g,%g" % (p1[0], p1[1], p2[0], p2[1])
        dash = ' stroke-dasharray="%s"' % s["dash"] if s["dash"] else ""
        out.append('<path id="edge-%d" data-style="%s" data-from="%s" data-to="%s" data-source="%s" data-quote="%s" d="%s" fill="none" stroke="%s" stroke-width="1.6"%s marker-end="url(#ar-%s)"/>' % (i, st, esc(e.get("from")), esc(e.get("to")), esc(src_locator(e.get("source"))), esc(src_quote(e.get("source"))), d, s["stroke"], dash, st))
        mids.append((i, (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, st, s))
        if st == "sequence":
            seq_i += 1
    out.append("</g>")
    out.append('<g id="layer-entities">')
    for n in spec["nodes"]:
        x, y, w, h = pos[n["id"]]
        fill = NODE_FILL.get(n.get("type", "default"), NODE_FILL["default"])
        out.append('<g id="node-%s" data-source="%s" data-quote="%s">' % (esc(n["id"]), esc(src_locator(n.get("source"))), esc(src_quote(n.get("source")))))
        if n.get("type") == "milestone":
            pts = "%g,%g %g,%g %g,%g %g,%g" % (x, y - h / 2 - 6, x + w / 2, y, x, y + h / 2 + 6, x - w / 2, y)
            out.append('<polygon points="%s" fill="%s" stroke="#546e7a" stroke-width="1.4"/>' % (pts, fill))
        else:
            out.append('<rect x="%g" y="%g" width="%g" height="%g" rx="6" fill="%s" stroke="#546e7a" stroke-width="1.4"/>' % (x - w / 2, y - h / 2, w, h, fill))
        lines = str(n.get("label", n["id"])).split("\n")
        for li, t in enumerate(lines):
            out.append('<text x="%g" y="%g" text-anchor="middle" font-size="12">%s</text>' % (x, y - 4 * (len(lines) - 1) + li * 14 + 4, esc(t)))
        if n.get("note"):
            out.append('<text x="%g" y="%g" text-anchor="middle" font-size="9" fill="#78909c">%s</text>' % (x, y + h / 2 + 12, esc(n["note"])))
        out.append("</g>")
    out.append("</g>")
    out.append('<g id="layer-labels">')
    seq_i = 0
    for i, mx, my, st, s in mids:
        if st == "sequence":
            seq_i += 1
            out.append('<g id="edge-%d-num"><circle cx="%g" cy="%g" r="10" fill="#ffffff" stroke="%s"/><text x="%g" y="%g" text-anchor="middle" font-size="11" fill="%s">%d</text></g>' % (i, mx, my, s["stroke"], mx, my + 4, s["stroke"], seq_i))
        e = edges[i]
        if e.get("label"):
            out.append('<text x="%g" y="%g" text-anchor="middle" font-size="10" fill="%s">%s</text>' % (mx, my - 13, s["stroke"], esc(e["label"])))
    cap = spec.get("caption_steps")
    if isinstance(cap, list) and cap:
        cy = H - 16 - 14 * len(cap)
        for j, c in enumerate(cap):
            out.append('<text x="220" y="%d" font-size="10" fill="#607d8b">%s</text>' % (cy + 14 * j, esc(str(c))))
    out.append("</g>")
    used = used_styles(edges)
    out.append('<g id="layer-legend">')
    ly = H - 14 - 20 * (len(used) + len(spec.get("legend") or []))
    out.append('<text x="20" y="%d" font-size="11" font-weight="bold" fill="#455a64">图例</text>' % ly)
    for j, s in enumerate(used):
        st = STYLES[s]
        dash = ' stroke-dasharray="%s"' % st["dash"] if st["dash"] else ""
        yy = ly + 14 + 20 * j
        out.append('<line x1="20" y1="%d" x2="56" y2="%d" stroke="%s" stroke-width="1.6"%s marker-end="url(#ar-%s)"/><text x="64" y="%d" font-size="11">%s</text>' % (yy, yy, st["stroke"], dash, s, yy + 4, esc(st.get("label", s))))
    for k, g in enumerate(spec.get("legend") or []):
        yy = ly + 14 + 20 * (len(used) + k)
        out.append('<text x="20" y="%d" font-size="11">%s</text>' % (yy + 4, esc(g.get("label", ""))))
    out.append("</g>")
    if spec.get("title"):
        out.append('<g id="layer-title"><text x="%d" y="16" text-anchor="middle" font-size="16" font-weight="bold">%s</text></g>' % (W // 2, esc(spec["title"])))
    out.append("</svg>")
    return "".join(out)

def source_trace(spec, sources):
    if not sources:
        return None
    low = ""
    for p in sources:
        try:
            low += "\n" + norm(open(p, encoding="utf-8", errors="replace").read())
        except OSError as e:
            print("WARN %s: %s" % (p, e), file=sys.stderr)
    mn, mv = [], []
    for n in spec.get("nodes") or []:
        t = toks(n.get("label", "")) + toks(n.get("note", ""))
        if t and not any(norm(x) in low for x in t):
            mn.append(n.get("id"))
        mv += [n.get("id") + ":" + x for f in (n.get("label", ""), n.get("note", "")) for x in NUM_UNIT.findall(str(f)) if norm(x) not in low]
    mv += ["e:" + x for e in spec.get("edges") or [] for x in NUM_UNIT.findall(str(e.get("label", ""))) if norm(x) not in low]
    return {"sources": [os.path.basename(p) for p in sources], "no_token": mn, "num_missing": mv}

def connections_table(spec):
    return [{"id": "edge-%d" % i, "from": e.get("from"), "to": e.get("to"), "style": (s := e.get("style", "sequence")),
             "stroke": STYLES.get(s, {}).get("stroke"), "dash": STYLES.get(s, {}).get("dash", ""),
             "label": e.get("label", ""), "source": src_locator(e.get("source")), "quote": src_quote(e.get("source"))}
            for i, e in enumerate(spec.get("edges") or [])]

def layout_issues(spec):
    """布局问题: apparatus 画布溢出节点(与 check_spec 同源判据)。"""
    ov = []
    if spec.get("kind") == "apparatus":
        c = spec.get("canvas") or {}
        cw, ch = c.get("w", 1200), c.get("h", 800)
        for n in spec.get("nodes") or []:
            x, y = n.get("x"), n.get("y")
            if x is None or y is None:
                continue
            w, h = n.get("w", 150), n.get("h", 56)
            if min(x - w / 2, y - h / 2) < 0 or x + w / 2 > cw or y + h / 2 > ch:
                ov.append(n["id"])
    return ov

def verify_figure(spec, svg_path, sources=None):
    svg = open(svg_path, encoding="utf-8").read()
    edges = spec.get("edges") or []
    pos, _, _ = layout(spec)
    c = {i: (p[0], p[1]) for i, p in pos.items()}
    bs, bd, bn, bl, nf = [], [], [], [], {}
    for m in EDGE_RE.finditer(svg):
        i = int(m.group(1))
        st, d, sk = m.group(2), m.group(3), m.group(4)
        dm = re.search(r'stroke-dasharray="([^"]*)"', m.group(5))
        dash, mk = dm.group(1) if dm else "", m.group(6)
        r = STYLES.get(st)
        if not r or sk != r.get("stroke") or dash != (r.get("dash") or "") or mk != st:
            bs.append("e%d %s glyph" % (i, st))
        e = edges[i] if i < len(edges) else None
        if e:
            if e.get("style") != st: bs.append("e%d style!=spec" % i)
            ep = last_pt(d)
            f, t = c.get(e.get("from")), c.get(e.get("to"))
            if f and t and ep and d2(ep, f) < d2(ep, t): bd.append("e%d reversed" % i)
    for m in NUM_RE.finditer(svg):
        nf[int(m.group(1))] = int(m.group(2))
    seq = [i for i, e in enumerate(edges) if e.get("style") == "sequence"]
    n = len(seq)
    if sorted(nf) != seq or [nf[i] for i in seq] != list(range(1, n + 1)):
        bn.append("num!=1..%d" % n)
    cap = spec.get("caption_steps") or spec.get("caption")
    if isinstance(cap, list) and len(cap) != n:
        bn.append("caption!=%d" % n)
    used = used_styles(edges)
    lb = LEGEND_RE.search(svg)
    lb = lb.group(1) if lb else ""
    for s in used:
        if "url(#ar-%s)" % s not in lb:
            bl.append("legend:%s" % s)
    ids = {nd.get("id") for nd in spec.get("nodes") or []}
    ends = {e.get("from") for e in edges} | {e.get("to") for e in edges}
    clo = {"dangling": sorted(ends - ids), "orphans": sorted(ids - ends)}
    tr = source_trace(spec, sources)
    raw = read_materials(sources)
    lines, sents = material_spans(raw)
    q = quote_audit(spec, raw, lines, sents)
    ent = entity_audit(spec, raw) if raw.strip() else {"mismatch": [], "note": "no materials"}
    req = required_audit(spec)
    dr = direction_audit(spec, raw, lines, sents)
    wo = None
    if "workorder" in spec:
        from workorder_guard import audit_workorder
        wo = audit_workorder(spec, sources or [], require=True)
    wo_bad = ["workorder:%s:%s" % (x.get("code"), x.get("path"))
              for x in (wo or {}).get("errors", [])]
    bd_all = bd + ["%s source-reversed" % t for t in dr["contradicted"]]
    ov = layout_issues(spec)
    layers_found = sorted(set(LAYER_RE.findall(svg)))
    need_layers = {"layer-edges", "layer-entities", "layer-labels", "layer-legend"}
    layers_missing = sorted(need_layers - set(layers_found))
    font_ok = "sans-serif" in (re.search(r'font-family="([^"]*)"', svg) or ["", ""])[1]
    export = {"svg_wellformed": True, "layers": layers_found, "layers_missing": layers_missing,
              "font_family": FONT, "font_stack_ok": font_ok}
    fails = (bs + bd_all + bn + bl + clo["dangling"] + q["missing"] + q["misplaced"] + req["missing"]
             + wo_bad + ((tr["no_token"] + tr["num_missing"]) if tr else []))
    rep = {"figure": os.path.basename(svg_path), "criteria": "assets/connection_rules.json",
           "workorder": wo,
           "semantic": {"edges": len(EDGE_RE.findall(svg)), "bad": bs},
           "direction": {"bad": bd_all, "unknown": dr["unknown"], "unsourced": dr["unsourced"],
                         "by_edge": {str(k): v for k, v in dr["by_edge"].items()}, "rows": dr["rows"]},
           "numbering": {"sequence_edges": n, "bad": bn}, "legend": {"used": used, "bad": bl},
           "closure": clo, "layout": {"dangling": clo["dangling"], "orphans": clo["orphans"],
                                       "overflow": ov},
           "export": export, "trace": tr, "quote": q, "entity": ent, "required": req}
    rep["checks"] = [
        {"name": "entity", "label": "实体逐字", "level": "advisory",
         "result": "warn" if ent.get("mismatch") else "pass", "detail": ent.get("mismatch")},
        {"name": "semantic", "label": "连接语义", "level": "advisory",
         "result": "warn" if bs else "pass", "detail": bs},
        {"name": "direction", "label": "方向", "level": "advisory",
         "result": "fail" if bd_all else ("warn" if (dr["unknown"] or dr["unsourced"]) else "pass"),
         "detail": {"bad": bd_all, "unknown": dr["unknown"], "unsourced": dr["unsourced"]}},
        {"name": "legend", "label": "图例", "level": "advisory",
         "result": "warn" if bl else "pass", "detail": bl},
        {"name": "layout", "label": "布局", "level": "mixed",
         "result": "fail" if clo["dangling"] else ("warn" if (clo["orphans"] or ov) else "pass"),
         "detail": {"dangling": clo["dangling"], "orphans": clo["orphans"], "overflow": ov}},
        {"name": "export", "label": "导出", "level": "mixed",
         "result": "fail" if not export["svg_wellformed"] else ("warn" if (layers_missing or not font_ok) else "pass"),
         "detail": export}]
    sc, ded = figure_score(rep)
    rep["score"] = {"value": sc, "max": 100, "deductions": ded,
                    "hint": "先修 fail 再修 warn; score>=90 或剩余 warn 均可解释即停"}
    rep["fails"] = len(fails)
    rep["verdict"] = "issues" if fails else "pass"
    return rep

def write_map(path, rep):
    q = rep.get("quote") or {}
    lines = ["# figure_map — 组件/连线 → 材料来源映射", "",
             "figure: `%s` | verdict: **%s** | score: **%s/100**" % (
                 rep.get("figure"), rep.get("verdict"), (rep.get("score") or {}).get("value")), "",
             "| 元素 | 类别 | 定位 locator | 材料 quote | 命中状态 |", "|---|---|---|---|---|"]
    for r in q.get("rows") or []:
        lines.append("| %s | %s | %s | %s | %s |" % (r["element"], r["kind"], r["locator"] or "—",
                                                        (r["quote"] or "—").replace("|", "\\|"), r["status"]))
    dr = rep.get("direction") or {}
    lines += ["", "## 箭头方向依据（from→to 段落支撑）", "",
              "| 边 | locator | 方向依据状态 |", "|---|---|---|"]
    for r in dr.get("rows") or []:
        lines.append("| %s | %s | %s |" % (r["element"], r.get("locator") or "—", r.get("status")))
    req = rep.get("required") or {}
    lines += ["", "## required 覆盖审计", "",
              "required 覆盖率: %d/%d；缺失: %s" % (req.get("covered", 0), len(req.get("required") or []),
                                                    "、".join(req.get("missing") or []) or "无"), ""]
    if rep.get("workorder"):
        wo = rep["workorder"]
        lines += ["## 参数 / 接口 / 工艺歧义工单", "",
                  "状态: **%s**；completion_ceiling: **%s**" % (wo.get("status"), wo.get("completion_ceiling")), "",
                  "| 级别 | code | 路径 | 处置/问题 |", "|---|---|---|---|"]
        for level, key in (("error", "errors"), ("limitation", "limitations"), ("warning", "warnings")):
            for item in wo.get(key) or []:
                lines.append("| %s | %s | %s | %s |" % (level, item.get("code"), item.get("path"),
                                                       str(item.get("message", "")).replace("|", "\\|")))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

def make_preview(svg, png):
    chain = [("rsvg-convert", ["rsvg-convert", "-o", png, svg]), ("inkscape", ["inkscape", svg, "-o", png])]
    exe = shutil.which("magick") or shutil.which("convert")
    if exe:
        chain.append(("imagemagick", [exe, svg, png]))
    for name, cmd in chain:
        if not shutil.which(cmd[0]):
            continue
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=120)
            if r.returncode == 0 and os.path.isfile(png) and os.path.getsize(png) > 0:
                return {"status": "ok", "renderer": name, "png": png}
        except Exception:
            pass
    try:
        import fitz
        fitz.open(svg)[0].get_pixmap(matrix=fitz.Matrix(2, 2)).save(png)
        return {"status": "ok", "renderer": "pymupdf", "png": png}
    except Exception:
        pass
    note = png + ".preview_unavailable.txt"
    with open(note, "w", encoding="utf-8") as f:
        f.write("preview_unavailable: 全部渲染器失败; SVG 仍可用浏览器打开。\n")
    return {"status": "preview_unavailable", "renderer": None, "png": None, "note": note}

def jprint(x, indent=1):
    print(json.dumps(x, ensure_ascii=False, indent=indent))

def cmd_check(a):
    rep = check_spec(load_json(a.spec))
    jprint(rep)
    sys.exit(0 if rep["ok"] else 1)

def cmd_render(a):
    spec = load_json(a.spec)
    rep = check_spec(spec)
    if not rep["ok"]:
        print(json.dumps(rep, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    svg = render_svg(spec)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(svg)
    jprint({"svg": a.out, "bytes": len(svg.encode("utf-8")), "warnings": rep["warnings"]}, 0)

def cmd_verify(a):
    spec = load_json(a.spec)
    stem = a.svg.rsplit(".", 1)[0] if a.svg else "figure"
    out = stem + ".verify.json"
    rep = None
    if not (a.svg and os.path.isfile(a.svg)):
        rep = {"figure": os.path.basename(a.svg or ""), "verdict": "invalid", "hard": "svg missing",
               "criteria": "assets/connection_rules.json",
               "score": {"value": 0, "max": 100, "deductions": {"hard": 100}}}
    else:
        try:
            xml_parse(a.svg)
        except Exception as e:
            rep = {"figure": os.path.basename(a.svg), "verdict": "invalid", "hard": "svg not well-formed: %s" % e,
                   "criteria": "assets/connection_rules.json",
                   "score": {"value": 0, "max": 100, "deductions": {"hard": 100}}}
    if rep is None:
        rep = verify_figure(spec, a.svg, a.sources)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    map_path = stem + "_map.md"
    if rep.get("verdict") != "invalid":
        write_map(map_path, rep)
    bad = sum(len(rep.get(k, {}).get("bad", [])) for k in ("semantic", "direction", "numbering", "legend"))
    jprint({"verdict": rep["verdict"], "report": out, "map": map_path if rep.get("verdict") != "invalid" else None,
            "bad": bad, "score": (rep.get("score") or {}).get("value"), "advisory": rep["verdict"] != "invalid"})
    sys.exit(0 if rep["verdict"] != "invalid" else 1)

def cmd_preview(a):
    jprint(make_preview(a.svg, a.png or a.svg.rsplit(".", 1)[0] + ".png"), 0)

def fingerprint(path):
    """Actual file identity for independent replay; missing files remain explicit nulls."""
    if not path or not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return {"path": os.path.abspath(path), "bytes": os.path.getsize(path), "sha256": h.hexdigest()}


def manifest(paths):
    return [x for x in (fingerprint(p) for p in paths if p) if x is not None]


def contract_value(key, ctx):
    n = re.sub(r"[^a-z0-9]+", "", str(key).lower())
    def has(*words):
        return any(w in n for w in words)
    if has("caseid") or n == "case": return ctx["case_id"]
    if has("status"): return ctx["status"]
    if has("editable", "svg"): return ctx["editable"]
    if has("map", "trace", "locat", "provenance", "evidence"): return ctx["mapping"]
    if has("png", "preview", "image", "thumbnail"): return ctx["preview"]
    if has("pdf", "export", "vector"): return ctx["exports"]
    if has("report", "check", "validation", "audit"): return ctx["report"]
    if has("uncertain"): return ctx["uncertainty"]
    if has("change", "log"): return ctx["changes"]
    if has("source"): return ctx["sources"]
    if has("deliverable", "output"): return ctx["outputs"]
    return None


def cmd_result(a):
    spec = load_json(a.spec) if a.spec else {}
    case = load_json(a.case) if a.case else {}
    rep = check_spec(spec) if spec else {"ok": False, "errors": ["no spec"]}
    p = a.preview if a.preview and os.path.isfile(a.preview) else None
    svg_ok, n = False, None
    if a.svg and os.path.isfile(a.svg):
        n = os.path.getsize(a.svg)
        try:
            xml_parse(a.svg); svg_ok = True
        except Exception:
            pass
    v = {}
    if a.verify and os.path.isfile(a.verify):
        try:
            v = json.load(open(a.verify, encoding="utf-8"))
        except Exception:
            v = {"error": "verify unreadable"}
    wo = v.get("workorder")
    if not wo and a.workorder_audit and os.path.isfile(a.workorder_audit):
        try:
            wo = json.load(open(a.workorder_audit, encoding="utf-8"))
        except Exception:
            wo = {"ok": False, "completion_ceiling": "partial", "errors": [{"code": "audit_unreadable"}]}
    req = (v.get("required") if isinstance(v.get("required"), dict) else None) or required_audit(spec)
    map_path = None
    if a.svg:
        cand = a.svg.rsplit(".", 1)[0] + "_map.md"
        map_path = cand if os.path.isfile(cand) else None
    ex = []
    if a.svg:
        ex.append({"path": a.svg, "format": "svg", "vector": True})
    if p:
        ex.append({"path": p, "format": "png", "renderer": a.renderer})
    nodes = spec.get("nodes") or []
    q = v.get("quote") or {}
    uncertainty = list(spec.get("uncertainty") or [])
    status = a.status
    if req["missing"] and status in ("success", "complete", "answered"):
        status = "partial"
        uncertainty.append("required 未覆盖: %s → status 强制 partial(禁止 success/complete)" % "、".join(req["missing"]))
    if wo:
        if wo.get("completion_ceiling") == "partial" and status in ("success", "complete", "answered"):
            status = "partial"
            uncertainty.append("workorder 参数/接口/工艺歧义未完全闭合 → status 强制 partial")
        for item in (wo.get("errors") or []) + (wo.get("limitations") or []):
            uncertainty.append("workorder %s %s: %s" % (item.get("code"), item.get("path"), item.get("message")))
    if v.get("verdict") in ("issues", "invalid") and status in ("success", "complete", "answered"):
        status = "partial"
        uncertainty.append("figure verify 未通过 → status 强制 partial")
    by_edge = (v.get("direction") or {}).get("by_edge") or {}
    dir_unknown = [t for t, st in by_edge.items() if st == "unknown"]
    dir_unsourced = [t for t, st in by_edge.items() if st == "unsourced"]
    dir_contradicted = [t for t, st in by_edge.items() if st == "contradicted"]
    if dir_unknown or dir_unsourced:
        uncertainty.append("箭头方向依据缺失→降级 unknown(不臆造): %s" % "、".join(sorted(dir_unknown + dir_unsourced)))
    if dir_contradicted:
        uncertainty.append("箭头方向与来源段落矛盾(fail, 需修 spec): %s" % "、".join(sorted(dir_contradicted)))
    conns = connections_table(spec) if spec else []
    for ci, c in enumerate(conns):
        c["direction"] = by_edge.get(str(ci), "unverified")
    sources = {"entities_total": len(nodes), "entities_sourced": sum(1 for x in nodes if x.get("source")),
               "quote_rows": len(q.get("rows") or []), "quote_missing": len(q.get("missing") or []),
               "quote_misplaced": len(q.get("misplaced") or []), "quote_legacy": len(q.get("legacy") or []),
               "entity_mismatch": len((v.get("entity") or {}).get("mismatch") or []),
               "direction_supported": len(by_edge) - len(dir_unknown + dir_unsourced + dir_contradicted),
               "direction_unknown": dir_unknown, "direction_unsourced": dir_unsourced,
               "direction_contradicted": dir_contradicted,
               "required_total": len(req["required"]), "required_covered": req["covered"],
               "required_missing": req["missing"],
               "workorder": {"status": (wo or {}).get("status", "not_declared"),
                             "counts": (wo or {}).get("counts", {})},
               "input_manifest": manifest((a.sources or []) + ([a.case] if a.case else [])),
               "details": [{"id": x.get("id"), "label": x.get("label"),
                            "locator": src_locator(x.get("source")), "quote": src_quote(x.get("source"))} for x in nodes]}
    result = {"case_id": a.case_id, "status": status, "task": "apparatus_and_technical_route",
              "result_schema_version": "scifig-result/2.0",
              "figure_version": str(spec.get("figure_version") or "1.0"),
              "spec_schema_version": str(spec.get("schema_version") or "scifig-spec/1.0"),
              "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "summary": a.summary or "", "figure_kind": spec.get("kind"),
              "outputs": {"editable_source": {"path": a.svg, "format": "svg", "layers": LAYERS, "bytes": n},
                          "preview": {"path": p, "renderer": a.renderer, "status": "ok" if p else "preview_unavailable"},
                          "mapping": {"path": map_path, "format": "markdown"},
                          "report": {"path": a.verify, "format": "json", "score": (v.get("score") or {}).get("value")},
                          "exports": ex},
              "sources": sources,
              "data_mapping": spec.get("mapping") or [], "connections": conns,
              "changes": {"decisions": spec.get("changes") or spec.get("change_records") or [],
                          "human_review": spec.get("human_review") or []},
              "change_records": spec.get("changes") or [], "uncertainty": uncertainty,
              "checks": {"spec_check": rep, "figure_check": v, "workorder_audit": wo,
                          "export_check": {"svg_wellformed": svg_ok, "svg_bytes": n,
                                           "font_family": FONT + "(未嵌)", "color_mode": "RGB"}},
              "generator": "scifig.py (Python 标准库)",
              "tool_versions": {"scifig.py": "6.0.0", "workorder_guard.py": "1.0.0",
                                "python": platform.python_version()},
              "source_manifest": manifest((a.sources or []) + ([a.spec] if a.spec else []) + ([a.case] if a.case else [])),
              "artifact_manifest": manifest([a.svg, p, a.verify, map_path, a.workorder_audit]),
              "review": {"scientific_judgement": "native_or_human_review_required",
                         "machine_check_scope": "source-anchor/interface/order/geometry/export consistency; not proof of scientific validity"},
              "reproduction": {"commands": [
                  "python3 scripts/workorder_guard.py audit %s %s --require --out workorder.audit.json" % (
                      shlex.quote(a.spec or "spec.json"), " ".join(shlex.quote(x) for x in (a.sources or []))),
                  "python3 scripts/scifig.py render %s figure.svg" % shlex.quote(a.spec or "spec.json"),
                  "python3 scripts/scifig.py verify %s figure.svg %s" % (
                      shlex.quote(a.spec or "spec.json"), " ".join(shlex.quote(x) for x in (a.sources or [])))
              ], "working_directory": "/app/work", "output_directory": "/app/output"}}
    oc = case.get("output_contract") or {}
    contract_keys = list(oc) if isinstance(oc, dict) else [str(k) for k in oc]
    result["output_contract"] = oc if isinstance(oc, dict) else {str(k): None for k in oc}
    result["output_contract_null_fields"] = []
    ctx = {"case_id": a.case_id, "status": status, "editable": result["outputs"]["editable_source"],
           "mapping": result["outputs"]["mapping"], "preview": result["outputs"]["preview"],
           "exports": result["outputs"]["exports"], "report": result["outputs"]["report"],
           "uncertainty": uncertainty, "changes": result["changes"], "sources": sources,
           "outputs": result["outputs"]}
    for key in contract_keys:
        if key in result and result[key] is not None:
            continue
        value = contract_value(key, ctx)
        result[key] = value
        if value is None:
            result["output_contract_null_fields"].append(key)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    jprint({"result": a.out, "status": status, "spec_ok": rep["ok"], "verify": v.get("verdict"),
            "score": (v.get("score") or {}).get("value"), "preview": "ok" if p else "preview_unavailable"}, 0)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check"); p.add_argument("spec"); p.set_defaults(f=cmd_check)
    p = sub.add_parser("render"); p.add_argument("spec"); p.add_argument("out"); p.set_defaults(f=cmd_render)
    p = sub.add_parser("verify"); p.add_argument("spec"); p.add_argument("svg"); p.add_argument("sources", nargs="*"); p.set_defaults(f=cmd_verify)
    p = sub.add_parser("preview"); p.add_argument("svg"); p.add_argument("png", nargs="?"); p.set_defaults(f=cmd_preview)
    p = sub.add_parser("result")
    for f in ("--case-id", "--spec", "--svg", "--preview", "--renderer", "--verify", "--summary", "--out"):
        p.add_argument(f, required=(f in ("--case-id", "--out")))
    p.add_argument("--case", help="原始 case.json；用于保留并逐键填 output_contract")
    p.add_argument("--source", dest="sources", action="append", default=[], help="实际材料路径，可重复")
    p.add_argument("--workorder-audit", help="workorder_guard.py 生成的审计 JSON")
    p.add_argument("--status", default="partial", choices=["success", "partial", "failed"])
    p.set_defaults(f=cmd_result)
    a = ap.parse_args(); a.f(a)

if __name__ == "__main__":
    main()
