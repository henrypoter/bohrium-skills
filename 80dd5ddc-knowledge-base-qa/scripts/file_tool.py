#!/usr/bin/env python3
"""科研资料管理工具：内容哈希去重 + 版本链识别 + 目录规范核验 + 交付校验。纯标准库。

  inventory <dir>                  逐文件 sha256/大小/类型，重复组、版本链、异常文件
  checkmap  <dir> --spec spec.json 按 spec 的路径模板与必填元数据核验落库规范
  schema    <result.json>          交付契约校验
"""
import hashlib, json, os, re, sys

VER_TOKENS = re.compile(r"(?i)(?:[_\-\s]?(?:v|ver|rev|final|draft|copy)\d*|[_\-\s]?\(\d+\)|[_\-\s]?\d{8})")

def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def cmd_inventory(d):
    if not os.path.isdir(d):
        print(json.dumps({"ok": False, "error": "目录不存在"}, ensure_ascii=False)); return 1
    files, by_hash, errs = [], {}, []
    for root, _, fns in os.walk(d):
        for fn in sorted(fns):
            p = os.path.join(root, fn)
            if os.path.islink(p):
                errs.append({"file": p, "issue": "软链，提交与归档均不允许"}); continue
            try:
                st = os.stat(p); h = _sha(p)
            except Exception as e:
                errs.append({"file": p, "issue": "读取失败: %s" % e}); continue
            rel = os.path.relpath(p, d)
            files.append({"path": rel, "size": st.st_size, "ext": os.path.splitext(fn)[1].lower(),
                          "sha256": h, "empty": st.st_size == 0})
            by_hash.setdefault(h, []).append(rel)
    dup = [{"sha256": h[:16], "files": v} for h, v in by_hash.items() if len(v) > 1]
    chains = {}
    for f in files:
        stem = os.path.splitext(os.path.basename(f["path"]))[0]
        base = re.sub(r"\s+", " ", VER_TOKENS.sub("", stem)).strip().lower()
        chains.setdefault(base, []).append(f["path"])
    versions = [{"base": b, "files": v} for b, v in chains.items() if len(v) > 1]
    print(json.dumps({"ok": True, "n_files": len(files), "total_bytes": sum(f["size"] for f in files),
                      "by_ext": {e: sum(1 for f in files if f["ext"] == e) for e in sorted({f["ext"] for f in files})},
                      "duplicate_groups": dup, "version_chains": versions,
                      "empty_files": [f["path"] for f in files if f["empty"]],
                      "anomalies": errs}, ensure_ascii=False))
    return 0

def cmd_checkmap(d, spec_path):
    spec = json.load(open(spec_path, encoding="utf-8"))
    patterns = [re.compile(p) for p in spec.get("path_patterns", [])]
    required = spec.get("required_meta", [])
    manifest = {}
    mf = spec.get("manifest_csv")
    if mf and os.path.isfile(mf):
        import csv
        with open(mf, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                manifest[r.get("path", "")] = r
    v_file, v_meta, missing = [], [], []
    for root, _, fns in os.walk(d):
        for fn in fns:
            rel = os.path.relpath(os.path.join(root, fn), d)
            if patterns and not any(p.match(rel) for p in patterns):
                v_file.append(rel)
            row = manifest.get(rel)
            if required:
                if row is None:
                    missing.append(rel)
                else:
                    for k in required:
                        if not str(row.get(k, "")).strip():
                            v_meta.append({"path": rel, "missing_meta": k})
    out = {"ok": not v_file and not v_meta and not missing,
           "path_violations": v_file, "missing_meta": v_meta, "no_manifest_row": missing,
           "checked_patterns": len(patterns), "required_meta": required}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1

def cmd_schema(path):
    d = json.load(open(path, encoding="utf-8"))
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "directory_tree", "manifest", "dedup", "versions",
              "operations", "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    for i, m in enumerate(d.get("manifest", [])):
        for k in ("path", "sha256", "source", "version"):
            if k not in m:
                errs.append("manifest[%d] 缺 %s" % (i, k))
    for i, o in enumerate(d.get("operations", [])):
        for k in ("action", "src", "dst", "result"):
            if k not in o:
                errs.append("operations[%d] 缺 %s" % (i, k))
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "manifest": len(d.get("manifest", [])),
                      "operations": len(d.get("operations", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "inventory":
        sys.exit(cmd_inventory(a[1]))
    if a[0] == "checkmap":
        sp = a[a.index("--spec") + 1] if "--spec" in a else None
        if not sp:
            print(json.dumps({"ok": False, "error": "checkmap 需要 --spec"}, ensure_ascii=False)); sys.exit(2)
        sys.exit(cmd_checkmap(a[1], sp))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
