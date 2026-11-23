#!/usr/bin/env python3
"""build_map.py v2 — 带标注的 Markdown 大纲 → 思维导图交付物（仅 Python 标准库）。

输入：首行 "# 中心主题"，其后缩进 "- " 列表为层级。节点标注（剥离出显示文本）：
  {来源: 材料 §2.1 第3段}  {关系: 因果|对比|依赖|时间|引用|支持|冲突|概括}
  {存疑: 原因}  {关联: <另一节点的显示文本>}  ← 跨分支关系（FreeMind arrowlink）

输出（--outdir 下，--name 前缀）：<name>.mm（来源/关系/存疑进 <richcontent TYPE="NOTE">，
关联进 <arrowlink>，节点带 ID）、<name>.opml（_source/_relation/_uncertain/_link/_note 属性）、
<name>.svg（自绘横向树 + CJK 字体栈 + 跨分支虚线弧）、<name>_mapping.md、<name>_report.json
（规则化 diagnostics + 0-100 可读性分数）。

用法: python3 build_map.py outline.md --outdir /app/output --name mindmap
退出码: 0=成功(可能有 warnings); 2=大纲解析失败。
"""
import argparse, json, os, re, sys
from xml.sax.saxutils import escape

ANN = re.compile(r"\{([^{}:：]+)[:：]([^}]*)\}")
BULLET = re.compile(r"^(\s*)[-*+]\s+(.*\S)\s*$")
ANN_KEYS = {"来源": "source", "src": "source", "source": "source",
            "关系": "relation", "rel": "relation", "relation": "relation",
            "存疑": "uncertain", "uncertain": "uncertain", "疑": "uncertain",
            "关联": "link", "link": "link"}
REL_OK = {"因果", "对比", "依赖", "时间", "引用", "支持", "冲突", "概括"}
REL_COLOR = {"因果": "#B279A2", "对比": "#E45756", "依赖": "#9D755D",
             "时间": "#72B7B2", "引用": "#54A24B", "支持": "#4C78A8",
             "冲突": "#E45756", "概括": "#999999"}
MAX_LABEL_UNITS = 24   # 叶节点建议显示宽度上限（1 汉字=2 单位）
MAX_BRANCHES = 7       # 根节点建议分支上限
MAX_DEPTH = 5          # 建议最大深度
MAX_NODES = 60         # 建议最大节点数（超过可读性下降）
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#B279A2",
           "#9D755D", "#72B7B2", "#EECA3B"]
FONT_STACK = ("'Noto Sans CJK SC','WenQuanYi Micro Hei','PingFang SC',"
              "'Microsoft YaHei','Source Han Sans SC',sans-serif")


def units(s):
    """显示宽度单位：CJK 全角按 2，其余按 1。"""
    return sum(2 if ord(c) > 0x2E7F else 1 for c in s)


def wrap(s, width=22):
    lines, cur = [], ""
    for ch in s:
        if units(cur + ch) > width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines or [""]


def diag(rule, status, node, detail, deduct):
    return {"rule": rule, "status": status, "node": node,
            "detail": detail, "deduct": deduct}


def fmt_diag(d):
    return "%s[%s] %s%s" % (d["rule"], d["status"],
                            ("%s: " % d["node"]) if d["node"] else "", d["detail"])


class Node:
    def __init__(self, text, depth):
        self.text, self.depth = text, depth
        self.source = self.relation = self.uncertain = self.link = ""
        self.link_id = self.id = ""
        self.children = []
        self.branch = -1  # 所属一级分支序号（根为 -1）
        self.x = self.y = self.w = self.h = 0.0


def parse_outline(md_text):
    root, stack = None, []  # stack: list[(indent, Node)]
    for ln, raw in enumerate(md_text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#") and root is None:
            root = Node(line.lstrip("#").strip(), 0)
            continue
        m = BULLET.match(line)
        if not m:
            continue
        if root is None:
            raise ValueError("第 %d 行：缺少首行 '# 中心主题'" % ln)
        indent, body = len(m.group(1)), m.group(2)
        node = Node(ANN.sub("", body).strip(), 0)
        for k, v in ANN.findall(body):
            attr = ANN_KEYS.get(k.strip())
            if attr:
                setattr(node, attr, v.strip())
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack:
            parent = stack[-1][1]
            node.depth = parent.depth + 1
            parent.children.append(node)
        else:
            node.depth = 1
            root.children.append(node)
        stack.append((indent, node))
    if root is None:
        raise ValueError("大纲为空：需要首行 '# 中心主题' 与缩进列表")
    return root


def all_nodes(root):
    out = [root]
    for c in root.children:
        out += all_nodes(c)
    return out


def assign_ids(root):
    n = 0
    for node in all_nodes(root):
        node.id = "ID_%d" % n
        n += 1


def resolve_links(root):
    by_text = {}
    for node in all_nodes(root):
        by_text.setdefault(node.text, []).append(node)
    w = []
    for n in all_nodes(root):
        if not n.link:
            continue
        tgt = by_text.get(n.link)
        if not tgt:
            w.append("关联目标未找到(按 {关联:<另一节点显示文本>} 精确匹配): %s -> %s"
                     % (n.text, n.link))
        elif tgt[0] is n:
            w.append("关联指向自身: %s" % n.text)
        else:
            n.link_id = tgt[0].id
    return w


def validate(root):
    checks = []
    for n in all_nodes(root):
        p = "/" + n.text
        if 1 <= n.depth <= 2 and not n.source and not n.uncertain:
            checks.append(diag("E1", "warn", p, "无来源标注(按概括/推断处理)", 2))
        if n.relation and n.relation not in REL_OK:
            checks.append(diag("E2", "warn", p,
                               "关系词不在建议集合 %s" % sorted(REL_OK), 1))
        if units(n.text) > MAX_LABEL_UNITS:
            checks.append(diag("E3", "warn", p,
                               "节点文字过长(>%d 单位，建议精简)" % MAX_LABEL_UNITS, 3))
        if n.depth > MAX_DEPTH:
            checks.append(diag("E4", "warn", p,
                               "层级过深(>%d，建议归并)" % MAX_DEPTH, 5))
    nb = len(root.children)
    if nb > MAX_BRANCHES:
        checks.append(diag("E5", "warn", "", "一级分支 %d 个(>%d，建议合并同类)"
                           % (nb, MAX_BRANCHES), 4))
    if nb == 0:
        checks.append(diag("E6", "fail", "", "根节点无任何分支", 15))
    total = len(all_nodes(root))
    if total > MAX_NODES:
        checks.append(diag("E7", "warn", "", "总节点数 %d(>%d，单图可读性下降)"
                           % (total, MAX_NODES), 4))
    sourced = sum(1 for n in all_nodes(root) if n.source)
    if sourced == 0:
        checks.append(diag("E8", "fail", "", "全图无任何 {来源:...} 标注", 15))
    cov = sourced / max(1, total - 1)
    if cov < 0.6:
        checks.append(diag("E9", "warn", "", "来源覆盖率 %.0f%%(<60%%)" % (cov * 100), 5))
    else:
        checks.append(diag("E9", "pass", "", "来源覆盖率 %.0f%%" % (cov * 100), 0))
    return checks


def measure(root):
    for i, b in enumerate(root.children):
        def tag(n, i=i):
            n.branch = i
            for c in n.children:
                tag(c)
        tag(b)
    for n in all_nodes(root):
        n.lines = wrap(n.text)
        n.w = max(units(l) for l in n.lines) * 7 + 18
        n.h = len(n.lines) * 17 + 10 + (13 if n.source else 0)


def layout(root):
    measure(root)
    depth_w = {}
    for n in all_nodes(root):
        depth_w[n.depth] = max(depth_w.get(n.depth, 0), n.w)
    xs, acc = {}, 24.0
    for d in range(max(depth_w) + 1):
        xs[d] = acc
        acc += depth_w[d] + 70
    y = [20.0]
    def place(n):
        n.x = xs[n.depth]
        if not n.children:
            n.y = y[0] + n.h / 2
            y[0] += n.h + 14
        else:
            for c in n.children:
                place(c)
            n.y = (n.children[0].y + n.children[-1].y) / 2
    place(root)
    W = acc - 70 + 24
    H = max(y[0] + 6, root.y * 2 + 20)
    return W, H


def overlap_check(root):
    nodes, ov = all_nodes(root), []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i], nodes[j]
            if (a.x < b.x + b.w - 2 and b.x < a.x + a.w - 2 and
                    a.y - a.h / 2 < b.y + b.h / 2 - 2 and
                    b.y - b.h / 2 < a.y + a.h / 2 - 2):
                ov.append("标签重叠: %s ↔ %s" % (a.text, b.text))
    return ov


def render_svg(root, title, W, H):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'font-family="%s">' % (W, H, FONT_STACK),
           '<rect width="%d" height="%d" fill="#ffffff"/>' % (W, H),
           '<text x="24" y="14" font-size="11" fill="#888">%s</text>' % escape(title)]
    id2node = {n.id: n for n in all_nodes(root)}
    edges, xlinks, boxes = [], [], []
    def draw(n):
        color = "#333333" if n.depth == 0 else PALETTE[n.branch % len(PALETTE)]
        fill = "#333333" if n.depth == 0 else (color if n.depth == 1 else "#ffffff")
        tcol = "#ffffff" if n.depth <= 1 else "#222222"
        dash = ' stroke-dasharray="5,3"' if n.uncertain else ""
        for c in n.children:
            x1, y1 = n.x + n.w, n.y
            x2, y2 = c.x, c.y
            mx = (x1 + x2) / 2
            edges.append('<path d="M%.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" '
                         'stroke="%s" stroke-width="1.6" fill="none"/>'
                         % (x1, y1, mx, y1, mx, y2, x2, y2,
                            PALETTE[c.branch % len(PALETTE)]))
            if c.relation:
                edges.append('<text x="%.1f" y="%.1f" font-size="10" fill="#777" '
                             'text-anchor="middle">%s</text>'
                             % (mx, (y1 + y2) / 2 - 3, escape(c.relation)))
        if n.link_id and n.link_id in id2node:
            t = id2node[n.link_id]
            x1, y1, x2, y2 = n.x + n.w, n.y, t.x, t.y
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            xlinks.append('<path d="M%.1f %.1f C %.1f %.1f %.1f %.1f %.1f %.1f" '
                          'stroke="#B22222" stroke-width="1.2" stroke-dasharray="4,4" '
                          'fill="none"/>' % (x1, y1, mx, y1, mx, y2, x2, y2))
            xlinks.append('<text x="%.1f" y="%.1f" font-size="9" fill="#B22222" '
                          'text-anchor="middle">关联</text>' % (mx, my - 4))
        boxes.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="7" '
                     'fill="%s" stroke="%s" stroke-width="1.4"%s/>'
                     % (n.x, n.y - n.h / 2, n.w, n.h, fill, color, dash))
        ty = n.y - n.h / 2 + 15
        for i, ln in enumerate(n.lines):
            boxes.append('<text x="%.1f" y="%.1f" font-size="12" fill="%s">%s</text>'
                         % (n.x + 9, ty + i * 17, tcol, escape(ln)))
        if n.source:
            boxes.append('<text x="%.1f" y="%.1f" font-size="9" fill="#999999">[%s]</text>'
                         % (n.x + 9, n.y + n.h / 2 - 4, escape(n.source)))
        if n.uncertain:
            boxes.append('<text x="%.1f" y="%.1f" font-size="10" fill="#D9534F">⚠存疑</text>'
                         % (n.x + n.w - 38, n.y - n.h / 2 + 12))
        for c in n.children:
            draw(c)
    draw(root)
    return ("".join(out) + "".join(edges) + "".join(xlinks) +
            "".join(boxes) + "</svg>")


def mm_note(n):
    parts = ((["来源:" + n.source] if n.source else []) +
             (["关系:" + n.relation] if n.relation else []) +
             (["存疑:" + n.uncertain] if n.uncertain else []) +
             (["关联:" + n.link] if n.link else []))
    if not parts:
        return ""
    return ('<richcontent TYPE="NOTE"><html><head></head><body><p>%s</p></body>'
            '</html></richcontent>' % escape(" | ".join(parts)))


def to_mm(n, root=False):
    attrs = ['TEXT="%s"' % escape(n.text, {'"': "&quot;"}), 'ID="%s"' % n.id]
    if root:
        attrs.append('POSITION="right"')
    s = "<node %s>" % " ".join(attrs) + mm_note(n)
    if n.link_id:
        s += ('<arrowlink DESTINATION="%s" COLOR="%s" STARTARROW="None" '
              'ENDARROW="Default"/>' % (n.link_id, REL_COLOR.get(n.relation, "#B22222")))
    s += "".join(to_mm(c) for c in n.children) + "</node>"
    return s


def opml_attr(name, val):
    return '%s="%s"' % (name, escape(val, {'"': "&quot;"})) if val else ""


def to_opml(n):
    meta = " ".join("%s:%s" % kv for kv in
                    (("来源", n.source), ("关系", n.relation),
                     ("存疑", n.uncertain), ("关联", n.link)) if kv[1])
    attrs = ['text="%s"' % escape(n.text, {'"': "&quot;"}),
             opml_attr("_source", n.source), opml_attr("_relation", n.relation),
             opml_attr("_uncertain", n.uncertain), opml_attr("_link", n.link_id),
             opml_attr("_note", meta)]
    s = "<outline %s>" % " ".join(a for a in attrs if a)
    s += "".join(to_opml(c) for c in n.children) + "</outline>"
    return s


def mapping_md(root):
    rows = ["| 节点路径 | 深度 | 类型 | 来源 | 关系 | 关联 | 存疑 |",
            "|---|---|---|---|---|---|---|"]
    cnt = {"n": 0, "sourced": 0}
    def walk(n, path):
        cnt["n"] += 1
        cnt["sourced"] += bool(n.source)
        p = (path + " / " + n.text).strip(" / ")
        typ = "中心主题" if n.depth == 0 else ("分支" if n.children else "叶节点")
        rows.append("| %s | %d | %s | %s | %s | %s | %s |" %
                    (p, n.depth, typ, n.source or "—（概括/推断，无直接来源）",
                     n.relation or "—", (n.link + ("→%s" % n.link_id if n.link_id else "")) or "—",
                     n.uncertain or "—"))
        for c in n.children:
            walk(c, p)
    walk(root, "")
    return "# 节点-来源映射\n\n" + "\n".join(rows) + "\n", cnt


def compute_score(checks, overlap_w, link_w):
    d = sum(c["deduct"] for c in checks) + 4 * len(overlap_w) + 5 * len(link_w)
    return max(0, 100 - d)


def max_depth(n):
    return max([n.depth] + [max_depth(c) for c in n.children])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outline")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--name", default="mindmap")
    ap.add_argument("--title", default="")
    a = ap.parse_args()
    try:
        md = open(a.outline, encoding="utf-8").read()
    except OSError as e:
        print("ERROR: 无法读取大纲: %s" % e, file=sys.stderr)
        return 2
    try:
        root = parse_outline(md)
    except ValueError as e:
        print("ERROR: 大纲解析失败: %s" % e, file=sys.stderr)
        return 2
    assign_ids(root)
    link_w = resolve_links(root)
    checks = validate(root)
    W, H = layout(root)
    ov = overlap_check(root)
    warnings = [fmt_diag(c) for c in checks if c["status"] != "pass"] + link_w + ov
    score = compute_score(checks, ov, link_w)
    os.makedirs(a.outdir, exist_ok=True)
    mm = '<map version="1.0.1">' + to_mm(root, root=True) + "</map>"
    opml = ('<?xml version="1.0" encoding="UTF-8"?><opml version="2.0">'
            '<head><title>%s</title></head><body>%s</body></opml>'
            % (escape(a.title or root.text), to_opml(root)))
    svg = render_svg(root, a.title or root.text, W, H)
    mapping, cnt = mapping_md(root)
    cov = cnt["sourced"] / max(1, cnt["n"] - 1)
    status = ("needs_fix" if any(c["status"] == "fail" for c in checks)
              else ("ok" if not warnings else "ok_with_warnings"))
    report = {"outline": os.path.abspath(a.outline), "node_count": cnt["n"],
              "sourced_nodes": cnt["sourced"], "source_coverage": round(cov, 3),
              "max_depth": max_depth(root), "branches": len(root.children),
              "warnings": warnings,
              "diagnostics": checks + [diag("E10", "warn", "", w, 4) for w in ov] +
                             [diag("E11", "warn", "", w, 5) for w in link_w],
              "readability": {"score": score, "max": 100,
                              "hint": "≥90 可交付；80–89 建议修复 warn；<80 先修 fail 项"},
              "status": status}
    p = lambda ext: os.path.join(a.outdir, a.name + ext)
    open(p(".mm"), "w", encoding="utf-8").write(mm)
    open(p(".opml"), "w", encoding="utf-8").write(opml)
    open(p(".svg"), "w", encoding="utf-8").write(svg)
    open(p("_mapping.md"), "w", encoding="utf-8").write(mapping)
    open(p("_report.json"), "w", encoding="utf-8").write(
        json.dumps(report, ensure_ascii=False, indent=2))
    print("OK nodes=%d sourced=%d depth=%d branches=%d readability=%d/100 status=%s -> %s"
          % (cnt["n"], cnt["sourced"], report["max_depth"], len(root.children),
             score, status, a.outdir))
    for w in warnings:
        print("  WARN:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
