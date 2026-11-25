#!/usr/bin/env python3
"""科研文件智能检索（仅 Python 标准库；可选调用系统已有解析器）。

命令：
  inventory ROOT [--output FILE]
  index ROOT --output INDEX.json [--metadata META.json] [--aliases ALIAS.json] [--ocr]
  search INDEX.json --query TEXT [--filters FILTERS.json] [--output FILE] [--limit N]
  verify RESULT.json --index INDEX.json [--root ROOT]
  schema RESULT.json [--index INDEX.json] [--root ROOT]
  compare --baseline BASE.json --skill SKILL.json --index INDEX.json [--gold GOLD.json] [--output FILE]

索引保存原文块、物理页/印刷页、章节、段落、Office 行列/幻灯片定位和内容哈希。
外部解析器不是 Python 包依赖：PDF 优先使用 pdftotext；无解析器或扫描件会明确
标记，不会伪造文本。所有过滤条件均为硬约束，缺元数据即排除并列入 coverage_gaps。
"""
import argparse
import csv
import datetime as _dt
import hashlib
import html
import io
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET

SCHEMA_VERSION = "research-retrieval-index-v1"
TEXT_EXT = {".txt", ".md", ".rst", ".log", ".yaml", ".yml", ".json", ".xml",
            ".html", ".htm", ".py", ".sql", ".tex", ".bib", ".csv", ".tsv"}
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_+.-]*|[\u4e00-\u9fff]+|\d+(?:\.\d+)*")
HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+|第[一二三四五六七八九十百0-9]+[章节篇]\s*|"
    r"\d+(?:\.\d+){0,4}\s+\S|(?:abstract|introduction|methods?|materials?\s+and\s+methods?|"
    r"results?|discussion|conclusions?|references|appendix|supplementary\s+materials?)\b|"
    r"(?:摘要|引言|绪论|材料与方法|实验方法|方法|结果|讨论|结论|参考文献|附录|补充材料)\s*$)", re.I)
PAGE_RE = re.compile(r"^(?:page\s*)?(\d{1,4}|[ivxlcdm]+)(?:\s*/\s*\d+)?$|^第\s*(\d{1,4})\s*页$", re.I)
BUILTIN_GROUPS = [
    ["buffer", "buffer solution", "缓冲液", "缓冲溶液"],
    ["recipe", "formulation", "composition", "配方", "组成"],
    ["flow cytometry", "FACS", "流式细胞术", "流式细胞分析"],
    ["mass spectrometry", "MS", "质谱"],
    ["polymerase chain reaction", "PCR", "聚合酶链式反应"],
    ["centrifuge", "centrifugation", "离心", "离心机"],
    ["incubation", "incubate", "孵育", "温育"],
    ["dataset", "data set", "数据集"],
    ["figure", "fig.", "图", "图件"],
    ["table", "表", "表格"],
    ["supplementary", "supplemental", "补充材料", "补充资料"],
    ["project", "project id", "项目", "项目编号"],
    ["batch", "experiment batch", "实验批次", "批次"],
    ["version", "revision", "版本", "修订版"],
]
STOPWORDS = {"the", "a", "an", "of", "in", "on", "for", "and", "or", "to", "which",
             "what", "where", "is", "are", "was", "were", "with", "that", "this", "请",
             "查找", "检索", "哪个", "哪一", "什么", "哪里", "对应", "请问", "的", "了", "在"}


def utcnow():
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(obj, path=None):
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if path:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        os.replace(tmp, path)
    return text


def emit(obj, output=None, rc=0):
    print(save_json(obj, output))
    return rc


def norm_path(path):
    return path.replace("\\", "/").lstrip("./")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_text(path):
    raw = open(path, "rb").read()
    if b"\x00" in raw[:4096]:
        raise ValueError("二进制 NUL 字节，不能按文本解析")
    for enc in ("utf-8-sig", "gb18030", "big5"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    return raw.decode("latin-1"), "latin-1"


def natural_key(s):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def safe_relpath(path, root):
    return norm_path(os.path.relpath(path, root))


def inventory_scan(root):
    root = os.path.abspath(root)
    out = {"schema_version": SCHEMA_VERSION, "root": root, "created_at": utcnow(),
           "files": [], "duplicate_groups": [], "anomalies": [], "empty_files": [],
           "by_ext": {}, "file_count": 0, "readable_file_count": 0, "total_bytes": 0}
    if not os.path.isdir(root):
        out["anomalies"].append({"path": root, "status": "path_invalid", "action": "检查挂载与大小写；不创建假清单"})
        return out
    by_hash = {}
    for current, dirs, names in os.walk(root, followlinks=False):
        kept = []
        for d in sorted(dirs):
            p = os.path.join(current, d)
            if os.path.islink(p):
                out["anomalies"].append({"path": safe_relpath(p, root), "status": "symlink",
                                         "action": "不跟随；登记真实目标后由用户确认授权"})
            else:
                kept.append(d)
        dirs[:] = kept
        for name in sorted(names):
            p = os.path.join(current, name)
            rel = safe_relpath(p, root)
            ext = os.path.splitext(name)[1].lower()
            out["by_ext"][ext or "[none]"] = out["by_ext"].get(ext or "[none]", 0) + 1
            row = {"path": rel, "ext": ext, "type": ext.lstrip("."), "size": None,
                   "sha256": None, "status": "unknown", "readable": False}
            if os.path.islink(p):
                row["status"] = "symlink"
                row["recovery"] = "不跟随软链；确认目标和权限后重新入库"
                out["anomalies"].append(row.copy())
                out["files"].append(row)
                continue
            try:
                st = os.stat(p)
                row["size"] = st.st_size
                row["mode"] = stat.filemode(st.st_mode)
                row["sha256"] = sha256_file(p)
                row["readable"] = True
                row["status"] = "empty" if st.st_size == 0 else "readable"
                out["readable_file_count"] += 1
                out["total_bytes"] += st.st_size
                if st.st_size == 0:
                    out["empty_files"].append(rel)
                else:
                    by_hash.setdefault(row["sha256"], []).append(rel)
            except PermissionError as e:
                row["status"] = "permission_denied"
                row["error"] = str(e)
                row["recovery"] = "保持 blocked；申请只读权限后重跑 inventory/index"
                out["anomalies"].append(row.copy())
            except OSError as e:
                row["status"] = "read_failed"
                row["error"] = str(e)
                row["recovery"] = "保留原路径；修复挂载或重新采集后按哈希复核"
                out["anomalies"].append(row.copy())
            out["files"].append(row)
    out["files"].sort(key=lambda x: natural_key(x["path"]))
    for h, paths in sorted(by_hash.items()):
        if len(paths) > 1:
            paths = sorted(paths, key=natural_key)
            out["duplicate_groups"].append({"sha256": h, "canonical": paths[0],
                                            "files": paths, "independent_evidence_count": 1,
                                            "rule": "仅内容完全相同；副本不是独立证据"})
    out["file_count"] = len(out["files"])
    return out


def cmd_inventory(args):
    out = inventory_scan(args.root)
    ok = not any(a.get("status") in {"path_invalid", "permission_denied", "read_failed"} for a in out["anomalies"])
    out["ok"] = ok
    return emit(out, args.output, 0 if ok else 1)


def load_metadata(path):
    if not path:
        return {}, []
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            data = list(csv.DictReader(f))
    else:
        data = load_json(path)
    rows = data.get("files", data) if isinstance(data, dict) else data
    result, errors = {}, []
    if isinstance(rows, dict):
        rows = [dict(v, path=k) if isinstance(v, dict) else {"path": k, "value": v}
                for k, v in rows.items()]
    if not isinstance(rows, list):
        raise ValueError("metadata 必须是 files 数组或 path→元数据对象")
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or not row.get("path"):
            errors.append("metadata[%d] 缺 path" % i)
            continue
        p = norm_path(str(row["path"]))
        if p in result:
            errors.append("metadata 重复路径: " + p)
        result[p] = {k: v for k, v in row.items() if k != "path"}
    return result, errors


def load_alias_groups(path=None):
    groups = [list(x) for x in BUILTIN_GROUPS]
    field_aliases = {"年份": "year", "年度": "year", "项目编号": "project", "项目": "project",
                     "文件类型": "type", "实验批次": "batch", "批次": "batch", "版本": "version",
                     "权限": "permission", "路径": "path", "章节": "section"}
    if path:
        d = load_json(path)
        for group in d.get("groups", []):
            if isinstance(group, list) and len(group) >= 2:
                groups.append([str(x) for x in group])
        field_aliases.update({str(k): str(v) for k, v in d.get("field_aliases", {}).items()})
    # 去重但保留配置顺序；同义组只扩展检索词，不改变过滤值。
    unique, seen = [], set()
    for g in groups:
        key = tuple(sorted(x.casefold() for x in g))
        if key not in seen:
            unique.append(g)
            seen.add(key)
    return unique, field_aliases


def printed_page_label(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for line in (lines[:3] + lines[-3:]):
        m = PAGE_RE.match(line)
        if m:
            return m.group(1) or m.group(2)
    return None


def first_sentence(text):
    s = text.strip()
    m = re.search(r"(?<=[。！？!?])\s|(?<=[.!?])\s+|\n", s)
    return s[:m.start()].strip() if m else s[:240].strip()


def source_uri(path, locator):
    quoted = urllib.parse.quote(norm_path(path), safe="/")
    frag = []
    if locator.get("page") is not None:
        frag.append("page=%s" % locator["page"])
    if locator.get("slide") is not None:
        frag.append("slide=%s" % locator["slide"])
    if locator.get("sheet"):
        frag.append("sheet=" + urllib.parse.quote(str(locator["sheet"])))
    if locator.get("row") is not None:
        frag.append("row=%s" % locator["row"])
    if locator.get("block_id"):
        frag.append("block=" + urllib.parse.quote(str(locator["block_id"])))
    return quoted + ("#" + "&".join(frag) if frag else "")


def make_blocks(text, path, file_index, page=None, printed_page=None, start_index=0,
                section_hint="", kind="paragraph"):
    """切为可逐字复核的小块；不改写块内文字。返回 (blocks, next_index, section)。"""
    blocks = []
    section = section_hint
    paragraph = 0
    # 保留原始换行；按空行切块，长块只在换行处切，避免整篇命中。
    chunks = []
    for part in re.split(r"(\n\s*\n)", text):
        if not part or not part.strip():
            continue
        if re.fullmatch(r"\n\s*\n", part):
            continue
        lines = part.splitlines()
        buf, size = [], 0
        for line in lines:
            if buf and (HEADING_RE.match(line.strip()) or size + len(line) > 3500):
                chunks.append("\n".join(buf))
                buf, size = [], 0
            buf.append(line)
            size += len(line) + 1
        if buf:
            chunks.append("\n".join(buf))
    for chunk in chunks:
        raw = chunk.strip()
        if not raw:
            continue
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
        is_heading = len(lines) == 1 and len(lines[0]) <= 180 and bool(HEADING_RE.match(lines[0]))
        if is_heading:
            section = re.sub(r"^#{1,6}\s*", "", lines[0]).strip()
        paragraph += 1
        low = raw.lstrip().lower()
        block_kind = kind
        if re.match(r"^(fig(?:ure)?\.?\s*\d+|图\s*\d+)", low):
            block_kind = "figure_caption"
        elif re.match(r"^(table\s*\d+|表\s*\d+)", low):
            block_kind = "table_or_caption"
        bid = "f%d:b%d" % (file_index, start_index + len(blocks))
        locator = {"kind": "pdf_page_paragraph" if page is not None else "text_paragraph",
                   "page": page, "printed_page": printed_page, "section": section or None,
                   "paragraph": paragraph, "block_id": bid}
        blocks.append({"block_id": bid, "path": path, "text": raw, "kind": block_kind,
                       "section": section or None, "locator": locator,
                       "paragraph_first_sentence": first_sentence(raw)})
    return blocks, start_index + len(blocks), section


def extract_plain(path, rel, fi):
    text, encoding = read_text(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in {".csv", ".tsv"}:
        delim = "\t" if ext == ".tsv" else ","
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
        blocks = []
        headers = rows[0] if rows else []
        for ri, row in enumerate(rows[1:] if headers else rows, start=2 if headers else 1):
            vals = ["%s=%s" % (headers[i] if i < len(headers) else "col%d" % (i + 1), v)
                    for i, v in enumerate(row)]
            raw = " | ".join(vals)
            bid = "f%d:b%d" % (fi, len(blocks))
            loc = {"kind": "table_row", "row": ri, "page": None, "printed_page": None,
                   "section": None, "block_id": bid}
            blocks.append({"block_id": bid, "path": rel, "text": raw, "kind": "table_row",
                           "section": None, "locator": loc, "paragraph_first_sentence": first_sentence(raw),
                           "row_metadata": {headers[i]: v for i, v in enumerate(row) if i < len(headers)}})
        return blocks, "delimited-text", "indexed"
    if ext in {".html", ".htm"}:
        # 只去标签用于检索；原文引用对应解析文本，不声称对应渲染页码。
        text = re.sub(r"(?is)<(script|style).*?</\1>", "", text)
        text = re.sub(r"(?i)</(?:p|div|h[1-6]|tr|li)>", "\n\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
    blocks, _, _ = make_blocks(text, rel, fi)
    return blocks, "text/" + encoding, "indexed"


def run_command(cmd, timeout=90):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)


def extract_pdf(path, rel, fi, ocr=False):
    exe = shutil.which("pdftotext")
    if not exe:
        return [], "none", "parser_unavailable", "缺少 pdftotext；安装系统解析器后重跑，不把 PDF 当纯文本"
    cmd = [exe, "-layout", "-enc", "UTF-8"]
    if not ocr:
        cmd.append("-nopgbrk") if False else None  # 始终保留物理页分隔符。
    cmd.extend([path, "-"])
    try:
        r = run_command(cmd)
    except subprocess.TimeoutExpired:
        return [], "pdftotext", "extraction_timeout", "缩小批次或延长解析时间后重跑"
    if r.returncode != 0:
        err = r.stderr.decode("utf-8", "replace").strip()
        status = "encrypted" if re.search(r"password|encrypted|incorrect", err, re.I) else "corrupt_or_unreadable"
        return [], "pdftotext", status, err[:500]
    text = r.stdout.decode("utf-8", "replace")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if not any(p.strip() for p in pages):
        return [], "pdftotext", "needs_ocr", "PDF 无文本层；授权 OCR 后重跑，不能凭文件名回答"
    blocks, bi, section = [], 0, ""
    for page, content in enumerate(pages, start=1):
        label = printed_page_label(content)
        made, bi, section = make_blocks(content, rel, fi, page, label, bi, section)
        if made and blocks and made[0]["kind"] == "table_or_caption" and blocks[-1]["kind"] == "table_or_caption":
            made[0]["continuation_of"] = blocks[-1]["block_id"]
        blocks.extend(made)
    return blocks, "pdftotext-layout", "indexed", None


def xml_text(el, ns):
    parts = []
    for node in el.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "t" and node.text:
            parts.append(node.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
    return "".join(parts)


def new_office_block(rel, fi, bi, text, kind, locator, section=None, row_metadata=None):
    bid = "f%d:b%d" % (fi, bi)
    locator = dict(locator)
    locator.update({"kind": kind, "block_id": bid, "page": None, "printed_page": None})
    b = {"block_id": bid, "path": rel, "text": text.strip(), "kind": kind,
         "section": section, "locator": locator, "paragraph_first_sentence": first_sentence(text)}
    if row_metadata:
        b["row_metadata"] = row_metadata
    return b


def extract_docx(path, rel, fi):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    blocks = []
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        body = root.find("w:body", ns)
        para_no, table_no, section = 0, 0, None
        children = list(body) if body is not None else list(root)
        for child in children:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                text = xml_text(child, ns).strip()
                if not text:
                    continue
                para_no += 1
                style_el = child.find("w:pPr/w:pStyle", ns)
                style = style_el.get("{%s}val" % ns["w"], "") if style_el is not None else ""
                if re.search(r"heading|标题|title", style, re.I) or HEADING_RE.match(text):
                    section = re.sub(r"^#{1,6}\s*", "", text)
                blocks.append(new_office_block(rel, fi, len(blocks), text, "docx_paragraph",
                                               {"paragraph": para_no, "section": section}, section))
            elif tag == "tbl":
                table_no += 1
                for ri, tr in enumerate(child.findall("w:tr", ns), start=1):
                    cells = [xml_text(tc, ns).strip() for tc in tr.findall("w:tc", ns)]
                    text = " | ".join("C%d=%s" % (ci, value) for ci, value in enumerate(cells, start=1))
                    if text.strip(" |C0123456789="):
                        blocks.append(new_office_block(rel, fi, len(blocks), text, "docx_table_row",
                                                       {"table": table_no, "row": ri, "section": section}, section))
        # 页眉页脚、脚注也入库并标明来源，避免遗漏缓冲液等关键条件。
        for name in sorted(n for n in z.namelist() if re.match(r"word/(?:header\d+|footer\d+|footnotes|endnotes)\.xml$", n)):
            x = ET.fromstring(z.read(name))
            for pi, p in enumerate(x.findall(".//w:p", ns), start=1):
                text = xml_text(p, ns).strip()
                if text:
                    blocks.append(new_office_block(rel, fi, len(blocks), text, "docx_auxiliary",
                                                   {"part": name, "paragraph": pi}, section))
    return blocks, "ooxml-docx", "indexed", None


def extract_pptx(path, rel, fi):
    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
    blocks = []
    with zipfile.ZipFile(path) as z:
        slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                        key=natural_key)
        for name in slides:
            slide = int(re.search(r"slide(\d+)\.xml$", name).group(1))
            root = ET.fromstring(z.read(name))
            for si, shape in enumerate(root.findall(".//{*}sp") + root.findall(".//{*}graphicFrame"), start=1):
                for pi, p in enumerate(shape.findall(".//a:p", ns), start=1):
                    text = xml_text(p, ns).strip()
                    if text:
                        blocks.append(new_office_block(rel, fi, len(blocks), text, "pptx_slide_paragraph",
                                                       {"slide": slide, "shape": si, "paragraph": pi}))
        notes = sorted((n for n in z.namelist() if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", n)),
                       key=natural_key)
        for name in notes:
            note_no = int(re.search(r"notesSlide(\d+)\.xml$", name).group(1))
            root = ET.fromstring(z.read(name))
            for pi, p in enumerate(root.findall(".//a:p", ns), start=1):
                text = xml_text(p, ns).strip()
                if text:
                    blocks.append(new_office_block(rel, fi, len(blocks), text, "pptx_notes",
                                                   {"slide": note_no, "paragraph": pi, "part": name}))
    return blocks, "ooxml-pptx", "indexed", None


def extract_xlsx(path, rel, fi):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    blocks = []
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.findall(".//m:t", ns)) for si in root.findall("m:si", ns)]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.get("Id"): r.get("Target") for r in rels}
        for sheet in wb.findall("m:sheets/m:sheet", ns):
            name = sheet.get("name", "Sheet")
            rid = sheet.get("{%s}id" % ns["r"])
            target = relmap.get(rid, "")
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("./")
            target = os.path.normpath(target).replace("\\", "/")
            if target not in z.namelist():
                continue
            root = ET.fromstring(z.read(target))
            headers = {}
            for row in root.findall(".//m:sheetData/m:row", ns):
                ri = int(row.get("r", len(blocks) + 1))
                values, row_meta = [], {}
                for c in row.findall("m:c", ns):
                    ref = c.get("r", "")
                    typ = c.get("t")
                    if typ == "inlineStr":
                        value = "".join(t.text or "" for t in c.findall(".//m:t", ns))
                    else:
                        v = c.find("m:v", ns)
                        value = "" if v is None or v.text is None else v.text
                        if typ == "s" and value:
                            try:
                                value = shared[int(value)]
                            except (ValueError, IndexError):
                                value = "[invalid shared string]"
                    col_match = re.match(r"[A-Z]+", ref)
                    column = col_match.group(0) if col_match else ref
                    if not headers:
                        row_meta[column] = value
                    else:
                        header = headers.get(column, column)
                        row_meta[header] = value
                    label = headers.get(column) if headers else None
                    values.append("%s%s=%s" % (ref, ":" + label if label else "", value))
                if not headers:
                    headers = dict(row_meta)
                text = " | ".join(values)
                if text.strip():
                    blocks.append(new_office_block(rel, fi, len(blocks), text, "xlsx_row",
                                                   {"sheet": name, "row": ri}, name, row_meta))
    return blocks, "ooxml-xlsx", "indexed", None


def extract_image_ocr(path, rel, fi, enabled):
    if not enabled:
        return [], "none", "needs_ocr", "图片无直接文本层；使用 --ocr 且系统有 tesseract 时才识别"
    exe = shutil.which("tesseract")
    if not exe:
        return [], "none", "needs_ocr", "缺少 tesseract；安装 OCR 后重跑"
    try:
        r = run_command([exe, path, "stdout", "-l", "eng+chi_sim"], timeout=120)
    except subprocess.TimeoutExpired:
        return [], "tesseract", "extraction_timeout", "OCR 超时；降低分辨率或分批处理"
    if r.returncode:
        return [], "tesseract", "ocr_failed", r.stderr.decode("utf-8", "replace")[:500]
    text = r.stdout.decode("utf-8", "replace")
    blocks, _, _ = make_blocks(text, rel, fi, page=1, printed_page="1")
    for b in blocks:
        b["ocr"] = True
    return blocks, "tesseract", "ocr_needs_review", "OCR 文本须与图像逐字复核"


def extract_file(path, rel, fi, ocr=False):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in TEXT_EXT:
            b, parser, status = extract_plain(path, rel, fi)
            return b, parser, status, None
        if ext == ".pdf":
            return extract_pdf(path, rel, fi, ocr)
        if ext == ".docx":
            return extract_docx(path, rel, fi)
        if ext == ".pptx":
            return extract_pptx(path, rel, fi)
        if ext == ".xlsx":
            return extract_xlsx(path, rel, fi)
        if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            return extract_image_ocr(path, rel, fi, ocr)
        if ext in {".doc", ".xls", ".ppt"}:
            return [], "none", "legacy_office_unsupported", "先用授权 Office/LibreOffice 转为 OOXML，保留原哈希与转换记录"
        return [], "none", "unsupported", "登记文件与哈希；增加受支持解析器后重跑，不猜测内容"
    except PermissionError as e:
        return [], "none", "permission_denied", str(e)
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, OSError) as e:
        return [], "none", "corrupt_or_unreadable", "%s: %s" % (type(e).__name__, str(e)[:400])


VERSION_TOKEN_RE = re.compile(r"(?i)(?:[_\-\s]?(?:v|ver|rev|final|draft|copy|副本|终稿|草稿)\d*|[_\-\s]?\(\d+\))$")


def version_relations(files):
    candidates, declared = {}, {}
    for f in files:
        stem = os.path.splitext(os.path.basename(f["path"]))[0]
        base = stem
        while True:
            new = VERSION_TOKEN_RE.sub("", base).strip(" _-")
            if new == base:
                break
            base = new
        candidates.setdefault(base.casefold(), []).append(f["path"])
        md = f.get("metadata", {})
        group = md.get("version_group", md.get("document_id"))
        if group:
            declared.setdefault(str(group), []).append(f)
    candidate_rows = [{"base": k, "files": sorted(v, key=natural_key), "relation": "candidate_only",
                       "current": None, "evidence": ["仅规范化文件名；不是替代/当前版本结论"]}
                      for k, v in candidates.items() if len(v) > 1]
    declared_rows = []
    for group, rows in declared.items():
        current = [f["path"] for f in rows if scalar_eq(f["metadata"].get("current"), True)]
        relations = []
        for f in rows:
            md = f["metadata"]
            if md.get("supersedes"):
                relations.append({"from": f["path"], "relation": "supersedes", "to": md["supersedes"]})
            if md.get("superseded_by"):
                relations.append({"from": f["path"], "relation": "superseded_by", "to": md["superseded_by"]})
        declared_rows.append({"group": group, "files": [f["path"] for f in rows],
                              "current": current[0] if len(current) == 1 else None,
                              "relations": relations,
                              "evidence": ["metadata:version_group/current/supersedes"],
                              "uncertainty": None if len(current) == 1 else "当前版本未由元数据唯一声明"})
    return candidate_rows, declared_rows


def cmd_index(args):
    inv = inventory_scan(args.root)
    metadata, metadata_errors = load_metadata(args.metadata)
    groups, field_aliases = load_alias_groups(args.aliases)
    files, blocks, warnings = [], [], []
    for fi, f in enumerate(inv["files"]):
        row = dict(f)
        row["metadata"] = metadata.get(f["path"], {})
        abs_path = os.path.join(os.path.abspath(args.root), f["path"])
        if f["status"] == "readable":
            made, parser, status, warning = extract_file(abs_path, f["path"], fi, args.ocr)
            row["parser"] = parser
            row["status"] = status
            row["block_count"] = len(made)
            if warning:
                row["warning"] = warning
                warnings.append({"path": f["path"], "status": status, "recovery": warning})
            for b in made:
                b["sha256"] = f["sha256"]
                b["metadata"] = row["metadata"]
                b["version"] = row["metadata"].get("version", row["metadata"].get("版本"))
                blocks.append(b)
        else:
            row["block_count"] = 0
        files.append(row)
    # 同哈希只算一个独立证据；不删除副本路径，保证按路径过滤仍可复核。
    by_hash = {}
    for f in files:
        if f.get("sha256"):
            by_hash.setdefault(f["sha256"], []).append(f["path"])
    for h, paths in by_hash.items():
        if len(paths) > 1:
            canonical = sorted(paths, key=natural_key)[0]
            for f in files:
                if f["path"] in paths:
                    f["duplicate_of"] = canonical if f["path"] != canonical else None
                    f["duplicate_aliases"] = sorted(paths, key=natural_key)
                    f["independent_evidence_id"] = h
    candidates, declared_versions = version_relations(files)
    out = dict(inv)
    out.update({"files": files, "blocks": blocks, "metadata_errors": metadata_errors,
                "version_candidates": candidates, "version_groups": declared_versions,
                "alias_groups": groups, "field_aliases": field_aliases,
                "indexed_block_count": len(blocks), "warnings": warnings,
                "metadata_source": os.path.abspath(args.metadata) if args.metadata else None})
    out["index_status"] = "issues" if warnings or metadata_errors or inv["anomalies"] else "ok"
    invalid = any(a.get("status") == "path_invalid" for a in inv["anomalies"])
    return emit(out, args.output, 1 if invalid else 0)


def field_value(item, key, field_aliases=None):
    key = field_aliases.get(key, key) if field_aliases else key
    md = item.get("metadata", {}) or {}
    if key in item and key not in {"metadata", "text", "blocks"}:
        return item[key]
    if key in md:
        return md[key]
    # 元数据键大小写不敏感，但不过度猜字段。
    for k, v in md.items():
        if str(k).casefold() == str(key).casefold():
            return v
    rowmd = item.get("row_metadata", {}) or {}
    if key in rowmd:
        return rowmd[key]
    if key == "section":
        return item.get("section")
    return None


def scalar_eq(actual, expected):
    if actual is None:
        return False
    if isinstance(actual, list):
        return any(scalar_eq(x, expected) for x in actual)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected or str(actual).lower() == str(expected).lower()
    if isinstance(actual, (int, float)) or isinstance(expected, (int, float)):
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            pass
    return str(actual).casefold() == str(expected).casefold()


def match_condition(actual, cond):
    if isinstance(cond, dict):
        for op, expected in cond.items():
            if op == "exists":
                if (actual is not None) != bool(expected):
                    return False
            elif op == "eq" and not scalar_eq(actual, expected):
                return False
            elif op == "ne" and scalar_eq(actual, expected):
                return False
            elif op == "in" and not any(scalar_eq(actual, x) for x in expected):
                return False
            elif op == "contains":
                if actual is None:
                    return False
                values = expected if isinstance(expected, list) else [expected]
                if isinstance(actual, list):
                    if not all(any(scalar_eq(a, e) for a in actual) for e in values):
                        return False
                elif not all(str(e).casefold() in str(actual).casefold() for e in values):
                    return False
            elif op in {"gte", "lte", "gt", "lt"}:
                try:
                    a, e = float(actual), float(expected)
                except (TypeError, ValueError):
                    return False
                if not {"gte": a >= e, "lte": a <= e, "gt": a > e, "lt": a < e}[op]:
                    return False
            elif op == "regex":
                if actual is None or not re.search(str(expected), str(actual), re.I):
                    return False
            else:
                return False
        return True
    if isinstance(cond, list):
        return any(scalar_eq(actual, x) for x in cond)
    return scalar_eq(actual, cond)


def check_filters(item, filters, field_aliases):
    violations, missing = [], []
    for key, cond in (filters or {}).items():
        if key.startswith("$"):
            # $and 中的每个条件仍须全部满足；不支持会悄悄放宽条件的 $or。
            if key == "$and" and isinstance(cond, list):
                for sub in cond:
                    v, m = check_filters(item, sub, field_aliases)
                    violations.extend(v)
                    missing.extend(m)
            else:
                violations.append({"field": key, "reason": "unsupported_operator"})
            continue
        actual = field_value(item, key, field_aliases)
        if actual is None and not (isinstance(cond, dict) and "exists" in cond):
            missing.append(key)
        if not match_condition(actual, cond):
            violations.append({"field": key, "expected": cond, "actual": actual})
    return violations, missing


def query_concepts(query, groups):
    q = query.casefold()
    concepts = []
    for group in groups:
        if any(x.casefold() in q for x in group):
            original = [x for x in group if x.casefold() in q]
            concepts.append({"original": original, "terms": group, "semantic": True})
    return concepts


def lexical_tokens(text):
    tokens = []
    for m in WORD_RE.finditer(text.casefold()):
        s = m.group(0)
        if s in STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", s):
            if len(s) <= 3 and s not in STOPWORDS:
                tokens.append(s)
            tokens.extend(s[i:i + 2] for i in range(len(s) - 1))
        elif len(s) > 1 or s.isdigit():
            tokens.append(s)
    return tokens


def quote_for_match(text, terms):
    positions = [(text.casefold().find(t.casefold()), t) for t in terms if t and text.casefold().find(t.casefold()) >= 0]
    if not positions or len(text) <= 900:
        return text
    pos = min(p for p, _ in positions)
    start_candidates = [text.rfind(x, 0, pos) for x in ("\n", "。", "！", "？", "! ", "? ")]
    start = max(start_candidates)
    start = 0 if start < 0 else start + 1
    ends = []
    for pattern in ("\n", "。", "！", "？", "! ", "? "):
        p = text.find(pattern, pos + 1)
        if p >= 0:
            ends.append(p + len(pattern))
    end = min(ends) if ends else len(text)
    quote = text[start:end].strip()
    return quote if len(quote) >= 12 else text


def cmd_search(args):
    index = load_json(args.index)
    filters = load_json(args.filters) if args.filters else {}
    if not isinstance(filters, dict):
        return emit({"ok": False, "error": "filters 必须是 JSON 对象；不会自动放宽"}, rc=2)
    groups = index.get("alias_groups") or BUILTIN_GROUPS
    field_aliases = index.get("field_aliases", {})
    concepts = query_concepts(args.query, groups)
    query_tokens = lexical_tokens(args.query)
    files = {f["path"]: f for f in index.get("files", [])}
    candidates, gaps, file_filter_counts = [], [], {}
    for b in index.get("blocks", []):
        f = files.get(b["path"], {})
        merged = dict(f)
        merged.update({k: v for k, v in b.items() if k not in {"metadata"}})
        merged["metadata"] = dict(f.get("metadata", {}))
        # 文件元数据 + 行级字段；行级条件不能越过其他硬过滤。
        for k, v in b.get("row_metadata", {}).items():
            merged["metadata"].setdefault(k, v)
        violations, missing = check_filters(merged, filters, field_aliases)
        if violations:
            for key in missing:
                gaps.append({"path": b["path"], "field": key, "action": "补真实元数据后重跑；未放宽条件"})
            file_filter_counts[b["path"]] = file_filter_counts.get(b["path"], 0) + 1
            continue
        candidates.append((b, merged))
    df = {}
    for b, _ in candidates:
        for t in set(lexical_tokens(b["text"])):
            df[t] = df.get(t, 0) + 1
    n = max(1, len(candidates))
    hits = []
    for b, merged in candidates:
        text_cf = b["text"].casefold()
        score, matched, semantic_matched = 0.0, [], []
        for token in query_tokens:
            if token in text_cf:
                idf = math.log(1 + (n - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5))
                score += max(0.2, idf)
                matched.append(token)
        for concept in concepts:
            originals = [t for t in concept["original"] if t.casefold() in text_cf]
            aliases = [t for t in concept["terms"] if t.casefold() in text_cf and t not in originals]
            if originals:
                score += 8.0 + min(4.0, max(len(x) for x in originals) / 4)
                matched.extend(originals)
            elif aliases:
                score += 5.5
                semantic_matched.extend(aliases[:3])
        if score < args.min_score:
            continue
        terms = matched + semantic_matched + query_tokens
        quote = quote_for_match(b["text"], terms)
        f = files.get(b["path"], {})
        loc = dict(b["locator"])
        hit = {"path": b["path"], "sha256": b["sha256"], "block_id": b["block_id"],
               "version": b.get("version"), "locator": loc, "section": b.get("section"),
               "paragraph_first_sentence": b.get("paragraph_first_sentence"),
               "quote": quote, "source_uri": source_uri(b["path"], loc),
               "score": round(score, 4), "matched_terms": sorted(set(matched)),
               "semantic_matches": sorted(set(semantic_matched)),
               "duplicate_of": f.get("duplicate_of"), "duplicate_aliases": f.get("duplicate_aliases", []),
               "independent_evidence_id": f.get("independent_evidence_id", b["sha256"]),
               "metadata": f.get("metadata", {})}
        hits.append(hit)
    hits.sort(key=lambda h: (-h["score"], natural_key(h["path"]), h["block_id"]))
    # 同一内容哈希 + 同一定位/引文只给一个主命中，副本作为 aliases 保留。
    unique, seen = [], {}
    for h in hits:
        key = (h["independent_evidence_id"], h["quote"], h["locator"].get("page"),
               h["locator"].get("section"), h["locator"].get("row"), h["locator"].get("slide"))
        if key in seen:
            primary = seen[key]
            alias = {"path": h["path"], "source_uri": h["source_uri"], "block_id": h["block_id"]}
            primary.setdefault("copy_aliases", []).append(alias)
        else:
            seen[key] = h
            unique.append(h)
    unique = unique[:args.limit]
    eligible_paths = sorted({b["path"] for b, _ in candidates}, key=natural_key)
    out = {"ok": True, "query": args.query, "filters_applied": filters,
           "hard_filter_policy": "AND；缺字段即排除；不使用 OR 或语义扩展放宽过滤",
           "search_trace": {"indexed_files": len(files), "indexed_blocks": index.get("indexed_block_count", 0),
                            "candidate_blocks_after_filters": len(candidates),
                            "eligible_files_after_filters": eligible_paths,
                            "ranked_hits_before_limit": len(hits), "returned_hits": len(unique)},
           "coverage_gaps": gaps[:200], "hits": unique,
           "independent_evidence_count": len({h["independent_evidence_id"] for h in unique}),
           "uncertainty": []}
    if not unique:
        out["no_hit"] = {"reason": "filters_excluded_all" if not candidates else "no_semantic_or_lexical_match",
                         "action": "核对过滤字段与索引状态；不得改引无关块或自动删过滤条件"}
    if gaps:
        out["uncertainty"].append("部分文件缺过滤元数据，已硬排除并逐条列入 coverage_gaps")
    if concepts:
        out["semantic_expansions"] = concepts
    return emit(out, args.output, 0)


def iter_query_objects(d):
    if isinstance(d, dict) and "hits" in d and ("query" in d or "question" in d):
        yield d
    if isinstance(d, dict):
        for value in d.values():
            yield from iter_query_objects(value)
    elif isinstance(d, list):
        for value in d:
            yield from iter_query_objects(value)


def all_evidence(d):
    evidence = []
    for q in iter_query_objects(d):
        evidence.extend(q.get("hits", []))
    # 允许最终交付采用 results[].evidence，而不是 queries[].hits。
    def walk(x):
        if isinstance(x, dict):
            if "quote" in x and "path" in x:
                evidence.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(d.get("results", []))
    # 按对象 id 去重，避免 hits 被通用遍历重复收集。
    unique, seen = [], set()
    for e in evidence:
        if id(e) not in seen:
            unique.append(e)
            seen.add(id(e))
    return unique


def verify_evidence(evidence, index, root=None):
    errors, checked = [], 0
    files = {f["path"]: f for f in index.get("files", [])}
    blocks = {b["block_id"]: b for b in index.get("blocks", [])}
    for i, e in enumerate(evidence):
        label = "evidence[%d]" % i
        for key in ("path", "sha256", "block_id", "quote", "locator"):
            if key not in e:
                errors.append(label + " 缺 " + key)
        if any(k not in e for k in ("path", "sha256", "block_id", "quote", "locator")):
            continue
        path = norm_path(e["path"])
        b = blocks.get(e["block_id"])
        f = files.get(path)
        if f is None:
            errors.append(label + " 路径不在索引: " + path)
            continue
        if b is None:
            errors.append(label + " block_id 不在索引: " + str(e["block_id"]))
            continue
        if b["path"] != path:
            errors.append(label + " block_id 与路径错配")
        if e["sha256"] != f.get("sha256") or b.get("sha256") != f.get("sha256"):
            errors.append(label + " 版本哈希与索引不符")
        if not isinstance(e["quote"], str) or len(e["quote"].strip()) < 4:
            errors.append(label + " 引文为空或过短")
        elif e["quote"] not in b["text"]:
            errors.append(label + " 引文不是该原文块的逐字子串")
        loc = e["locator"]
        for key in ("page", "printed_page", "paragraph", "slide", "sheet", "row", "section"):
            if loc.get(key) != b["locator"].get(key):
                errors.append(label + " 定位字段 %s 不符: %r != %r" % (key, loc.get(key), b["locator"].get(key)))
        if e.get("source_uri"):
            parsed = urllib.parse.urlsplit(e["source_uri"])
            if norm_path(urllib.parse.unquote(parsed.path)) != path:
                errors.append(label + " source_uri 路径不符")
        if e.get("paragraph_first_sentence") and e["paragraph_first_sentence"] != b.get("paragraph_first_sentence"):
            errors.append(label + " 段落首句被改写")
        if root:
            abs_path = os.path.join(root, path)
            if not os.path.isfile(abs_path):
                errors.append(label + " 当前路径失效: " + path)
            else:
                try:
                    if sha256_file(abs_path) != f["sha256"]:
                        errors.append(label + " 当前文件已变化，须重建索引")
                except OSError as ex:
                    errors.append(label + " 当前文件不可读: " + str(ex))
        checked += 1
    return errors, checked


def verify_query_filters(result, index):
    """重放每个查询的全部硬过滤，防止最终复制证据时丢条件。"""
    errors = []
    files = {f["path"]: f for f in index.get("files", [])}
    blocks = {b["block_id"]: b for b in index.get("blocks", [])}
    for qi, q in enumerate(iter_query_objects(result)):
        filters = q.get("filters_applied", q.get("filters", {}))
        for hi, h in enumerate(q.get("hits", [])):
            f = files.get(norm_path(h.get("path", "")))
            b = blocks.get(h.get("block_id"))
            if f and b:
                merged = dict(f)
                merged.update(b)
                merged["metadata"] = dict(f.get("metadata", {}))
                # 与 search 一致：文件级字段优先；行级字段只在文件未声明时补充。
                for k, v in b.get("row_metadata", {}).items():
                    merged["metadata"].setdefault(k, v)
                violations, _ = check_filters(merged, filters, index.get("field_aliases", {}))
                for v in violations:
                    errors.append("query[%d].hits[%d] 违反硬过滤: %s" % (qi, hi, v))
    return errors


def cmd_verify(args):
    result = load_json(args.result)
    index = load_json(args.index)
    evidence = all_evidence(result)
    errors, checked = verify_evidence(evidence, index, args.root)
    if not evidence:
        queries = list(iter_query_objects(result))
        valid_empty = bool(queries) and all(not q.get("hits") and q.get("no_hit") and q.get("search_trace") for q in queries)
        if not valid_empty:
            errors.append("没有可机检的 hits/evidence；空结果也须保留 search_trace 与 no_hit")
    errors.extend(verify_query_filters(result, index))
    out = {"ok": not errors, "checked_evidence": checked, "errors": errors,
           "rule": "路径+版本哈希+原文块+逐字子串+全部定位字段+硬过滤；合法空结果须留检索轨迹"}
    return emit(out, rc=0 if out["ok"] else 1)


def cmd_schema(args):
    d = load_json(args.result)
    errors, warnings = [], []
    required = ("case_id", "status", "inventory", "files", "version_groups", "queries",
                "operations", "skipped", "failures", "conflicts", "recovery", "sources",
                "uncertainty", "change_log", "gain", "unchecked")
    if not isinstance(d, dict):
        return emit({"ok": False, "errors": ["顶层必须是对象"]}, rc=1)
    for key in required:
        if key not in d:
            errors.append("缺顶层字段 " + key)
    if d.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    if not d.get("case_id"):
        errors.append("case_id 不能为空")
    files = d.get("files", [])
    if isinstance(files, list):
        paths = set()
        for i, f in enumerate(files):
            if not isinstance(f, dict) or not f.get("path"):
                errors.append("files[%d] 缺 path" % i)
                continue
            if f["path"] in paths:
                errors.append("files 重复路径 " + f["path"])
            paths.add(f["path"])
            if f.get("status") in {"indexed", "readable", "empty", "ocr_needs_review"} and not re.fullmatch(r"[0-9a-f]{64}", str(f.get("sha256", ""))):
                errors.append("files[%d] 缺完整 sha256" % i)
        inv = d.get("inventory", {})
        if isinstance(inv, dict) and inv.get("file_count") is not None and inv["file_count"] != len(files):
            errors.append("inventory.file_count 与 files 数量不一致")
    else:
        errors.append("files 必须是数组")
    queries = d.get("queries", [])
    if not isinstance(queries, list) or not queries:
        errors.append("queries 必须至少含一次实际检索")
    else:
        for i, q in enumerate(queries):
            for key in ("question", "filters", "hits", "search_trace"):
                if key not in q:
                    errors.append("queries[%d] 缺 %s" % (i, key))
            if q.get("hits") == [] and "no_hit" not in q:
                errors.append("queries[%d] 空结果缺 no_hit 与恢复动作" % i)
    for i, vg in enumerate(d.get("version_groups", []) if isinstance(d.get("version_groups"), list) else []):
        if not vg.get("evidence"):
            errors.append("version_groups[%d] 缺关系判据 evidence；不能仅凭 final/日期命名" % i)
    if d.get("status") == "pass":
        for key in ("failures", "conflicts", "unchecked"):
            if d.get(key):
                errors.append("status=pass 但 %s 非空" % key)
    gain = d.get("gain")
    if not isinstance(gain, dict) or gain.get("comparison_status") not in {"measured", "platform_pending", "not_measured"}:
        errors.append("gain.comparison_status 必须为 measured/platform_pending/not_measured")
    elif gain.get("comparison_status") == "measured" and not (gain.get("same_input") and gain.get("same_permissions")):
        errors.append("measured 增益必须证明 same_input 与 same_permissions")
    if args.index:
        index = load_json(args.index)
        evidence = all_evidence(d)
        ev_errors, checked = verify_evidence(evidence, index, args.root)
        errors.extend(ev_errors)
        errors.extend(verify_query_filters(d, index))
        if not evidence and any(q.get("hits") for q in queries if isinstance(q, dict)):
            errors.append("有命中但未收集到证据")
    out = {"ok": not errors, "errors": errors, "warnings": warnings,
           "checked_queries": len(queries) if isinstance(queries, list) else 0}
    return emit(out, rc=0 if out["ok"] else 1)


def output_fingerprint(d):
    return d.get("input_fingerprint") or d.get("metrics", {}).get("input_fingerprint")


def permission_fingerprint(d):
    return d.get("permissions_fingerprint") or d.get("metrics", {}).get("permissions_fingerprint")


def elapsed(d):
    return d.get("metrics", {}).get("elapsed_seconds", d.get("elapsed_seconds"))


def cmd_compare(args):
    base, skill, index = load_json(args.baseline), load_json(args.skill), load_json(args.index)
    fairness_errors = []
    if base.get("case_id") != skill.get("case_id"):
        fairness_errors.append("case_id 不同，禁止比较")
    if output_fingerprint(base) != output_fingerprint(skill):
        fairness_errors.append("input_fingerprint 不同或缺失，禁止声称同输入增益")
    if permission_fingerprint(base) != permission_fingerprint(skill):
        fairness_errors.append("permissions_fingerprint 不同或缺失，禁止声称同权限增益")
    be, se = all_evidence(base), all_evidence(skill)
    berr, _ = verify_evidence(be, index)
    serr, _ = verify_evidence(se, index)
    # 有效率按唯一证据对象计；错误列表可能一条证据多项，所以逐条重算。
    def valid_count(items):
        return sum(0 if verify_evidence([x], index)[0] else 1 for x in items)
    bv, sv = valid_count(be), valid_count(se)
    out = {"case_id": skill.get("case_id"), "fairness": {
               "same_input": not any("input" in x for x in fairness_errors),
               "same_permissions": not any("permission" in x for x in fairness_errors),
               "errors": fairness_errors},
           "baseline": {"evidence_count": len(be), "valid_evidence_count": bv,
                        "valid_evidence_rate": bv / len(be) if be else 0.0,
                        "elapsed_seconds": elapsed(base)},
           "skill": {"evidence_count": len(se), "valid_evidence_count": sv,
                     "valid_evidence_rate": sv / len(se) if se else 0.0,
                     "elapsed_seconds": elapsed(skill)},
           "quality_gain": {"valid_evidence_rate_delta": (sv / len(se) if se else 0.0) - (bv / len(be) if be else 0.0),
                            "valid_evidence_count_delta": sv - bv}}
    if elapsed(base) is not None and elapsed(skill) is not None:
        out["efficiency_gain"] = {"seconds_saved": elapsed(base) - elapsed(skill),
                                  "speedup": elapsed(base) / elapsed(skill) if elapsed(skill) else None}
    if args.gold:
        gold = load_json(args.gold)
        expected = {(norm_path(x["path"]), x.get("block_id")) for x in gold.get("expected", [])}
        def pred(items):
            return {(norm_path(x["path"]), x.get("block_id")) for x in items}
        for name, items in (("baseline", be), ("skill", se)):
            p = pred(items)
            tp = len(p & expected)
            out[name]["gold_precision"] = tp / len(p) if p else 0.0
            out[name]["gold_recall"] = tp / len(expected) if expected else None
        out["quality_gain"]["gold_recall_delta"] = out["skill"]["gold_recall"] - out["baseline"]["gold_recall"]
    out["ok"] = not fairness_errors
    return emit(out, args.output, 0 if out["ok"] else 1)


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    x = sub.add_parser("inventory")
    x.add_argument("root")
    x.add_argument("--output")
    x.set_defaults(func=cmd_inventory)
    x = sub.add_parser("index")
    x.add_argument("root")
    x.add_argument("--output", required=True)
    x.add_argument("--metadata")
    x.add_argument("--aliases")
    x.add_argument("--ocr", action="store_true")
    x.set_defaults(func=cmd_index)
    x = sub.add_parser("search")
    x.add_argument("index")
    x.add_argument("--query", required=True)
    x.add_argument("--filters")
    x.add_argument("--output")
    x.add_argument("--limit", type=int, default=20)
    x.add_argument("--min-score", type=float, default=0.5)
    x.set_defaults(func=cmd_search)
    x = sub.add_parser("verify")
    x.add_argument("result")
    x.add_argument("--index", required=True)
    x.add_argument("--root")
    x.set_defaults(func=cmd_verify)
    x = sub.add_parser("schema")
    x.add_argument("result")
    x.add_argument("--index")
    x.add_argument("--root")
    x.set_defaults(func=cmd_schema)
    x = sub.add_parser("compare")
    x.add_argument("--baseline", required=True)
    x.add_argument("--skill", required=True)
    x.add_argument("--index", required=True)
    x.add_argument("--gold")
    x.add_argument("--output")
    x.set_defaults(func=cmd_compare)
    return p


def main():
    args = parser().parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return emit({"ok": False, "error": type(e).__name__ + ": " + str(e),
                     "recovery": "修正输入路径/JSON 后重跑；不生成假结果"}, rc=2)


if __name__ == "__main__":
    sys.exit(main())
