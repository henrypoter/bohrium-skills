#!/usr/bin/env python3
"""axisfit.py -- pixel<->data calibration, axis-type verdict, curve digitizer.
Pure stdlib; auditable math only, never invents numbers.
Run: axisfit.py spec.json [--rules rules.json]
Spec per panel: axes x/y/y_right = {"ticks":[[px,val],...],"type":"auto|
linear|log","unit":u}; points = [{"id","x_px","y_px","y_axis":"left|right",
"xerr_px":[lo,hi],"yerr_px":[lo,hi]}]; trace_files = {"ser":"t1","s2@right":"t"}
auto: fits linear & log10, keeps higher R^2; 2nd verdict from tick spacing
("spacing": equal steps vs equal ratios) -- disagreement = warning, never
silent. Residual audit drops an outlier tick and refits (dropped_ticks). Log
verdict from few ticks = low confidence. Dual-axis: points/traces must declare
y_axis ("y_axis" / "@left|@right"); missing = assumed left WITH a warning.
Thresholds in rules.json.
"""
import json, sys, math

RULES = {"r2_min": 0.999, "drop_outliers": True, "outlier_k": 3.0,
         "max_drops": 2, "spacing_rtol": 0.15, "log_min_ticks": 3}

def fit(pairs, log):
    pts = [(float(p), float(v)) for p, v in pairs]
    if log:
        if any(v <= 0 for _, v in pts):
            return None
        pts = [(p, math.log10(v)) for p, v in pts]
    n = len(pts)
    if n < 2:
        return None
    sx = sum(p for p, _ in pts); sy = sum(v for _, v in pts)
    sxx = sum(p * p for p, _ in pts); sxy = sum(p * v for p, v in pts)
    den = n * sxx - sx * sx
    if abs(den) < 1e-12:
        return None
    a = (n * sxy - sx * sy) / den; b = (sy - a * sx) / n
    sst = sum((v - sy / n) ** 2 for _, v in pts)
    ssr = sum((v - (a * p + b)) ** 2 for p, v in pts)
    r2 = 1.0 - ssr / sst if sst > 1e-12 else (1.0 if ssr < 1e-9 else 0.0)
    return a, b, r2, [v - (a * p + b) for p, v in pts]

def spread(ds):
    m = sum(ds) / len(ds)
    return max(abs(d - m) for d in ds) / abs(m) if abs(m) > 1e-12 else 0.0

def spacing(ticks, rtol):
    t = sorted((float(p), float(v)) for p, v in ticks)
    if len(t) < 3:
        return None
    dv = [t[i + 1][1] - t[i][1] for i in range(len(t) - 1)]
    mono = all(d > 0 for d in dv) or all(d < 0 for d in dv)
    dp = [t[i + 1][0] - t[i][0] for i in range(len(t) - 1)]
    out = {"monotonic": mono,
           "pixel_even": all(d > 0 for d in dp) and spread(dp) <= rtol,
           "linear_consistent": mono and spread([abs(d) for d in dv]) <= rtol,
           "log_consistent": False}
    if mono and all(v > 0 for _, v in t):
        r = [t[i + 1][1] / t[i][1] for i in range(len(t) - 1)]
        out["log_consistent"] = all(x > 0 for x in r) and spread(r) <= rtol
    return out

def audit(ticks, log, R):
    "Fit; drop worst outlier & refit (audited), at most max_drops."
    kept = [[float(p), float(v)] for p, v in ticks]
    dropped = []
    r = fit(kept, log)
    while (r and R["drop_outliers"] and len(kept) > 2
           and len(dropped) < int(R["max_drops"])):
        res = r[3]
        i = max(range(len(res)), key=lambda j: abs(res[j]))
        rest = [abs(x) for j, x in enumerate(res) if j != i]
        if abs(res[i]) > R["outlier_k"] * max(sum(rest) / len(rest), 1e-9):
            dropped.append(kept.pop(i) + [round(res[i], 6)])
            r = fit(kept, log)
        else:
            break
    return r, dropped

def calibrate(axis, R):
    ticks = axis.get("ticks") or []
    want = axis.get("type", "auto")
    out = {"n_ticks": len(ticks), "unit": axis.get("unit"), "warnings": []}
    w = out["warnings"].append
    sp = spacing(ticks, R["spacing_rtol"])
    if sp:
        out["spacing"] = sp
        if not sp["monotonic"]:
            w("tick values not monotonic in pixel order; "
                                   "OCR misread likely")
        if not sp["pixel_even"]:
            w("tick pixels unevenly spaced; label-pixel "
                                   "mis-pairing likely")
    if len(ticks) < 2:
        out["status"] = "uncalibrated"
        w("fewer than 2 readable ticks")
        return out, None
    cands, drops = {}, {}
    for name, lg in (("linear", False), ("log", True)):
        r, dr = audit(ticks, lg, R)
        if r:
            cands[name] = r; drops[name] = dr
    out["fit_quality"] = {k: round(v[2], 6) for k, v in cands.items()}
    if want in cands:
        chosen = want
    elif cands:
        chosen = max(cands, key=lambda k: cands[k][2])
        if len(cands) == 2 and abs(cands["linear"][2] - cands["log"][2]) < 1e-3:
            w("linear/log ambiguous; verify axis labels")
    else:
        out["status"] = "uncalibrated"
        w("no usable fit (log needs all-positive ticks)")
        return out, None
    if sp and want == "auto":
        other = "log" if chosen == "linear" else "linear"
        if not sp[chosen + "_consistent"] and sp[other + "_consistent"]:
            w("R2 verdict=%s but tick spacing fits %s; "
                                   "re-verify ticks" % (chosen, other))
    a, b, r2, res = cands[chosen]
    out.update(status="ok", type=chosen, a=a, b=b, r2=round(r2, 6),
               residuals=[round(x, 6) for x in res],
               verdict_confidence="high")
    if drops[chosen]:
        out["dropped_ticks"] = drops[chosen]
        w("dropped %d outlier tick(s) then refit; re-OCR "
                               "them" % len(drops[chosen]))
    if chosen == "log" and len(ticks) - len(drops[chosen]) < R["log_min_ticks"]:
        out["verdict_confidence"] = "low"
        w("log verdict from <%d ticks is unreliable; "
                               "confirm via labels" % R["log_min_ticks"])
    if r2 < R["r2_min"]:
        w("R2<%g: tick pixels misread or axis non-linear"
                               % R["r2_min"])
    lg = chosen == "log"
    def to_data(px, a=a, b=b, lg=lg):
        t = a * float(px) + b
        return 10 ** t if lg else t
    return out, to_data

def yaxis_of(decl, has_right, warn, what):
    if decl in ("left", "right"):
        return decl
    if has_right:
        warn.append("%s: y_axis missing, ASSUMED left (dual-axis requires "
                    "explicit y_axis)" % what)
    return "left"

def conv_points(panel, fns, warn):
    has_right = "y_right" in panel
    out = []
    for pt in panel.get("points") or []:
        ya = yaxis_of(pt.get("y_axis"), has_right, warn,
                      "point %s" % pt.get("id"))
        key = "y_right" if ya == "right" else "y"
        rec = {"id": pt.get("id"), "evidence": "inferred", "y_axis": ya,
               "pixel": {"x": pt.get("x_px"), "y": pt.get("y_px")}}
        if fns.get("x") and fns.get(key):
            rec["x"] = fns["x"](pt["x_px"]); rec["y"] = fns[key](pt["y_px"])
            for k, ax in (("xerr_px", "x"), ("yerr_px", key)):
                if pt.get(k):
                    lo, hi = fns[ax](pt[k][0]), fns[ax](pt[k][1])
                    rec[k.replace("_px", "")] = [min(lo, hi), max(lo, hi)]
        else:
            rec["evidence"] = "undetermined"
            rec["reason"] = ("y_right uncalibrated" if ya == "right"
                             else "axis uncalibrated") + "; pixel coords only"
        out.append(rec)
    return out

def conv_traces(panel, fns, warn, max_pts=200):
    has_right = "y_right" in panel
    out = {}
    for name, path in (panel.get("trace_files") or {}).items():
        ya = yaxis_of(name.rpartition("@")[2], has_right, warn,
                      "trace %s" % name)
        key = "y_right" if ya == "right" else "y"
        try:
            pts = json.load(open(path, encoding="utf-8")).get("points") or []
        except Exception as e:
            out[name] = {"status": "error", "reason": str(e)}
            continue
        if not (fns.get("x") and fns.get(key)) or not pts:
            out[name] = {"status": "undetermined", "y_axis": ya,
                         "reason": "axis uncalibrated or empty trace"}
            continue
        step = max(1, len(pts) // max_pts)
        out[name] = {"status": "ok", "y_axis": ya, "evidence": "inferred",
                     "n_raw": len(pts),
                     "data": [[round(fns["x"](p[0]), 8),
                               round(fns[key](p[1]), 8)] for p in pts[::step]]}
    return out

def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    spec = json.load(open(a[0], encoding="utf-8"))
    R = dict(RULES)
    if "--rules" in a:
        try:
            R.update(json.load(open(a[a.index("--rules") + 1],
                                    encoding="utf-8")))
        except Exception as e:
            print("rules unreadable, using defaults:", e, file=sys.stderr)
    res = {"figure": spec.get("figure"), "panels": {}}
    for pn, panel in (spec.get("panels") or {}).items():
        fns, axes, warn = {}, {}, []
        for an in ("x", "y", "y_right"):
            if an in panel:
                axes[an], fns[an] = calibrate(panel[an], R)
        rec = {"axes": axes, "points": conv_points(panel, fns, warn),
               "traces": conv_traces(panel, fns, warn)}
        if warn:
            rec["warnings"] = warn
        res["panels"][pn] = rec
    json.dump(res, sys.stdout, ensure_ascii=False, indent=1)
    print()

if __name__ == "__main__":
    main()
