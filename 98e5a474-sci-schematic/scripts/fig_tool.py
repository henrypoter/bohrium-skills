#!/usr/bin/env python3
"""科研绘图工具：SVG 结构与可编辑性核验 + 元素-数据映射 + 交付校验。纯标准库。

  svg_check <file.svg>        解析 SVG：尺寸、元素计数、文本是否可编辑(未转曲)、是否疑似空图
  element_map <mapping.json>  每个视觉元素是否映射到来源数据/材料
  schema <result.json>        交付契约校验
"""
import json, sys, xml.etree.ElementTree as ET

SVGNS = "{http://www.w3.org/2000/svg}"

def _strip(tag):
    return tag.split("}")[-1]

def cmd_svg_check(path):
    try:
        tree = ET.parse(path)
    except Exception as e:
        print(json.dumps({"ok": False, "error": "SVG 解析失败: %s" % e}, ensure_ascii=False)); return 1
    root = tree.getroot()
    counts = {}
    text_chars = 0
    for el in root.iter():
        t = _strip(el.tag)
        counts[t] = counts.get(t, 0) + 1
        if t == "text":
            text_chars += len("".join(el.itertext()).strip())
    w, h = root.get("width"), root.get("height")
    vb = root.get("viewBox")
    errs, warn = [], []
    n_text = counts.get("text", 0)
    n_path = counts.get("path", 0)
    if n_text == 0 and n_path > 10:
        errs.append("无 <text> 元素但有 %d 个 path：文字疑似已转曲，不可编辑" % n_path)
    if n_text > 0 and text_chars == 0:
        warn.append("<text> 元素存在但无文字内容")
    if not (w and h) and not vb:
        errs.append("缺 width/height 且无 viewBox，尺寸不可知")
    n_img = counts.get("image", 0)
    if n_img > 0:
        warn.append("含 %d 个位图 <image>，注意可编辑性与来源" % n_img)
    total = sum(counts.values())
    if total < 3:
        errs.append("元素过少(%d)，疑似空图" % total)
    print(json.dumps({"ok": not errs, "width": w, "height": h, "viewBox": vb,
                      "elements": counts, "text_elements": n_text, "text_chars": text_chars,
                      "errors": errs, "warnings": warn}, ensure_ascii=False))
    return 0 if not errs else 1

def cmd_element_map(path):
    d = json.load(open(path, encoding="utf-8"))
    mapping = d.get("mapping", [])
    errs, unmapped = [], []
    for i, m in enumerate(mapping):
        if not m.get("element") or not m.get("source"):
            unmapped.append(m.get("element") or "mapping[%d]" % i)
        if not m.get("source_location"):
            errs.append("mapping[%d] 缺 source_location(来源定位)" % i)
    print(json.dumps({"ok": not errs and not unmapped, "n_elements": len(mapping),
                      "unmapped_elements": unmapped, "errors": errs}, ensure_ascii=False))
    return 0 if not errs and not unmapped else 1

def cmd_schema(path):
    d = json.load(open(path, encoding="utf-8"))
    errs = []
    for k in ("case_id", "status", "figure_version", "figures", "mapping",
              "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if k not in d:
            errs.append("缺顶层字段 %s" % k)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errs.append("status 非法")
    for i, f in enumerate(d.get("figures", [])):
        for k in ("id", "svg", "png", "figure_type"):
            if k not in f:
                errs.append("figures[%d] 缺 %s(须同时给可编辑 SVG 源与渲染 PNG)" % (i, k))
    if errs:
        print(json.dumps({"ok": False, "errors": errs}, ensure_ascii=False)); return 1
    print(json.dumps({"ok": True, "figures": len(d.get("figures", []))}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__); sys.exit(2)
    if a[0] == "svg_check":
        sys.exit(cmd_svg_check(a[1]))
    if a[0] == "element_map":
        sys.exit(cmd_element_map(a[1]))
    if a[0] == "schema":
        sys.exit(cmd_schema(a[1]))
    print(__doc__); sys.exit(2)
