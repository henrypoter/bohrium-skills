#!/usr/bin/env python3
"""ocr_words.py -- run tesseract (preinstalled ocr-tool) on a figure, emit JSON
words with pixel boxes + numeric tick_candidates (centroids) for the axisfit
spec. Usage: ocr_words.py IMG [--psm 11] [--lang eng]
If tesseract is absent, ok=false -> degrade honestly, never guess ticks.
"""
import json, subprocess, sys, shutil, re, tempfile, os

NUM = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?[a-zA-Zµμ%]*$")

def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    img = args[0]
    get = lambda k, d: args[args.index(k) + 1] if k in args else d
    psm, lang = get("--psm", "11"), get("--lang", "eng")
    tess = shutil.which("tesseract")
    if not tess:
        json.dump({"ok": False, "note": "tesseract not found; "
                   "no OCR fallback -- mark tick-dependent values undetermined"},
                  sys.stdout, ensure_ascii=False)
        print()
        return
    tsv = subprocess.run([tess, img, "stdout", "--psm", psm, "-l", lang, "tsv"],
                         capture_output=True, text=True).stdout
    words = []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 12 or not f[11].strip():
            continue
        try:
            conf = float(f[10]); x, y, w, h = map(int, f[6:10])
        except ValueError:
            continue
        if conf < 0:
            continue
        words.append({"text": f[11].strip(), "conf": round(conf, 1),
                      "x": x, "y": y, "w": w, "h": h,
                      "cx": x + w / 2, "cy": y + h / 2})
    ticks = [w for w in words if NUM.match(w["text"])]
    json.dump({"ok": True, "n_words": len(words), "words": words,
               "tick_candidates": ticks,
               "note": "cluster tick_candidates by cx (y-axis, incl. right "
                       "edge for dual axis) or cy (x-axis)"},
              sys.stdout, ensure_ascii=False, indent=1)
    print()

if __name__ == "__main__":
    main()
