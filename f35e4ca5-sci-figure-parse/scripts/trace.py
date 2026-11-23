#!/usr/bin/env python3
"""trace.py -- color-based curve digitizer (pixel space). Requires PIL.
  trace.py IMG colors [--top 12]      list dominant saturated color clusters
  trace.py IMG extract --rgb R,G,B [--tol 42] [--minx 0] [--maxx W]
      per x column, median y of matching pixels -> {"points": [[x,y],...]}
      in PIXEL coords; reference from an axisfit spec "trace_files" for data
      coords. Never invents points.
"""
import json, sys, statistics

def load(path):
    try:
        from PIL import Image
    except ImportError:
        sys.exit('{"ok": false, "note": "PIL absent; trace unavailable, '
                 'degrade to tick-based manual reading"}')
    return Image.open(path).convert("RGB")

def colors(path, top):
    im = load(path)
    im = im.resize((max(1, im.width // 4), max(1, im.height // 4)))
    q = im.quantize(colors=48).convert("RGB")
    cnt = {}
    raw = q.tobytes()
    for i in range(0, len(raw), 3):
        p = raw[i:i + 3]
        if max(p) - min(p) < 40 or max(p) < 60:
            continue  # skip grays and near-black text/axes
        cnt[p] = cnt.get(p, 0) + 1
    best = sorted(cnt.items(), key=lambda kv: -kv[1])[:top]
    return {"ok": True, "clusters": [{"rgb": list(c), "px_approx": n * 16}
            for c, n in best],
            "note": "pick one cluster per series; run extract --rgb for each"}

def extract(path, rgb, tol, minx, maxx):
    im = load(path)
    w, h = im.size
    maxx = min(maxx, w - 1)
    px = im.load()
    cols = {}
    for x in range(max(0, minx), maxx + 1):
        ys = [y for y in range(h)
              if max(abs(px[x, y][0] - rgb[0]), abs(px[x, y][1] - rgb[1]),
                     abs(px[x, y][2] - rgb[2])) <= tol]
        if ys:
            cols[x] = statistics.median(ys)
    pts = [[x, y] for x, y in sorted(cols.items())]
    out = {"ok": True, "rgb": list(rgb), "tol": tol, "n_columns": len(pts),
           "coverage": round(len(pts) / max(1, maxx - minx + 1), 3),
           "points": pts,
           "note": "pixel coords; convert via axisfit trace_files. "
                   "coverage << 1 means dashed line or overlap"}
    if len(pts) < 3:
        out["ok"] = False
        out["note"] = "too few matching pixels; color/tol wrong or no series"
    return out

def main():
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    img, mode = a[0], a[1]
    if mode == "colors":
        res = colors(img, int(a[a.index("--top") + 1]) if "--top" in a else 12)
    else:
        rgb = [int(v) for v in a[a.index("--rgb") + 1].split(",")]
        tol = int(a[a.index("--tol") + 1]) if "--tol" in a else 42
        minx = int(a[a.index("--minx") + 1]) if "--minx" in a else 0
        maxx = int(a[a.index("--maxx") + 1]) if "--maxx" in a else 10 ** 9
        res = extract(img, rgb, tol, minx, maxx)
    json.dump(res, sys.stdout, ensure_ascii=False)
    print()

if __name__ == "__main__":
    main()
