#!/usr/bin/env python3
"""阅读批注与知识沉淀工具：锚点核验 / 笔记-证据回路 / 关联依据 / 版本归并 / 可复现契约。纯标准库。

  anchor_check <annotations.json> [--text <source.txt>]  每条批注类型合法、页/位置齐全、引文逐字在原文
  note_check   <notes.json>                              每条笔记论断有原文支撑且支撑定位到页/段
  link_check   <links.json>                              每条关联有明确依据（杜绝只凭关键词重合）
  version_check <files.json>                             按内容哈希归并重复/多版本，批注挂在逻辑文档上
  schema       <result.json>                             可复现契约（文件哈希+脚本版本+锚点）
"""
import json, re, sys, unicodedata

TYPES = {"highlight", "underline", "margin", "handwritten", "webclip"}
NOTE_KINDS = {"question", "method", "conclusion", "reusable", "doubt"}
RELATIONS = {"supports", "contradicts", "extends", "same_method", "same_author", "part_of", "other"}


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def _norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    return re.sub(r"\s+", "", s)


def cmd_anchor_check(path, text_path=None):
    d = _load(path)
    anns = d.get("annotations", d if isinstance(d, list) else [])
    text = None
    if text_path:
        try:
            text = _norm(open(text_path, encoding="utf-8", errors="replace").read())
        except Exception as e:
            print(json.dumps({"ok": False, "error": "原文读取失败: %s" % e}, ensure_ascii=False)); return 1
    errs, not_found, bad_type, missing = [], [], [], []
    for i, a in enumerate(anns):
        aid = a.get("id") or "ann[%d]" % i
        if a.get("type") not in TYPES:
            bad_type.append({"id": aid, "type": a.get("type")})
        for k in ("source_file", "page", "quote"):
            if a.get(k) in (None, ""):
                missing.append({"id": aid, "field": k})
        if not a.get("color") and a.get("type") in ("highlight", "underline"):
            missing.append({"id": aid, "field": "color(颜色含义不可抹平)"})
        if text is not None:
            q = _norm(a.get("quote"))
            if q and q not in text:
                not_found.append({"id": aid, "quote": str(a.get("quote"))[:40]})
    out = {"ok": not errs and not not_found and not bad_type and not missing,
           "n_annotations": len(anns), "anchor_not_in_source": not_found,
           "type_invalid_or_mixed": bad_type, "missing_field": missing, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，跳过逐字核验"
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_note_check(path):
    d = _load(path)
    notes = d.get("notes", d if isinstance(d, list) else [])
    errs, no_support, bad_kind, dangling = [], [], [], []
    for i, n in enumerate(notes):
        nid = n.get("id") or "note[%d]" % i
        if n.get("kind") not in NOTE_KINDS:
            bad_kind.append({"id": nid, "kind": n.get("kind")})
        sup = n.get("support", [])
        if not sup:
            no_support.append(nid)
        for j, s in enumerate(sup):
            if not s.get("location"):
                errs.append("note %s support[%d] 缺 location(须定位到页/段)" % (nid, j))
            if not (s.get("annotation_id") or s.get("quote")):
                dangling.append({"note": nid, "support": j})
    out = {"ok": not errs and not no_support and not bad_kind and not dangling,
           "n_notes": len(notes), "notes_without_support": no_support,
           "kind_invalid": bad_kind, "support_without_anchor": dangling, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_link_check(path):
    d = _load(path)
    links = d.get("links", d if isinstance(d, list) else [])
    errs, no_basis, weak_basis = [], [], []
    for i, l in enumerate(links):
        lid = "%s->%s" % (l.get("from"), l.get("to"))
        if l.get("relation") not in RELATIONS:
            errs.append("link %s relation 非法: %s" % (lid, l.get("relation")))
        basis = str(l.get("basis", "")).strip()
        if not basis:
            no_basis.append(lid)
        elif len(basis) < 8 or ("关键词" in basis and len(basis) < 15):
            weak_basis.append({"link": lid, "basis": basis})
    out = {"ok": not errs and not no_basis and not weak_basis,
           "n_links": len(links), "links_without_basis": no_basis,
           "links_keyword_only": weak_basis, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_version_check(path):
    d = _load(path)
    files = d.get("files", [])
    by_hash = {}
    for f in files:
        h = f.get("sha256")
        if not h:
            continue
        by_hash.setdefault(h, []).append(f.get("path"))
    dup_groups = {h: ps for h, ps in by_hash.items() if len(ps) > 1}
    no_hash = [f.get("path") for f in files if not f.get("sha256")]
    errs = []
    if no_hash:
        errs.append("缺 sha256 的文件(无法归并与复现): %s" % no_hash)
    out = {"ok": not errs, "n_files": len(files), "n_duplicate_groups": len(dup_groups),
           "duplicate_groups": dup_groups, "files_without_hash": no_hash, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


def cmd_schema(path):
    d = _load(path)
    errs = []
    for k in ("case_id", "status", "script_version", "sources", "annotations", "notes",
              "links", "counts", "skipped", "conflicts", "gain", "unchecked", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("script_version"):
        errs.append("script_version 为空(可复现需脚本版本)")
    for i, s in enumerate(d.get("sources", [])):
        if not s.get("sha256"):
            errs.append("sources[%d] 缺 sha256(过程不可复现)" % i)
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "annotations": len(d.get("annotations", [])),
                      "notes": len(d.get("notes", [])), "links": len(d.get("links", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "anchor_check":
        tp = a[a.index("--text") + 1] if "--text" in a else None
        sys.exit(cmd_anchor_check(a[1], tp))
    if a[0] == "note_check":
        sys.exit(cmd_note_check(a[1]))
    if a[0] == "link_check":
        sys.exit(cmd_link_check(a[1]))
    if a[0] == "version_check":
        sys.exit(cmd_version_check(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
