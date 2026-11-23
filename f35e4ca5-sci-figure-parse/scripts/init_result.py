#!/usr/bin/env python3
"""init_result.py -- create / validate result.json. Stdlib only.
  init_result.py --case /input/case.json --out /app/output/result.json [--force]
      skeleton, contract fields = null; no overwrite without --force.
  init_result.py --finalize --case ... --out ...
      check contract fields + case_id/status/sources/uncertainty; print OK or
      MISSING/EMPTY lines; exit 1 if anything missing. Never fabricates.
"""
import json, sys, os

CONTRACT_KEYS = ("output_contract", "outputContract", "contract", "output_schema")
ID_KEYS = ("case_id", "caseId", "id")
META = ("case_id", "status", "sources", "uncertainty")

def find(obj, keys):
    if isinstance(obj, dict):
        for k in keys:
            if k in obj:
                return obj[k]
        for v in obj.values():
            r = find(v, keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, keys)
            if r is not None:
                return r
    return None

def fields(spec):
    if isinstance(spec, str):
        return [spec]
    if isinstance(spec, dict):
        if isinstance(spec.get("properties"), dict):
            return list(spec["properties"])
        if isinstance(spec.get("fields"), (list, dict)):
            return fields(spec["fields"])
        return [k for k in spec if not str(k).startswith("$")]
    if isinstance(spec, list):
        return [x for x in (it if isinstance(it, str) else
                next((it[k] for k in ("field", "name", "key") if k in it), "")
                if isinstance(it, (str, dict)) else "" for it in spec) if x]
    return []

def load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}

def main():
    a = sys.argv[1:]
    get = lambda k, d: a[a.index(k) + 1] if k in a else d
    case = load(get("--case", "/input/case.json"))
    out_p = get("--out", "/app/output/result.json")
    case_id = find(case, ID_KEYS) or "unknown-case"
    cfields = fields(find(case, CONTRACT_KEYS) or [])
    if "--finalize" in a:
        res = load(out_p)
        missing = [f for f in list(META) + cfields if f not in res]
        bad = [f for f in ("status", "sources", "uncertainty")
               if f in res and res[f] in (None, "")]
        for f in missing:
            print("MISSING", f)
        for f in bad:
            print("EMPTY", f, "-- fill honestly")
        for f in ("sources", "uncertainty"):
            if res.get(f) == []:
                print("WARN", f, "is empty -- confirm this is honest")
        print("OK" if not (missing or bad) else "NOT-READY")
        sys.exit(1 if (missing or bad) else 0)
    if os.path.exists(out_p) and "--force" not in a:
        print("exists, not overwriting:", out_p)
        return
    skel = {"case_id": case_id, "status": "partial",
            "status_reason": "skeleton before analysis (save honest result "
                             "first, improve incrementally)",
            "sources": [], "uncertainty": ["analysis not yet performed"]}
    for f in cfields:
        if f not in skel:
            skel[f] = None
    os.makedirs(os.path.dirname(out_p) or ".", exist_ok=True)
    json.dump(skel, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("skeleton ->", out_p, "| contract fields:", cfields or "(none; "
          "mirror output_contract manually)")

if __name__ == "__main__":
    main()
