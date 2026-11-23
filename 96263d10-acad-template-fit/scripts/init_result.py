#!/usr/bin/env python3
# init_result.py -- result.json skeleton/validate + JSONL change log. Stdlib only.
# --case C --out R (skeleton, no overwrite w/o --force); --finalize (validate, exit 1);
# --changelog --file F --rule R --before B --after A --reason W [--log L]; --logsummary.
import json, os, sys, time

CK, IK = ("output_contract", "outputContract", "contract", "output_schema"), ("case_id", "caseId", "id")
META = ("case_id", "status", "sources", "uncertainty")

def find(o, keys):
    if isinstance(o, dict):
        for k in keys:
            if k in o: return o[k]
        for v in o.values():
            r = find(v, keys)
            if r is not None: return r
    elif isinstance(o, list):
        for v in o:
            r = find(v, keys)
            if r is not None: return r
    return None

def fields(spec):
    if isinstance(spec, str): return [spec]
    if isinstance(spec, dict):
        if isinstance(spec.get("properties"), dict): return list(spec["properties"])
        return [k for k in spec if not str(k).startswith("$")]
    if isinstance(spec, list):
        out = []
        for x in spec:
            if isinstance(x, str): out.append(x)
            elif isinstance(x, dict): out.append(next((x[k] for k in ("field", "name", "key") if k in x), ""))
        return [x for x in out if x]
    return []

def get(a, k, d=None):
    return a[a.index(k) + 1] if k in a else d

def load(p):
    try: return json.load(open(p, encoding="utf-8"))
    except Exception: return {}

def main():
    a = sys.argv[1:]
    if "--changelog" in a or "--logsummary" in a:
        log = get(a, "--log", "/app/work/changes.jsonl")
        if "--logsummary" in a:
            counts = {}
            if os.path.exists(log):
                for line in open(log, encoding="utf-8"):
                    try:
                        r = json.loads(line); counts[r["rule"]] = counts.get(r["rule"], 0) + 1
                    except Exception: pass
            print(json.dumps({"log": log, "total": sum(counts.values()), "by_rule": counts}, ensure_ascii=False)); return
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "file": get(a, "--file"),
               "rule": get(a, "--rule"), "before": get(a, "--before", ""), "after": get(a, "--after", ""),
               "reason": get(a, "--reason", "")}
        if not rec["file"] or not rec["rule"]: print("ERROR: --file and --rule required"); sys.exit(1)
        os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
        open(log, "a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("logged ->", log); return
    case_p, out_p = get(a, "--case", "/input/case.json"), get(a, "--out", "/app/output/result.json")
    case = load(case_p)
    case_id, cfields = find(case, IK) or "unknown-case", fields(find(case, CK) or [])
    if "--finalize" in a:
        res = load(out_p)
        missing = [f for f in list(META) + cfields if f not in res]
        bad = [f for f in ("status", "sources", "uncertainty") if f in res and res[f] in (None, "")]
        for f in missing: print("MISSING", f)
        for f in bad: print("EMPTY", f, "-- fill honestly (e.g. uncertainty lists gaps)")
        for f in ("sources", "uncertainty"):
            if res.get(f) == []: print("WARN", f, "is empty -- confirm this is honest")
        print("OK" if not (missing or bad) else "NOT-READY"); sys.exit(1 if (missing or bad) else 0)
    if os.path.exists(out_p) and "--force" not in a:
        print("exists, not overwriting:", out_p); return
    skel = {"case_id": case_id, "status": "partial", "status_reason": "skeleton first",
            "sources": [], "uncertainty": ["adaptation not yet performed"]}
    for f in cfields:
        if f not in skel: skel[f] = None
    os.makedirs(os.path.dirname(out_p) or ".", exist_ok=True)
    json.dump(skel, open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("skeleton ->", out_p, "| contract fields:", cfields or "(none found; mirror output_contract manually)")

if __name__ == "__main__":
    main()
