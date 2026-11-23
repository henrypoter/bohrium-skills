"""build_pathway.py: pathway spec JSON -> layered editable SVG (stdlib only).
Usage: build_pathway.py spec.json out.svg. Edge grammar EXTERNAL (assets/edge_rules.json)."""
import json, os, sys
from xml.sax.saxutils import escape

FONT = "Helvetica,Arial,'DejaVu Sans','Noto Sans CJK SC',sans-serif"
K = "#1a1a1a"
NS = {
    "ligand": ("#E69F00", "hex", K), "small_molecule": ("#F0E442", "hex", K),
    "receptor": ("#0072B2", "receptor", "#fff"), "protein": ("#56B4E9", "rrect", K),
    "tf": ("#56B4E9", "rrect", K), "complex": ("#009E73", "stack", "#fff"),
    "gene": ("#CC79A7", "para", K), "organelle": ("#D55E00", "ellipse", "#fff"),
    "process": ("#999999", "hex", K),
}
REL_FB = {"activates": {"marker": "arrow"}, "inhibits": {"marker": "bar"},
          "binds": {"marker": "dot"}, "unknown": {"marker": None, "badge": "?"}}
NW, NH, BAND_H, MEM_H = 132, 46, 150, 64
LEFT, TOP, GAP, LEGEND_W = 150, 60, 44, 252
STR = f'stroke="{K}" stroke-width="1.2"'
QUOT = {'"': '&quot;', "'": '&#39;'}


def rules():
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "edge_rules.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {"relations": REL_FB}


REL = rules().get("relations", REL_FB)


def esc(s):
    return escape(str(s), QUOT)


def boundary(cx, cy, w, h, tx, ty):
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    t = min((w / 2) / abs(dx) if dx else 1e9, (h / 2) / abs(dy) if dy else 1e9)
    return cx + dx * t, cy + dy * t


def layout(spec, warnings):
    comps = [dict(c) for c in (spec.get("compartments") or [{"id": "cytosol", "label": "Cytosol"}])]
    nodes = {n["id"]: dict(n) for n in spec.get("nodes", [])}
    edges = [dict(e) for e in spec.get("edges", [])]
    cids = {c["id"] for c in comps}
    for n in nodes.values():
        if n.get("compartment") not in cids:
            warnings.append(f"node {n['id']}: unknown compartment '{n.get('compartment')}'")
            n["compartment"] = "unlocalized"
    if any(n.get("compartment") == "unlocalized" for n in nodes.values()):
        comps.append({"id": "unlocalized", "label": "Unlocalized", "kind": "unknown"})
    order = [c["id"] for c in comps]
    bands = {cid: [] for cid in order}
    for n in spec.get("nodes", []):
        bands[nodes[n["id"]]["compartment"]].append(n["id"])
    for _ in range(2):
        pos = {nid: j for cid in order for j, nid in enumerate(bands[cid])}
        for cid in order:
            def key(nid, _p=dict(pos)):
                nb = [_p[m] for e in edges for m in
                      (e.get("to") if e.get("from") == nid else e.get("from") if e.get("to") == nid else None,)
                      if m in _p]
                return sum(nb) / len(nb) if nb else _p[nid]
            bands[cid].sort(key=key)
    y = TOP
    for c in comps:
        h = MEM_H if c.get("kind") == "membrane" else BAND_H
        c["y0"], c["y1"] = y, y + h
        for j, nid in enumerate(bands[c["id"]]):
            nodes[nid]["_x"] = LEFT + (j + 0.5) * (NW + GAP)
            nodes[nid]["_y"] = y + h / 2
        y += h
    width = LEFT + max([len(b) for b in bands.values()] + [1]) * (NW + GAP) + LEGEND_W
    return comps, nodes, edges, width, y


def glyph(n, mem_h):
    x, y, t = n["_x"], n["_y"], n["_type"]
    fill, shape, tc = NS[t]
    lab = escape(n.get("label", n["id"]))
    o = []
    if shape == "receptor":
        h = mem_h + 22
        o.append(f'<rect x="{x-17}" y="{y-h/2}" width="34" height="{h}" rx="8" fill="{fill}" {STR}/>'
                 f'<text x="{x}" y="{y+h/2+15}" text-anchor="middle" font-size="12" fill="{K}">{lab}</text>')
        return "".join(o)
    w, h = NW, NH
    if shape == "stack":
        o.append(f'<rect x="{x-w/2+6}" y="{y-h/2+6}" width="{w}" height="{h}" rx="10" fill="{fill}" opacity="0.45" stroke="{K}"/>')
    if shape in ("rrect", "stack"):
        o.append(f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="10" fill="{fill}" {STR}/>')
    elif shape == "para":
        p = f"{x-w/2+14},{y-h/2} {x+w/2},{y-h/2} {x+w/2-14},{y+h/2} {x-w/2},{y+h/2}"
        o.append(f'<polygon points="{p}" fill="{fill}" {STR}/>')
    elif shape == "hex":
        p = f"{x-w/2+16},{y-h/2} {x+w/2-16},{y-h/2} {x+w/2},{y} {x+w/2-16},{y+h/2} {x-w/2+16},{y+h/2} {x-w/2},{y}"
        o.append(f'<polygon points="{p}" fill="{fill}" {STR}/>')
    elif shape == "ellipse":
        o.append(f'<ellipse cx="{x}" cy="{y}" rx="{w/2}" ry="{h/2}" fill="{fill}" {STR}/>')
    it = ' font-style="italic"' if t == "gene" else ""
    o.append(f'<text x="{x}" y="{y+4}" text-anchor="middle" font-size="12.5" fill="{tc}"{it}>{lab}</text>')
    return "".join(o)


def build(spec):
    warnings = []
    comps, nodes, edges, width, bottom = layout(spec, warnings)
    mem_h = next((c["y1"] - c["y0"] for c in comps if c.get("kind") == "membrane"), MEM_H)
    for n in nodes.values():
        t = n.get("type", "protein")
        if t not in NS:
            warnings.append(f"node {n['id']}: unknown type '{t}' -> protein")
            t = "protein"
        n["_type"] = t
        n["_w"], n["_h"] = (34, mem_h + 22) if t == "receptor" else (NW, NH)
    caps = [f"Entities: {len(nodes)} · Interactions: {len(edges)}",
            "Triangle=activation · T-bar=inhibition · dot=binding",
            "Dashed=translocation · P/Ub/Me/Ac/X=mods · data-source per element"]
    H = bottom + 72
    S = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{H}" viewBox="0 0 {width} {H}" font-family="{FONT}">',
         f'<desc>case_id={esc(spec.get("case_id", ""))}</desc>',
         '<defs><marker id="m-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#333"/></marker><marker id="m-bar" viewBox="0 0 10 12" refX="9" refY="6" markerWidth="7" markerHeight="11" orient="auto"><path d="M9,0 L9,12" stroke="#333" stroke-width="2.6"/></marker><marker id="m-dot" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="7" markerHeight="7"><circle cx="5" cy="5" r="3.2" fill="#333"/></marker></defs>',
         f'<rect width="{width}" height="{H}" fill="#ffffff"/>',
         f'<g id="layer-title"><text x="{width/2}" y="28" text-anchor="middle" font-size="16" font-weight="bold" fill="{K}">{escape(spec.get("title", "Pathway diagram"))}</text></g>',
         '<g id="layer-compartments">']
    for c in comps:
        x0, x1 = LEFT - 16, width - LEGEND_W + 10
        y0, y1, kind = c["y0"], c["y1"], c.get("kind", "")
        S.append(f'<g id="comp-{esc(c["id"])}" data-kind="{kind}" data-y0="{y0:.1f}" data-y1="{y1:.1f}" data-label="{esc(c.get("label", c["id"]))}">')
        if kind == "membrane":
            S.append(f'<rect x="{x0}" y="{y0+6}" width="{x1-x0}" height="{y1-y0-12}" fill="#dff1fa"/>')
            for yy in (y0 + 6, y1 - 6):
                S.append(f'<line x1="{x0}" y1="{yy}" x2="{x1}" y2="{yy}" stroke="#7aa7bd" stroke-width="2.5"/>')
        elif kind == "unknown":
            S.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" fill="none" stroke="#999" stroke-dasharray="4 4"/>')
        S.append(f'<text x="18" y="{(y0+y1)/2+4}" font-size="13" font-style="italic" fill="#666">{escape(c.get("label", c["id"]))}</text></g>')
    S.append('</g><g id="layer-edges" stroke="#333" stroke-width="2" fill="none">')
    used_rel, used_typ = set(), set()
    for e in edges:
        a, b = nodes.get(e.get("from")), nodes.get(e.get("to"))
        if a is None or b is None:
            warnings.append(f"edge {e.get('from')}->{e.get('to')}: dangling")
            continue
        rel = e.get("relation", "unknown")
        if rel not in REL:
            warnings.append(f"edge {e['from']}->{e['to']}: relation '{rel}' -> unknown")
            rel = "unknown"
        rs = REL[rel]
        used_rel.add(rel)
        x1, y1 = boundary(a["_x"], a["_y"], a["_w"], a["_h"], b["_x"], b["_y"])
        x2, y2 = boundary(b["_x"], b["_y"], b["_w"], b["_h"], a["_x"], a["_y"])
        dash = f' stroke-dasharray="{rs["dash"]}"' if rs.get("dash") else ""
        mk = f' marker-end="url(#m-{rs["marker"]})"' if rs.get("marker") else ""
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if e.get("feedback"):
            dx, dy = x2 - x1, y2 - y1
            L = max((dx * dx + dy * dy) ** 0.5, 1)
            d = f"M{x1:.1f},{y1:.1f} Q{mx-dy/L*46:.1f},{my+dx/L*46:.1f} {x2:.1f},{y2:.1f}"
        else:
            d = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
        S.append(f'<g id="edge-{esc(e["from"])}-{esc(e["to"])}" data-relation="{rel}" data-from="{esc(e["from"])}" '
                 f'data-to="{esc(e["to"])}" data-source="{esc(e.get("source", ""))}"><path d="{d}"{dash}{mk}/>')
        if rs.get("badge"):
            bx, by = x1 + (x2 - x1) * 0.62, y1 + (y2 - y1) * 0.62
            S.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="9" fill="#fff" stroke="#333" stroke-width="1.2"/>'
                     f'<text x="{bx:.1f}" y="{by+3.5:.1f}" text-anchor="middle" font-size="9.5" fill="{K}" stroke="none">{rs["badge"]}</text>')
        S.append('</g>')
    S.append('</g><g id="layer-nodes">')
    for n in nodes.values():
        if "_x" in n:
            used_typ.add(n["_type"])
            bb = f'{n["_x"]-n["_w"]/2},{n["_y"]-n["_h"]/2},{n["_w"]},{n["_h"]}'
            S.append(f'<g id="node-{esc(n["id"])}" data-type="{n["_type"]}" data-compartment="{esc(n.get("compartment", ""))}" '
                     f'data-bbox="{bb}" data-label="{esc(n.get("label", n["id"]))}" data-source="{esc(n.get("source", ""))}">')
            S.append(glyph(n, mem_h))
            S.append('</g>')
    lx, ly = width - LEGEND_W + 22, TOP + 6
    rows = [("typ", t) for t in sorted(used_typ)] + [("rel", r) for r in sorted(used_rel)]
    S.append(f'</g><g id="layer-legend"><rect x="{lx-12}" y="{ly-22}" width="{LEGEND_W-34}" height="{30+22*len(rows)}" rx="8" fill="#fafafa" stroke="#bbb"/><text x="{lx}" y="{ly}" font-size="12.5" font-weight="bold" fill="{K}">Legend</text>')
    yy = ly + 22
    for kind, key in rows:
        if kind == "typ":
            S.append(f'<g data-kind="typ" data-key="{key}"><rect x="{lx}" y="{yy-11}" width="26" height="15" rx="4" fill="{NS[key][0]}" stroke="{K}"/><text x="{lx+34}" y="{yy+1}" font-size="11" fill="{K}">{key}</text></g>')
        else:
            rs = REL[key]
            dash = f' stroke-dasharray="{rs["dash"]}"' if rs.get("dash") else ""
            mk = f' marker-end="url(#m-{rs["marker"]})"' if rs.get("marker") else ""
            extra = (f' [{rs["badge"]}]' if rs.get("badge") not in (None, "?") else " (?=uncertain)" if key == "unknown" else "")
            S.append(f'<g data-kind="rel" data-key="{key}"><line x1="{lx}" y1="{yy-4}" x2="{lx+28}" y2="{yy-4}" stroke="#333" stroke-width="2"{dash}{mk}/><text x="{lx+36}" y="{yy}" font-size="11" fill="{K}">{key}{extra}</text></g>')
        yy += 22
    S.append('</g><g id="layer-caption" font-size="10.5" fill="#555">')
    for i, c in enumerate(caps):
        S.append(f'<text x="{LEFT-16}" y="{H-40+14*i}">{escape(c)}</text>')
    S.append('</g></svg>')
    return "\n".join(S), warnings


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: build_pathway.py spec.json out.svg")
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    if not spec.get("nodes"):
        sys.exit("spec error: empty nodes")
    svg, warnings = build(spec)
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        f.write(svg)
    print(json.dumps({"nodes": len(spec["nodes"]), "edges": len(spec.get("edges", [])),
                      "svg": sys.argv[2], "warnings": warnings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
