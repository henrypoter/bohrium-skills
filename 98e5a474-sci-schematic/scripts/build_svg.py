#!/usr/bin/env python3
"""build_svg.py: elements.json -> layered editable SVG schematic. Stdlib only.

Usage: build_svg.py elements.json out.svg
Layers <g id="layer-groups|edges|nodes|legend">; real <text>; every group carries
data-source. Edge grammar is EXTERNAL (assets/edge_rules.json, SBGN-aligned):
activates/flows=triangle arrow, inhibits=T bar, contains/unknown=dashed no head.
Node boxes sized from estimated DejaVu Sans text width (no label overflow).
legend "auto"/omitted derives entries ONLY from kinds+edge types actually used;
node color keyed by kind, so legend==figure by construction.
"""
import json, sys, math, os
from xml.sax.saxutils import escape

RULES_FB = {"activates": {"marker": "arrow", "dash": ""}, "flows": {"marker": "arrow", "dash": ""},
            "inhibits": {"marker": "tbar", "dash": ""}, "contains": {"marker": "", "dash": "6,4"},
            "unknown": {"marker": "", "dash": "4,4"}}
PAL_FB = {"node": ["#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2", "#D55E00", "#CC79A7"],
          "edge": "#333333", "group_fill": "#F5F5F5", "font": "DejaVu Sans"}


def asset(name, fallback, merge=False):
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", name)
    try:
        d = json.load(open(p, encoding="utf-8"))
        return {**fallback, **d} if merge else d
    except Exception:
        return fallback


def src_str(s):
    """source may be a legacy string or {locator, quote}; render both readably."""
    if isinstance(s, dict):
        loc, q = str(s.get("locator", "") or ""), str(s.get("quote", "") or "")
        return f"{loc}: '{q}'" if q else loc
    return str(s or "")


def est_w(s, size):
    """Estimated DejaVu Sans advance width in px (per-char class table)."""
    w = 0.0
    for ch in s:
        if ch in "iljtfI.,:;'|! ": w += 0.30
        elif ch in "mwMW@": w += 0.88
        elif ord(ch) > 0x2E7F: w += 1.0   # CJK full-width
        elif ch.isupper(): w += 0.72
        elif ch.isdigit(): w += 0.64
        else: w += 0.57
    return w * size


def layout(nodes, edges, W, H):
    """Layered layout: layer = longest path from a source (upstream on the left)."""
    ids = [n["id"] for n in nodes]
    layer = dict.fromkeys(ids, 0)
    for _ in range(len(ids)):
        ch = False
        for e in edges:
            f, t = e.get("from"), e.get("to")
            if f in layer and t in layer and layer[t] < layer[f] + 1:
                layer[t] = layer[f] + 1
                ch = True
        if not ch:
            break
    by = {}
    for i in ids:
        by.setdefault(layer[i], []).append(i)
    n = max(len(by), 1)
    return {i: (W * (L + 1) / (n + 1), H * (k + 1) / (len(m) + 1))
            for L, m in by.items() for k, i in enumerate(m)}


def build(spec):
    pal = asset("palette.json", PAL_FB, merge=True)
    rules = asset("edge_rules.json", {}).get("rules", RULES_FB)
    cv = spec.get("canvas", {})
    W, H = int(cv.get("width", 900)), int(cv.get("height", 560))
    nodes, edges, groups = spec.get("nodes", []), spec.get("edges", []), spec.get("groups", [])
    pos = layout(nodes, edges, W, H)
    kinds = list(dict.fromkeys(n.get("kind", "entity") for n in nodes))
    kcol = {k: pal["node"][i % len(pal["node"])] for i, k in enumerate(kinds)}
    types = list(dict.fromkeys(e.get("type", "flows") for e in edges))
    size = {}
    for nd in nodes:  # text metrics first: box must fit label + sublabel
        w = max(96, est_w(nd.get("label", nd["id"]), 13) + 30, est_w(nd.get("sublabel", ""), 10) + 26)
        size[nd["id"]] = (min(w, 300), 46)
        if w > 300:
            print(f"WARN: label too long, truncated fit: {nd.get('label')!r}", file=sys.stderr)
    auto = not spec.get("legend") or spec.get("legend") == "auto"
    legend = ([{"key": k, "label": k, "kind": "node"} for k in kinds] +
              [{"key": t, "label": t, "kind": "edge"} for t in types]) if auto else spec["legend"]

    s = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<!-- traceability: every element group carries data-source = origin file -->',
         f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="{escape(pal["font"])}">',
         '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" '
         'orient="auto" markerUnits="strokeWidth">'
         f'<path d="M0,0 L9,3 L0,6 Z" fill="{pal["edge"]}"/></marker>'
         '<marker id="tbar" markerWidth="12" markerHeight="12" refX="9" refY="3" '
         'orient="auto" markerUnits="strokeWidth">'
         f'<path d="M8,-3 L8,9" stroke="{pal["edge"]}" stroke-width="2.2"/></marker></defs>',
         f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>']
    if spec.get("title"):
        s.append(f'<g id="layer-title"><text x="{W/2:.0f}" y="26" text-anchor="middle" '
                 f'font-size="18" font-weight="bold">{escape(spec["title"])}</text></g>')
    s.append('<g id="layer-groups">')
    for gi, g in enumerate(groups):
        mem = [(pos[m], size[m]) for m in g.get("members", []) if m in pos]
        if not mem:
            continue
        x0 = min(p[0][0] - p[1][0] / 2 for p in mem) - 16
        x1 = max(p[0][0] + p[1][0] / 2 for p in mem) + 16
        y0 = min(p[0][1] for p in mem) - 46
        y1 = max(p[0][1] for p in mem) + 46
        s.append(f'<g id="group-{escape(g.get("id", str(gi)))}" data-source="{escape(src_str(g.get("source", "")))}">'
                 f'<rect x="{x0:.0f}" y="{y0:.0f}" width="{x1-x0:.0f}" height="{y1-y0:.0f}" rx="10" '
                 f'fill="{pal["group_fill"]}" stroke="#999" stroke-dasharray="6,4"/>'
                 f'<text x="{x0+8:.0f}" y="{y0+18:.0f}" font-size="12" fill="#555">'
                 f'{escape(g.get("label", ""))}</text></g>')
    s.append('</g><g id="layer-edges">')
    for ei, e in enumerate(edges):
        f, t = e.get("from"), e.get("to")
        if f not in pos or t not in pos:
            continue
        r = rules.get(e.get("type", "flows"), rules.get("flows", RULES_FB["flows"]))
        (x1, y1), (x2, y2) = pos[f], pos[t]
        d = math.hypot(x2 - x1, y2 - y1) or 1.0
        r1, r2 = size[f][0] / 2 + 6, size[t][0] / 2 + 6
        x1, y1 = x1 + (x2 - x1) * r1 / d, y1 + (y2 - y1) * r1 / d
        x2, y2 = x2 - (x2 - x1) * r2 / d, y2 - (y2 - y1) * r2 / d
        da = f' stroke-dasharray="{r["dash"]}"' if r.get("dash") else ""
        mk = f' marker-end="url(#{r["marker"]})"' if r.get("marker") else ""
        s.append(f'<g id="edge-{ei}" data-type="{escape(e.get("type", "flows"))}" '
                 f'data-source="{escape(src_str(e.get("source", "")))}">'
                 f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                 f'stroke="{pal["edge"]}" stroke-width="1.8"{da}{mk}/>')
        if e.get("label"):
            s.append(f'<text x="{(x1+x2)/2:.0f}" y="{(y1+y2)/2 - 6:.0f}" text-anchor="middle" '
                     f'font-size="11" fill="#444">{escape(e["label"])}</text>')
        s.append('</g>')
    s.append('</g><g id="layer-nodes">')
    for nd in nodes:
        x, y = pos[nd["id"]]
        w, h = size[nd["id"]]
        col = kcol[nd.get("kind", "entity")]
        s.append(f'<g id="node-{escape(nd["id"])}" data-kind="{escape(nd.get("kind", "entity"))}" '
                 f'data-source="{escape(src_str(nd.get("source", "")))}">'
                 f'<rect x="{x-w/2:.0f}" y="{y-h/2:.0f}" width="{w:.0f}" height="{h}" rx="8" '
                 f'fill="{col}" fill-opacity="0.25" stroke="{col}" stroke-width="2"/>'
                 f'<text x="{x:.0f}" y="{y+1:.0f}" text-anchor="middle" font-size="13" '
                 f'font-weight="bold">{escape(nd.get("label", nd["id"]))}</text>')
        if nd.get("sublabel"):
            s.append(f'<text x="{x:.0f}" y="{y+16:.0f}" text-anchor="middle" font-size="10" '
                     f'fill="#333">{escape(nd["sublabel"])}</text>')
        s.append('</g>')
    s.append('</g>')
    if legend:
        lw = max(est_w(str(i.get("label", "")), 11) for i in legend) + 62
        lx, ly = 16, H - 16 - 20 * len(legend)
        s.append(f'<g id="layer-legend" data-derived="{"auto" if auto else "explicit"}">'
                 f'<rect x="{lx-8}" y="{ly-18}" width="{lw:.0f}" height="{20*len(legend)+26}" '
                 'fill="#FFF" stroke="#BBB"/>'
                 f'<text x="{lx}" y="{ly-4}" font-size="11" font-weight="bold">Legend</text>')
        for li, item in enumerate(legend):
            yy = ly + 14 + li * 20
            key = str(item.get("key", item.get("label", "")))
            if item.get("kind") == "edge" or key in rules:
                r = rules.get(key, RULES_FB["unknown"])
                sw = (f'<line x1="{lx}" y1="{yy-3}" x2="{lx+22}" y2="{yy-3}" stroke="{pal["edge"]}" '
                      f'stroke-width="1.8"'
                      + (f' stroke-dasharray="{r["dash"]}"' if r.get("dash") else "")
                      + (f' marker-end="url(#{r["marker"]})"' if r.get("marker") else "") + "/>")
            else:
                col = item.get("color", kcol.get(key, pal["node"][li % len(pal["node"])]))
                sw = f'<rect x="{lx}" y="{yy-9}" width="14" height="12" fill="{col}" fill-opacity="0.4" stroke="{col}"/>'
            s.append(f'<g id="legend-{li}" data-key="{escape(key)}" '
                     f'data-source="{escape(src_str(item.get("source", "auto-derived" if auto else "")))}">{sw}'
                     f'<text x="{lx+28}" y="{yy+1}" font-size="11">{escape(str(item.get("label", "")))}</text></g>')
        s.append('</g>')
    for ui, note in enumerate(spec.get("units_notes", [])):
        s.append(f'<g id="layer-note-{ui}"><text x="{W-12}" y="{H-12-ui*16}" text-anchor="end" '
                 f'font-size="10" fill="#666">{escape(note)}</text></g>')
    s.append('</svg>')
    return "\n".join(s) + "\n"


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: build_svg.py elements.json out.svg")
    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    svg = build(spec)
    open(sys.argv[2], "w", encoding="utf-8").write(svg)
    auto = not spec.get("legend") or spec.get("legend") == "auto"
    print(f"wrote {sys.argv[2]} ({len(svg)} bytes, {len(spec.get('nodes', []))} nodes, "
          f"{len(spec.get('edges', []))} edges, legend={'auto' if auto else 'explicit'})")


if __name__ == "__main__":
    main()
