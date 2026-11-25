#!/usr/bin/env python3
"""学术格式与模板适配补强：模板反推检查项 / 图表与交叉引用联动核验 / 转换保真度比对。纯标准库。

  reverse  <template.txt> [--out checks.json]   从模板文本抽取格式要求 -> 结构化检查项清单
  xcheck   <doc.json>                          图表编号与正文交叉引用一致性（编号/题注/引用三对齐）
  fidelity <before.json> <after.json>          转换前后内容单元(公式/脚注/题注/域)保真度比对，丢失即报错
"""
import json, re, sys


def _load(p):
    return json.load(open(p, encoding="utf-8"))


def cmd_reverse(path, out=None):
    try:
        txt = open(path, encoding="utf-8", errors="replace").read()
    except Exception as e:
        print(json.dumps({"ok": False, "error": "模板读取失败: %s" % e}, ensure_ascii=False)); return 1
    checks = []
    RULES = [
        (r"(摘要|abstract)", "abstract", "摘要结构"),
        (r"(关键词|关键字|key ?words?)", "keywords", "关键词"),
        (r"(一级标题|第[一二三]级标题|标题层级|heading)", "heading", "标题层级与编号"),
        (r"(三线表|three[- ]line)", "three_line_table", "三线表"),
        (r"(图注|图题|表注|表题|caption)", "caption", "图表题注"),
        (r"(页边距|margin)", "margins", "页边距"),
        (r"(行距|line[- ]spacing|倍行距)", "line_spacing", "行距"),
        (r"(页码|page number)", "page_number", "页码"),
        (r"(目录|table of contents)", "toc", "目录"),
        (r"(参考文献|references|bibliography)", "references", "参考文献样式"),
        (r"(字体|font|宋体|黑体|Times)", "font", "字体字号"),
        (r"(页眉|页脚|header|footer)", "header_footer", "页眉页脚"),
    ]
    for pat, key, label in RULES:
        m = re.search(pat, txt, re.I)
        if m:
            seg = txt[max(0, m.start() - 40): m.end() + 80].replace("\n", " ")
            checks.append({"key": key, "label": label, "evidence": seg[:120], "status": "to_verify"})
    out_obj = {"ok": True, "template": path, "n_requirements": len(checks), "requirements": checks}
    if not checks:
        out_obj["ok"] = False
        out_obj["note"] = "未从模板抽取到格式要求（模板可能无文本层或非规范模板）"
    text = json.dumps(out_obj, ensure_ascii=False, indent=1)
    if out:
        open(out, "w", encoding="utf-8").write(text + "\n")
    print(text)
    return 0 if out_obj["ok"] else 1


def cmd_xcheck(path):
    d = _load(path)
    figs = d.get("figures", [])
    refs = d.get("cross_refs", [])
    errs = []
    numbers = set()
    for f in figs:
        n = f.get("number")
        if not n:
            errs.append("figure 缺编号: %s" % str(f)[:40]); continue
        if n in numbers:
            errs.append("图表编号重复: %s" % n)
        numbers.add(n)
        if not f.get("caption"):
            errs.append("图 %s 缺题注" % n)
    for r in refs:
        tgt = r.get("target_number")
        if tgt and tgt not in numbers:
            errs.append("正文交叉引用指向不存在的图表 %s（编号变引用未同步）" % tgt)
    out = {"ok": not errs, "figures": len(figs), "cross_refs": len(refs), "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


def cmd_fidelity(before, after):
    b, a = _load(before), _load(after)
    KINDS = ("formulas", "footnotes", "captions", "field_codes", "annotations")
    errs, report = [], {}
    for k in KINDS:
        nb, na = len(b.get(k, [])), len(a.get(k, []))
        report[k] = {"before": nb, "after": na}
        if na < nb:
            lost = [x for x in b.get(k, []) if x not in a.get(k, [])]
            errs.append("%s 转换丢失 %d 个: %s" % (k, nb - na, str(lost)[:120]))
    out = {"ok": not errs, "units": report, "errors": errs}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if not errs else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "reverse":
        out = a[a.index("--out") + 1] if "--out" in a else None
        sys.exit(cmd_reverse(a[1], out))
    if a[0] == "xcheck":
        sys.exit(cmd_xcheck(a[1]))
    if a[0] == "fidelity":
        if len(a) < 3:
            print(json.dumps({"ok": False, "error": "fidelity 需要 before/after 两个文件"}, ensure_ascii=False)); sys.exit(2)
        sys.exit(cmd_fidelity(a[1], a[2]))
    print(__doc__); sys.exit(2)
