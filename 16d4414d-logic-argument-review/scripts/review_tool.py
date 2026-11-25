#!/usr/bin/env python3
"""论文质量审查工具：引文逐字核验(误报抑制) + 分面覆盖统计 + 交付校验。纯标准库。

  verify  <issues.json> [--text manuscript.txt]   每条问题的 quote 是否真在原文中逐字存在；重复问题检测
  logic_check <issues.json> [--text manuscript.txt] 判对三件事：引文逐字 + 定位精确到句 + 建议可执行
  summary <issues.json>                          六类检查项覆盖矩阵 + 严重度分布
  schema  <result.json>                          交付契约校验
"""
import json, re, sys, unicodedata

CATS = ["fact", "citation", "design", "statistics", "argument", "compliance"]
SEV = ["critical", "major", "minor"]


def _norm(s):
    s = unicodedata.normalize("NFKC", str(s or ""))
    s = re.sub(r"\s+", "", s)
    return s


def _load(p):
    d = json.load(open(p, encoding="utf-8"))
    return d.get("issues", d) if isinstance(d, dict) else d


def cmd_verify(path, text_path=None):
    issues = _load(path)
    text = None
    if text_path:
        try:
            text = _norm(open(text_path, encoding="utf-8", errors="replace").read())
        except Exception as e:
            print(json.dumps({"ok": False, "error": "原文读取失败: %s" % e}, ensure_ascii=False))
            return 1
    not_found, dup, errs = [], [], []
    seen = {}
    for i, it in enumerate(issues):
        q = _norm(it.get("quote"))
        if text is not None:
            if not q:
                errs.append("issues[%d] quote 为空，无法核验" % i)
            elif q not in text:
                not_found.append({"id": it.get("id"), "quote": it.get("quote", "")[:60]})
        key = (_norm(it.get("location")), q)
        if key in seen:
            dup.append({"a": seen[key], "b": it.get("id"), "reason": "位置与引文完全相同"})
        else:
            seen[key] = it.get("id")
    out = {"ok": not not_found and not errs, "total": len(issues),
           "quote_not_in_source": not_found, "duplicates": dup, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，跳过逐字核验（仅做重复检测）"
        out["ok"] = not errs
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_summary(path):
    issues = _load(path)
    cat = {c: 0 for c in CATS}
    sev = {s: 0 for s in SEV}
    other = []
    for it in issues:
        c = it.get("category")
        if c in cat:
            cat[c] += 1
        elif c:
            other.append(c)
        s = it.get("severity")
        if s in sev:
            sev[s] += 1
    missing = [c for c in CATS if cat[c] == 0]
    print(json.dumps({"ok": True, "total": len(issues), "by_category": cat, "by_severity": sev,
                      "unchecked_categories": missing, "unknown_categories": sorted(set(other)),
                      "category_coverage": round(1 - len(missing) / float(len(CATS)), 3)},
                     ensure_ascii=False))
    return 0


CLAIM_TYPES = {"author_claim", "cited_claim", "hypothesis"}
VAGUE_LOC = {"引言", "绪论", "方法", "结果", "讨论", "结论", "摘要", "正文", "第一章", "第二章",
             "第三章", "第四章", "第五章", "第1章", "第2章", "第3章", "第4章", "第5章",
             "讨论部分", "方法部分", "结果部分", "结论部分", "摘要部分", "正文部分"}
VAGUE_FIX = {"改进论证", "加强逻辑", "完善一下", "需要修改", "不够严谨", "补充说明", "进一步修改", "再改改"}


def _precise_loc(loc):
    """定位是否精确到句/段/行，而非只给章节名。"""
    loc = str(loc or "").strip()
    if not loc:
        return False
    if loc in VAGUE_LOC:
        return False
    if re.search(r"(页|段|句|行|第\s*\d+\s*[句段行页]|[Pp]\.?\d+|para|line|sentence)", loc):
        return True
    if re.search(r"\d", loc):
        return True
    return False


def _actionable_fix(fix):
    """修改建议是否可执行（含具体动作词，非空泛）。"""
    fix = str(fix or "").strip()
    if len(fix) < 6:
        return False
    if fix in VAGUE_FIX:
        return False
    if re.search(r"(补|增|删|改|降|强化|限定|注明|引用|重写|替换|移除|标注|区分|并列|调整|改为|移出)", fix):
        return True
    return False


def cmd_logic_check(path, text_path=None):
    """判对三件事机检：①引文逐字回原文 ②定位精确到句 ③建议可执行。"""
    issues = _load(path)
    text = None
    if text_path:
        try:
            text = _norm(open(text_path, encoding="utf-8", errors="replace").read())
        except Exception as e:
            print(json.dumps({"ok": False, "error": "原文读取失败: %s" % e}, ensure_ascii=False))
            return 1
    not_found, vague_loc, vague_fix, errs = [], [], [], []
    for i, it in enumerate(issues):
        iid = it.get("id") or "issues[%d]" % i
        q = _norm(it.get("quote"))
        if text is not None and (not q or q not in text):
            not_found.append({"id": iid, "quote": str(it.get("quote"))[:60]})
        if not _precise_loc(it.get("location")):
            vague_loc.append({"id": iid, "location": str(it.get("location"))[:40]})
        if not _actionable_fix(it.get("fix")):
            vague_fix.append({"id": iid, "fix": str(it.get("fix"))[:40]})
        ct = it.get("claim_type")
        if ct is not None and ct not in CLAIM_TYPES:
            errs.append("issues[%d] claim_type 非法: %s" % (i, ct))
    out = {"ok": not not_found and not vague_loc and not vague_fix and not errs,
           "total": len(issues), "quote_not_in_source": not_found,
           "imprecise_location": vague_loc, "unactionable_fix": vague_fix, "errors": errs}
    if text is None:
        out["note"] = "未提供 --text，跳过逐字核验"
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


def cmd_schema(path):
    d = json.load(open(path, encoding="utf-8")) if True else None
    if not isinstance(d, dict):
        print(json.dumps({"ok": False, "errors": ["顶层必须是对象"]}, ensure_ascii=False)); return 1
    errs = []
    for k in ("case_id", "status", "manuscript_version", "issues", "checked_scope",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    if not d.get("manuscript_version"):
        errs.append("manuscript_version 为空(必须记录稿件版本才能复核)")
    for i, it in enumerate(d.get("issues", [])):
        for k in ("id", "category", "severity", "location", "quote", "claim", "fix"):
            if k not in it:
                errs.append("issues[%d] 缺 %s" % (i, k))
        if it.get("category") not in CATS:
            errs.append("issues[%d] category 非法: %s" % (i, it.get("category")))
        if it.get("severity") not in SEV:
            errs.append("issues[%d] severity 非法: %s" % (i, it.get("severity")))
    if not d.get("checked_scope"):
        errs.append("checked_scope 为空(须写明查了哪些检查项、哪些未查)")
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "issues": len(d.get("issues", []))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "verify":
        tp = a[a.index("--text") + 1] if "--text" in a else None
        sys.exit(cmd_verify(a[1], tp))
    if a[0] == "summary":
        sys.exit(cmd_summary(a[1]))
    if a[0] == "logic_check":
        tp = a[a.index("--text") + 1] if "--text" in a else None
        sys.exit(cmd_logic_check(a[1], tp))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
