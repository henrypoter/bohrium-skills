#!/usr/bin/env python3
"""probe.py -- inspect a figure image before analysis. Prints JSON, exit 0 always.
Stdlib header sniff (PNG/JPEG/PDF) works without PIL; PIL adds exposure/
contrast/color stats and warnings. Usage: probe.py IMG
"""
import json, sys, struct

def sniff(path):
    with open(path, "rb") as f:
        h = f.read(65536)
    if h[:8] == b"\x89PNG\r\n\x1a\n":
        w, hh = struct.unpack(">II", h[16:24])
        return {"format": "PNG", "width": w, "height": hh}
    if h[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(h):
            if h[i] != 0xFF:
                i += 1; continue
            m = h[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3):
                hh, w = struct.unpack(">HH", h[i + 5:i + 9])
                return {"format": "JPEG", "width": w, "height": hh}
            i += 2 + struct.unpack(">H", h[i + 2:i + 4])[0]
        return {"format": "JPEG", "note": "dimensions not in first 64KB"}
    if h[:4] == b"%PDF":
        return {"format": "PDF",
                "note": "rasterize first: pdftoppm -r 300 -png in.pdf page"}
    return {"format": "unknown", "note": "unrecognized file signature"}

def pil_stats(path):
    try:
        from PIL import Image
    except ImportError:
        return {"pil": False, "note": "PIL absent; header-only mode (degraded)"}
    im = Image.open(path)
    out = {"pil": True, "mode": im.mode, "width": im.width, "height": im.height}
    g = im.convert("L")
    hist = g.histogram(); tot = sum(hist) or 1
    mean = sum(i * c for i, c in enumerate(hist)) / tot
    var = sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / tot
    out["luma"] = {"mean": round(mean, 1), "std": round(var ** 0.5, 1),
                   "frac_white>245": round(sum(hist[245:]) / tot, 4),
                   "frac_black<10": round(sum(hist[:10]) / tot, 4)}
    w = []
    if out["luma"]["frac_white>245"] > 0.995 and out["luma"]["std"] < 8:
        w.append("near-blank or overexposed image")
    if out["luma"]["std"] < 12:
        w.append("very low contrast; OCR unreliable")
    if im.width < 400:
        w.append("low resolution; tick labels unreadable")
    if im.mode in ("RGB", "RGBA"):
        px = im.convert("RGB").resize((64, 64)).tobytes()
        n_sat = sum(1 for i in range(0, len(px), 3)
                    if max(px[i:i + 3]) - min(px[i:i + 3]) > 40)
        out["colored_fraction"] = round(n_sat / 4096, 4)
        if out["colored_fraction"] < 0.005:
            w.append("grayscale: color-based tracing will not work")
    out["warnings"] = w
    return out

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    info = sniff(args[0])
    if info.get("format") not in ("PDF", "unknown"):
        info.update(pil_stats(args[0]))
    json.dump(info, sys.stdout, ensure_ascii=False, indent=1)
    print()

if __name__ == "__main__":
    main()
