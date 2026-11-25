#!/usr/bin/env python3
"""网页论文正文抽取与双语对齐。仅使用 Python 标准库。

命令：
  fetch URL --out PAGE.html --meta FETCH.json [--timeout 20] [--max-bytes 8000000]
  stamp PAGE.html --url URL --out FETCH.json --capture-method browser_rendered|provided_snapshot
  extract PAGE.html --meta FETCH.json --out CORPUS.json
  align CORPUS.json TRANSLATION.json --out BILINGUAL.json

align 是机器保真检查，不是自动翻译，也不声称替代语义审校。
"""
import argparse
import collections
import datetime
import hashlib
import html
import html.parser
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TOOL_VERSION = "3.0.0"
SCHEMA_VERSION = "2.0.0"
SKIP_TAGS = {"script", "style", "noscript", "template", "nav", "form", "button", "svg", "canvas"}
NOISE_TAGS = {"aside", "footer"}
NOISE_WORDS = re.compile(r"(?:^|[\s_])(?:nav|navigation|menu|advert|advertisement|social|share|related|recommend|citation-tools|cookie|banner|toolbar|breadcrumb)(?:$|[\s_-])", re.I)
REF_WORDS = re.compile(r"(?:^|[\s_])(?:references?|bibliography|ref-list|reference-list)(?:$|[\s_-])", re.I)
ROOT_WORDS = re.compile(r"article(?:-body|__body|_content)?|full-?text|main-content|post-content|entry-content|paper-body", re.I)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "caption", "table", "li"}
MATH_RE = re.compile(r"(\\\(.*?\\\)|\\\[.*?\\\]|\$\$.*?\$\$|(?<!\$)\$[^$\n]+?\$(?!\$))", re.S)
NUMBER_RE = re.compile(r"(?<![\w.])(?:[+-]?(?:\d+(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?%?)(?![\w.])")
UNIT_RE = re.compile(r"(?<![\w])(?:kg|mg|µg|μg|ng|g|km|cm|mm|µm|μm|nm|mL|ml|µL|μL|L|mol|mmol|µmol|μmol|mM|nM|Hz|kHz|MHz|GHz|Pa|kPa|MPa|GPa|eV|keV|MeV|GeV|TeV|K|°C|℃|h|min|s|ms|µs|μs|ns)(?![\w])")
CITATION_RE = re.compile(r"\[(?:\d+(?:\s*[-–,]\s*\d+)*)\]")
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"']+")


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha_text(value):
    return sha_bytes(value.encode("utf-8"))


def canonical_hash(value):
    return sha_text(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("%s: 顶层必须是 JSON 对象" % path)
    return value


def write_json(path, value):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)


def emit(value, code=0):
    print(json.dumps(value, ensure_ascii=False))
    return code


def normalize_space(value):
    return re.sub(r"\s+", " ", value or "").strip()


def fetch_page(url, out_path, meta_path, timeout=20, max_bytes=8000000):
    started = utcnow()
    meta = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION, "requested_url": url,
            "started_at": started, "finished_at": None, "status": "failed", "http_status": None,
            "final_url": url, "encoding": "utf-8", "headers": {}, "sha256": None, "bytes": 0,
            "failure": None}
    if urllib.parse.urlparse(url).scheme not in {"http", "https"}:
        meta["failure"] = {"kind": "unsupported_scheme", "signal": "仅允许 http/https",
                           "action": "交给已提供的浏览器工具或人工取得页面；不绕过权限"}
        write_json(meta_path, meta)
        return emit(meta, 2)
    request = urllib.request.Request(url, headers={
        "User-Agent": "WebReadingTranslation/%s (research source verification)" % TOOL_VERSION,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        "Accept-Encoding": "identity",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            final_url = response.geturl()
            headers = {k.lower(): v for k, v in response.headers.items()}
            meta.update(http_status=response.status, final_url=final_url, headers=headers,
                        encoding=response.headers.get_content_charset() or "utf-8")
            if len(raw) > max_bytes:
                meta["failure"] = {"kind": "oversized_page", "signal": "超过 max-bytes=%d" % max_bytes,
                                   "action": "停止；调大有界预算或使用浏览器保存渲染后 HTML"}
            elif response.status == 401:
                meta["failure"] = {"kind": "login_expired", "signal": "HTTP 401",
                                   "action": "停止并交人工重新认证；保留快照，不尝试绕过"}
            elif response.status in {402, 403, 407}:
                meta["failure"] = {"kind": "permission_denied", "signal": "HTTP %d" % response.status,
                                   "action": "停止；确认订阅/代理权限，不绕过付费墙或访问控制"}
            elif urllib.parse.urlparse(url).netloc.lower() != urllib.parse.urlparse(final_url).netloc.lower():
                meta["failure"] = {"kind": "cross_domain_redirect", "signal": "%s -> %s" % (url, final_url),
                                   "action": "停止；人工确认目标域与权限后用最终 URL 新起一次抓取"}
            else:
                parent = os.path.dirname(os.path.abspath(out_path))
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                with open(out_path, "wb") as handle:
                    handle.write(raw)
                meta.update(status="done", sha256=sha_bytes(raw), bytes=len(raw))
    except urllib.error.HTTPError as exc:
        meta["http_status"] = exc.code
        kind = "login_expired" if exc.code == 401 else "permission_denied" if exc.code in {402, 403, 407} else "rate_limited" if exc.code == 429 else "http_error"
        action = "停止并交人工认证/授权" if exc.code in {401, 402, 403, 407} else "按 Retry-After 或指数退避有界重试；达到上限标 failed 并保留 resume_point" if exc.code == 429 else "记录响应；仅在幂等 GET 且服务瞬断时有界重试"
        meta["failure"] = {"kind": kind, "signal": "HTTP %d" % exc.code, "action": action}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        meta["failure"] = {"kind": "timeout" if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower() else "network_error",
                           "signal": str(reason), "action": "保留失败记录；有界重试一次，仍失败则标 partial 并交人工"}
    finally:
        meta["finished_at"] = utcnow()
        write_json(meta_path, meta)
    return emit(meta, 0 if meta["status"] == "done" else 1)


def stamp_snapshot(snapshot_path, url, meta_path, capture_method, encoding="utf-8", notes=""):
    """为浏览器/题目提供的真实 HTML 快照补同构版本元数据，不伪称 HTTP 抓取。"""
    if capture_method not in {"browser_rendered", "provided_snapshot"}:
        return emit({"ok": False, "failure": {"kind": "unsupported_capture_method", "signal": capture_method,
                     "action": "只登记实际使用的 browser_rendered/provided_snapshot"}}, 2)
    if urllib.parse.urlparse(url).scheme not in {"http", "https"}:
        return emit({"ok": False, "failure": {"kind": "unsupported_scheme", "signal": url,
                     "action": "记录真实 http/https 来源，不虚构 file URL 为网页"}}, 2)
    try:
        with open(snapshot_path, "rb") as handle:
            raw = handle.read()
        if not raw:
            raise ValueError("空 HTML 快照")
        now = utcnow()
        meta = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION, "requested_url": url,
                "started_at": now, "finished_at": now, "status": "done", "http_status": None,
                "final_url": url, "encoding": encoding, "headers": {}, "sha256": sha_bytes(raw), "bytes": len(raw),
                "page_version": sha_bytes(raw), "capture_method": capture_method, "capture_notes": notes,
                "failure": None}
        write_json(meta_path, meta)
        return emit(meta, 0)
    except (OSError, ValueError) as exc:
        return emit({"ok": False, "status": "failed", "failure": {"kind": "unversioned_snapshot", "signal": str(exc),
                     "action": "取得真实非空 HTML 后重跑 stamp；不得编造快照"}}, 1)


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = dict(attrs or [])
        self.children = []
        self.parent = parent

    def append(self, child):
        self.children.append(child)


class DOMParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def _autoclose(self, tag):
        rules = {"li": {"li"}, "p": {"p"}, "tr": {"tr"}, "td": {"td", "th"}, "th": {"td", "th"},
                 "option": {"option"}}
        if tag in rules and self.stack[-1].tag in rules[tag]:
            self.stack.pop()
        if tag == "p":
            for index in range(len(self.stack) - 1, 0, -1):
                if self.stack[index].tag == "p":
                    del self.stack[index:]
                    break
                if self.stack[index].tag in {"section", "article", "div", "main", "td", "li"}:
                    break

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        self._autoclose(tag)
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = Node(tag.lower(), attrs, self.stack[-1])
        self.stack[-1].append(node)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].append(data)


def walk(node):
    yield node
    for child in node.children:
        if isinstance(child, Node):
            yield from walk(child)


def first_meta(root, names):
    names = {x.lower() for x in names}
    for node in walk(root):
        if node.tag == "meta" and node.attrs.get("name", "").lower() in names:
            value = node.attrs.get("content")
            if value:
                return value.strip()
    return None


def all_meta(root, names):
    names = {x.lower() for x in names}
    return [n.attrs["content"].strip() for n in walk(root)
            if n.tag == "meta" and n.attrs.get("name", "").lower() in names and n.attrs.get("content", "").strip()]


def metadata_text(node):
    """作者/日期回退提取：剔除嵌在姓名后的整段脚注与单位。"""
    if not isinstance(node, Node):
        return str(node)
    classes = node.attrs.get("class", "")
    if re.search(r"ltx_note|ltx_contact|ltx_role_affiliation|ltx_affiliation", classes):
        return ""
    return "".join(metadata_text(x) for x in node.children)


def dom_path(node):
    parts = []
    current = node
    while current is not None and current.tag != "document":
        if current.parent is None:
            break
        same = [x for x in current.parent.children if isinstance(x, Node) and x.tag == current.tag]
        part = "%s[%d]" % (current.tag, same.index(current) + 1)
        if current.attrs.get("id"):
            part += "#" + current.attrs["id"]
        parts.append(part)
        current = current.parent
    return "/" + "/".join(reversed(parts))


def css_anchor(node, block_id):
    current = node
    while current is not None and current.tag != "document":
        if current.attrs.get("id"):
            return "#" + current.attrs["id"]
        current = current.parent
    return "#" + block_id


def serialize(node):
    if not isinstance(node, Node):
        return html.escape(str(node), quote=False)
    attrs = "".join(" %s=\"%s\"" % (k, html.escape(str(v), quote=True)) for k, v in node.attrs.items())
    content = "".join(serialize(x) for x in node.children)
    if node.tag in VOID_TAGS:
        return "<%s%s>" % (node.tag, attrs)
    return "<%s%s>%s</%s>" % (node.tag, attrs, content, node.tag)


def math_value(node):
    for key in ("alttext", "data-alttext", "data-tex", "aria-label"):
        if node.attrs.get(key):
            return node.attrs[key].strip(), "tex"
    for child in walk(node):
        if child.tag == "annotation" and ("tex" in child.attrs.get("encoding", "").lower() or "latex" in child.attrs.get("encoding", "").lower()):
            value = normalize_space("".join(str(x) for x in child.children if not isinstance(x, Node)))
            if value:
                return value, "tex"
    value = normalize_space(serialize(node))
    return value, "mathml" if value else "unknown"


def text_of(node, formulas=None, in_footnote=False):
    if not isinstance(node, Node):
        return str(node)
    tag = node.tag
    if tag in SKIP_TAGS:
        return ""
    classes = node.attrs.get("class", "")
    note_boundary = "ltx_note_outer" in classes or "ltx_note_content" in classes
    if note_boundary and not in_footnote:
        return ""
    in_footnote = in_footnote or note_boundary
    if tag == "math":
        value, form = math_value(node)
        token = "\\(%s\\)" % value if form == "tex" else "[[MATHML:%s]]" % value
        if formulas is not None:
            formulas.append({"format": form, "value": value, "token": token, "mathml": serialize(node)})
        return token
    if tag in {"img"}:
        alt = node.attrs.get("alt", "").strip()
        return alt
    if tag == "br":
        return " "
    if tag in {"sub", "sup"}:
        inner = normalize_space("".join(text_of(x, formulas, in_footnote) for x in node.children))
        if tag == "sup" and re.fullmatch(r"(?:\[\d+(?:\s*[-–,]\s*\d+)*\]|\d+|[*†‡])", inner):
            return inner
        return ("_{%s}" if tag == "sub" else "^{%s}") % inner
    if tag == "annotation":
        return ""
    value = "".join(text_of(x, formulas, in_footnote) for x in node.children)
    if tag in {"p", "div", "section", "li", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "caption", "tr"}:
        value += " "
    return value


def attr_noise(node):
    value = " ".join([node.attrs.get("id", ""), node.attrs.get("class", ""), node.attrs.get("role", "")]).replace("_", " ")
    return bool(NOISE_WORDS.search(value))


def attr_reference(node):
    value = " ".join([node.attrs.get("id", ""), node.attrs.get("class", "")]).replace("_", " ")
    return bool(REF_WORDS.search(value))


def heading_text(node):
    if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return normalize_space(text_of(node)).lower()
    for child in node.children:
        if isinstance(child, Node) and child.tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return normalize_space(text_of(child)).lower()
    return ""


def is_reference_node(node):
    if attr_reference(node):
        return True
    title = heading_text(node)
    return bool(re.fullmatch(r"(?:\d+[.\s]*)?(?:references?|bibliography|参考文献)(?:\s*[:：]?)", title, re.I))


def is_noise(node):
    if node.tag in SKIP_TAGS or node.tag in NOISE_TAGS or attr_noise(node):
        return True
    if node.tag == "header":
        # 保留真正的章节标题，但剔除作者/期刊/导航页眉文字。
        return not any(x.tag in {"h2", "h3", "h4"} for x in walk(node))
    return False


def choose_root(root):
    candidates = []
    for node in walk(root):
        attrs = "%s %s" % (node.attrs.get("id", ""), node.attrs.get("class", ""))
        if node.tag in {"article", "main"} or ROOT_WORDS.search(attrs):
            text = normalize_space(text_of(node))
            ptext = sum(len(normalize_space(text_of(p))) for p in walk(node) if p.tag == "p" and not is_noise(p))
            score = min(len(text), 20000) + 2 * min(ptext, 30000)
            if node.tag in {"article", "main"}:
                score += 12000
            if ROOT_WORDS.search(attrs):
                score += 10000
            if attr_noise(node) or attr_reference(node):
                score -= 30000
            candidates.append((score, node))
    if candidates:
        best = max(candidates, key=lambda x: x[0])[1]
        if normalize_space(text_of(best)):
            return best
    for node in walk(root):
        if node.tag == "body":
            return node
    return root


def section_kind(path):
    joined = " ".join(path).lower()
    if re.search(r"abstract|摘要", joined):
        return "abstract"
    if re.search(r"methods?|materials?|方法|材料", joined):
        return "methods"
    if re.search(r"results?|结果", joined):
        return "results"
    if re.search(r"discussion|讨论", joined):
        return "discussion"
    if re.search(r"conclusions?|结论", joined):
        return "conclusion"
    if re.search(r"introduction|引言|介绍", joined):
        return "introduction"
    return "body"


def table_data(node, formulas):
    rows = []
    for tr in (x for x in walk(node) if x.tag == "tr"):
        cells = [normalize_space(text_of(cell, formulas)) for cell in tr.children
                 if isinstance(cell, Node) and cell.tag in {"td", "th"}]
        if cells:
            rows.append(cells)
    width = max((len(row) for row in rows), default=0)
    rows = [row + [""] * (width - len(row)) for row in rows]
    if not rows:
        return {"rows": [], "n_rows": 0, "n_columns": 0, "html": serialize(node)}, "(empty table)"
    def esc(cell):
        return cell.replace("|", "\\|")
    lines = ["| " + " | ".join(esc(cell) for cell in rows[0]) + " |",
             "| " + " | ".join("---" for _ in range(width)) + " |"]
    for row in rows[1:]:
        lines.append("| " + " | ".join(esc(cell) for cell in row) + " |")
    return {"rows": rows, "n_rows": len(rows), "n_columns": width, "html": serialize(node)}, "\n".join(lines)


def extract_blocks(root):
    blocks = []
    excluded = []
    path = []
    ordinal = 0

    def append_block(node, text, kind, formulas, table=None):
        nonlocal ordinal
        if not text or text == "(empty table)":
            return
        ordinal += 1
        bid = "B%04d" % ordinal
        blocks.append({"id": bid, "order": ordinal, "kind": kind, "dom_path": dom_path(node),
                       "html_anchor": css_anchor(node, bid), "section_path": path,
                       "section_kind": section_kind(path), "text": text, "quote": text,
                       "text_sha256": sha_text(text), "formulas": formulas, "table": table,
                       "source_scope": "translation"})

    def recurse(node):
        nonlocal path
        if not isinstance(node, Node):
            return
        if is_noise(node):
            excluded.append({"dom_path": dom_path(node), "reason": "navigation_or_noise", "tag": node.tag})
            return
        if is_reference_node(node) and node.tag not in {"a", "sup"}:
            excluded.append({"dom_path": dom_path(node), "reason": "reference_list_excluded_from_body", "tag": node.tag,
                             "text_preview": normalize_space(text_of(node))[:240]})
            return
        # 脚注统一在后文独立成块，避免正文内联脚注重复一次、独立段落又重复一次。
        if any(re.search(r"ltx_note|footnote", a.attrs.get("class", ""), re.I) or a.attrs.get("role") == "doc-footnote" for a in ancestor_nodes(node)) and node.tag in BLOCK_TAGS:
            return
        old_path = path
        if node.tag in {"section", "article", "main"}:
            title = heading_text(node)
            if title:
                path = path + [title]
        if node.tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "figcaption", "caption", "table"}:
            if node.tag == "table":
                # caption 先于表格单独成块；table 的 Markdown 不重复 caption。
                for child in node.children:
                    if isinstance(child, Node) and child.tag == "caption":
                        recurse(child)
            formulas = []
            table = None
            classes = node.attrs.get("class", "")
            equation_table = node.tag == "table" and re.search(r"ltx_equation|ltx_eqn", classes)
            if node.tag == "table" and not equation_table:
                table, text = table_data(node, formulas)
                kind = "table"
            else:
                text = normalize_space(text_of(node, formulas))
                if equation_table:
                    kind = "formula"
                elif node.tag == "caption":
                    kind = "table_caption"
                elif node.tag == "figcaption":
                    ancestor_classes = " ".join(a.attrs.get("class", "") for a in ancestor_nodes(node))
                    kind = "table_caption" if "ltx_table" in ancestor_classes else "figure_caption"
                else:
                    kind = "heading" if node.tag.startswith("h") else "paragraph"
            append_block(node, text, kind, formulas, table)
            return  # 不把表格单元格/标题内部文字再抽成重复块。
        for child in node.children:
            recurse(child)
        path = old_path

    recurse(root)
    # LaTeXML/常见 HTML 脚注：保留脚注标记在正文，脚注内容独立翻译并可回链。
    for note in walk(root):
        classes = note.attrs.get("class", "")
        is_note = "ltx_note_content" in classes or note.attrs.get("role") == "doc-footnote"
        if not is_note or any("ltx_note_content" in a.attrs.get("class", "") for a in ancestor_nodes(note)):
            continue
        formulas = []
        text = normalize_space(text_of(note, formulas, True))
        append_block(note, text, "footnote", formulas)
    # char offsets 在同一个拼接正文中唯一，可复跑定位。
    cursor = 0
    full_parts = []
    for block in blocks:
        if full_parts:
            cursor += 2
            full_parts.append("\n\n")
        block["char_start"] = cursor
        block["char_end"] = cursor + len(block["text"])
        cursor = block["char_end"]
        full_parts.append(block["text"])
    return blocks, excluded, "".join(full_parts)


def ancestor_nodes(node):
    current = node.parent
    while current is not None:
        yield current
        current = current.parent


def access_signals(root, raw_text, meta):
    issues = []
    nodes = list(walk(root))
    para_count = sum(1 for n in nodes if n.tag == "p" and len(normalize_space(text_of(n))) > 40
                     and not any(is_noise(a) for a in ancestor_nodes(n)))
    title_nodes = [normalize_space(text_of(n)) for n in nodes if n.tag == "title"]
    title = title_nodes[0] if title_nodes else ""
    password = any(n.tag == "input" and n.attrs.get("type", "").lower() == "password" for n in nodes)
    login_text = bool(re.search(r"sign in to (?:view|access|read)|log in to (?:view|access|read)|登录后(?:查看|阅读)|会话(?:已)?过期|session expired", raw_text, re.I))
    paywall_text = bool(re.search(r"subscribe to (?:view|read|access)|purchase (?:this article|access)|paywall|subscription required|订阅后(?:查看|阅读)|购买全文|付费墙", raw_text, re.I))
    if meta.get("http_status") == 401 or ((password or login_text) and para_count < 3):
        issues.append({"kind": "login_expired", "severity": "fatal", "signal": "登录表单/会话失效且正文不足", "action": "停止；人工认证后重新保存页面"})
    if paywall_text and para_count < 8:
        issues.append({"kind": "paywall", "severity": "fatal", "signal": "订阅/购买提示且只能取得部分内容", "action": "停止；确认合法订阅权限，不绕过付费墙"})
    if para_count == 0 and any(n.tag == "script" for n in nodes):
        issues.append({"kind": "dynamic_render_failed", "severity": "fatal", "signal": "只有脚本、未取得正文段落", "action": "使用已提供的 Chromium 渲染后保存 HTML，再重跑 extract"})
    if title and re.search(r"(?:just a moment|access denied|attention required|验证码|安全验证)", title, re.I):
        issues.append({"kind": "access_control", "severity": "fatal", "signal": "页面标题=" + title, "action": "停止并交人工；不绕过站点风控"})
    if meta.get("sha256") is None:
        issues.append({"kind": "unversioned_snapshot", "severity": "fatal", "signal": "fetch meta 缺 sha256", "action": "使用 fetch 生成带哈希的快照元数据"})
    return issues


def page_signals(root):
    pagination = []
    lazy = []
    for node in walk(root):
        rel = node.attrs.get("rel", "")
        classes = node.attrs.get("class", "")
        href = node.attrs.get("href") or node.attrs.get("data-href")
        if node.tag in {"a", "link"} and (re.search(r"(?:^|\s)next(?:\s|$)", rel, re.I) or re.search(r"(?:^|\s)(?:next|pagination-next)(?:\s|$)", classes, re.I)):
            pagination.append({"dom_path": dom_path(node), "href": href, "signal": "rel/class next"})
        if node.tag in {"img", "iframe"}:
            unresolved = [k for k in ("data-src", "data-original", "data-lazy-src") if node.attrs.get(k)]
            placeholder = node.attrs.get("src", "")
            if unresolved and (not placeholder or placeholder.startswith("data:") or "placeholder" in placeholder):
                lazy.append({"dom_path": dom_path(node), "attributes": unresolved, "signal": "只有懒加载占位资源"})
    return pagination, lazy


def read_snapshot(path, meta):
    with open(path, "rb") as handle:
        raw = handle.read()
    actual_hash = sha_bytes(raw)
    if meta.get("sha256") and meta["sha256"] != actual_hash:
        raise ValueError("快照 sha256 与 fetch 元数据不一致；拒绝抽取被替换/损坏的页面")
    encoding = meta.get("encoding") or "utf-8"
    try:
        decoded = raw.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        match = re.search(br"<meta[^>]+charset=[\"']?\s*([A-Za-z0-9_-]+)", raw[:4096], re.I)
        encoding = match.group(1).decode("ascii") if match else "utf-8"
        decoded = raw.decode(encoding, errors="replace")
    return raw, decoded, actual_hash


def protected_tokens(text):
    values = []
    values.extend(m.group(0) for m in MATH_RE.finditer(text))
    masked = MATH_RE.sub(" ", text)
    values.extend(m.group(0) for m in NUMBER_RE.finditer(masked))
    values.extend(m.group(0) for m in UNIT_RE.finditer(masked))
    values.extend(m.group(0) for m in CITATION_RE.finditer(masked))
    values.extend(m.group(0) for m in DOI_RE.finditer(masked))
    values.extend(m.group(0) for m in URL_RE.finditer(masked))
    return values


def extract_document(snapshot_path, meta_path):
    meta = load_json(meta_path)
    raw, decoded, actual_hash = read_snapshot(snapshot_path, meta)
    parser = DOMParser()
    parser.feed(decoded)
    parser.close()
    root = choose_root(parser.root)
    issues = access_signals(parser.root, decoded, meta)
    blocks, excluded, full_text = extract_blocks(root)
    pagination, lazy = page_signals(parser.root)
    if not blocks and not any(x["severity"] == "fatal" for x in issues):
        issues.append({"kind": "missing_article_element", "severity": "fatal", "signal": "主候选根节点未产出正文块",
                       "action": "记录失效选择器与 dom_path；人工确认改版后新增适配，不拿摘要冒充全文"})
    if pagination:
        issues.append({"kind": "pagination", "severity": "partial", "signal": "检测到下一页链接 %d 个" % len(pagination),
                       "action": "逐页保存并抽取，未合并齐全前结果标 partial；不得声称全文完成"})
    if lazy:
        issues.append({"kind": "lazy_load_unresolved", "severity": "partial", "signal": "未解析懒加载资源 %d 个" % len(lazy),
                       "action": "用 Chromium 滚动并等待资源后重存 HTML；缺口在 unchecked 标注"})
    abstract_blocks = [x for x in blocks if x["section_kind"] == "abstract"]
    nonheading = [x for x in blocks if x["kind"] not in {"heading", "figure_caption", "table_caption"}]
    if abstract_blocks and len(nonheading) <= len(abstract_blocks) + 1:
        issues.append({"kind": "abstract_only", "severity": "fatal", "signal": "只检测到摘要及至多一个正文块",
                       "action": "标 partial/failed；回到全文链接，不以摘要页代替正文"})
    fatal = any(x["severity"] == "fatal" for x in issues)
    metadata = {
        "title": first_meta(parser.root, ["citation_title", "dc.title", "dcterms.title", "og:title"]),
        "authors": all_meta(parser.root, ["citation_author", "dc.creator"]),
        "journal": first_meta(parser.root, ["citation_journal_title", "prism.publicationname"]),
        "year": first_meta(parser.root, ["citation_publication_date", "citation_year", "dc.date"]),
        "doi": first_meta(parser.root, ["citation_doi", "dc.identifier"]),
    }
    if not metadata["title"]:
        titles = [normalize_space(text_of(n)) for n in walk(parser.root) if n.tag == "title"]
        metadata["title"] = titles[0] if titles else None
    if not metadata["authors"]:
        metadata["authors"] = [normalize_space(metadata_text(n)) for n in walk(parser.root)
                               if re.search(r"(?:^|\s)(?:ltx_personname|fn)(?:\s|$)", n.attrs.get("class", ""))]
        metadata["authors"] = [x for x in metadata["authors"] if x]
    if not metadata["year"]:
        dates = [n.attrs.get("datetime") or normalize_space(metadata_text(n)) for n in walk(parser.root)
                 if n.tag == "time" or "ltx_date" in n.attrs.get("class", "")]
        metadata["year"] = next((x for x in dates if x), None)
    for block in blocks:
        block["protected_tokens"] = protected_tokens(block["text"])
    source = {"requested_url": meta.get("requested_url"), "url": meta.get("final_url") or meta.get("requested_url"),
              "http_status": meta.get("http_status"), "fetched_at": meta.get("finished_at") or meta.get("started_at"),
              "snapshot_path": os.path.abspath(snapshot_path), "snapshot_sha256": actual_hash,
              "bytes": len(raw), "page_version": meta.get("headers", {}).get("last-modified") or meta.get("headers", {}).get("etag") or actual_hash,
              "content_type": meta.get("headers", {}).get("content-type"), "capture_method": meta.get("capture_method", "urllib_http"),
              "capture_notes": meta.get("capture_notes", ""), "root_dom_path": dom_path(root),
              "root_html_anchor": css_anchor(root, "ROOT")}
    status = "failed" if fatal or not blocks else "issues" if issues else "pass"
    corpus = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION, "kind": "source_corpus",
              "extraction_status": status, "complete": status == "pass", "source": source, "metadata": metadata,
              "blocks": blocks, "excluded": excluded, "issues": issues,
              "page_signals": {"pagination": pagination, "lazy_load": lazy},
              "coverage": {"translation_blocks": len(blocks),
                           "paragraphs": sum(x["kind"] == "paragraph" for x in blocks),
                           "headings": sum(x["kind"] == "heading" for x in blocks),
                           "figure_captions": sum(x["kind"] == "figure_caption" for x in blocks),
                           "table_captions": sum(x["kind"] == "table_caption" for x in blocks),
                           "tables": sum(x["kind"] == "table" for x in blocks),
                           "formula_blocks": sum(x["kind"] == "formula" for x in blocks),
                           "footnotes": sum(x["kind"] == "footnote" for x in blocks),
                           "formulas": sum(len(x["formulas"]) for x in blocks),
                           "excluded_nodes": len(excluded)},
              "full_text_sha256": sha_text(full_text), "corpus_sha256": None}
    corpus["corpus_sha256"] = canonical_hash({k: v for k, v in corpus.items() if k != "corpus_sha256"})
    return corpus


def markdown_shape(text):
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("|") and line.strip().endswith("|")]
    if len(lines) < 2:
        return (0, 0)
    rows = [line for line in lines if not re.fullmatch(r"\|(?:\s*:?-{3,}:?\s*\|)+", line)]
    def columns(line):
        return len(re.split(r"(?<!\\)\|", line)) - 2
    return (len(rows), max((columns(x) for x in rows), default=0))


def term_occurs(source, term):
    if re.search(r"[A-Za-z0-9]", term):
        pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])"
    else:
        pattern = re.escape(term)
    return re.search(pattern, source, re.I) is not None


def source_variants(entry):
    values = [entry.get("source", "")] + list(entry.get("source_variants") or [])
    return [x for x in values if isinstance(x, str) and x.strip()]


def target_variants(entry):
    values = [entry.get("target", "")] + list(entry.get("target_variants") or [])
    return [x for x in values if isinstance(x, str) and x.strip()]


def align_document(corpus, translation):
    errors, warnings = [], []
    if translation.get("corpus_sha256") != corpus.get("corpus_sha256"):
        errors.append("translation.corpus_sha256 与语料不一致；拒绝错版对齐")
    tparas = translation.get("paragraphs")
    if not isinstance(tparas, list):
        errors.append("translation.paragraphs 必须是数组")
        tparas = []
    by_id = collections.defaultdict(list)
    for index, para in enumerate(tparas):
        if not isinstance(para, dict) or not para.get("id"):
            errors.append("paragraphs[%d] 缺 id" % index)
            continue
        if not isinstance(para.get("target"), str) or not para["target"].strip():
            errors.append("%s 的 target 为空" % para.get("id"))
        by_id[para["id"]].append((index, para))
    source_ids = [x["id"] for x in corpus.get("blocks", [])]
    for sid, values in by_id.items():
        if len(values) > 1:
            errors.append("译文段落 id 重复: %s" % sid)
        if sid not in source_ids:
            errors.append("译文含原文不存在的 id: %s" % sid)
    input_order = [x.get("id") for x in tparas if isinstance(x, dict)]
    expected_order = [x for x in input_order if x in source_ids]
    if expected_order != [x for x in source_ids if x in expected_order]:
        errors.append("译文段落顺序与原文不一致")
    missing = [x for x in source_ids if x not in by_id]
    if missing:
        errors.append("漏译/漏对齐: " + ", ".join(missing))
    glossary = translation.get("glossary") or []
    for i, entry in enumerate(glossary):
        if not isinstance(entry, dict) or not entry.get("source") or not target_variants(entry):
            errors.append("glossary[%d] 必须有 source 与非空 target/target_variants" % i)
            continue
        if entry.get("occurrence_policy", "at_least_once_per_source_paragraph") not in {"at_least_once_per_source_paragraph", "first_full_then_abbreviation"}:
            errors.append("glossary[%d] occurrence_policy 未登记" % i)
        if entry.get("occurrence_policy") == "first_full_then_abbreviation" and not (entry.get("first_target") or entry.get("target")):
            errors.append("glossary[%d] 首现全称策略缺 first_target/target" % i)
    metadata_errors = []
    translated_meta = translation.get("metadata") or {}
    for key in ("title", "authors", "journal", "year", "doi"):
        expected = corpus.get("metadata", {}).get(key)
        if expected and key not in translated_meta:
            metadata_errors.append("缺 " + key)
        elif expected and translated_meta.get(key) != expected:
            metadata_errors.append(key + " 被改写")
        elif not expected and key in translated_meta and translated_meta.get(key) not in (None, "", []):
            warnings.append("原文元数据 %s 未报告，但译文填了值；请回原文核实" % key)
    if metadata_errors:
        errors.extend("元数据不保真: " + x for x in metadata_errors)
    output_paras = []
    glossary_rows = []
    seen_terms = set()
    total_violations = 0
    for block in corpus.get("blocks", []):
        if block["id"] not in by_id:
            continue
        target = by_id[block["id"]][0][1].get("target", "")
        source_counts = collections.Counter(block.get("protected_tokens") or protected_tokens(block["text"]))
        target_counts = collections.Counter(protected_tokens(target))
        missing_tokens, changed_tokens = [], []
        for token, count in source_counts.items():
            if target_counts[token] != count:
                changed_tokens.append({"token": token, "source_count": count, "target_count": target_counts[token]})
                if target_counts[token] < count:
                    missing_tokens.append(token)
        extra_countable = []
        for token, count in target_counts.items():
            if not source_counts[token] and (MATH_RE.fullmatch(token) or DOI_RE.fullmatch(token) or URL_RE.fullmatch(token)):
                extra_countable.append(token)
        table_report = None
        if block.get("kind") == "table":
            expected_shape = (block["table"]["n_rows"], block["table"]["n_columns"])
            actual_shape = markdown_shape(target)
            table_report = {"expected_rows_columns": list(expected_shape), "actual_rows_columns": list(actual_shape),
                            "ok": actual_shape == expected_shape}
            if actual_shape != expected_shape:
                errors.append("%s 表格结构改变: 期望%s，实际%s" % (block["id"], expected_shape, actual_shape))
        if changed_tokens:
            errors.append("%s 数字/公式/单位/引文标记未逐项保留: %d 项" % (block["id"], len(changed_tokens)))
        if extra_countable:
            errors.append("%s 凭空增加公式/DOI/URL" % block["id"])
        total_violations += len(changed_tokens) + len(extra_countable) + (0 if table_report is None or table_report["ok"] else 1)
        term_reports = []
        for gi, entry in enumerate(glossary):
            if not isinstance(entry, dict) or not entry.get("source"):
                continue
            source_forms = source_variants(entry)
            matched_sources = [form for form in source_forms if term_occurs(block["text"], form)]
            if matched_sources:
                policy = entry.get("occurrence_policy", "at_least_once_per_source_paragraph")
                variants = target_variants(entry)
                if policy == "first_full_then_abbreviation" and gi not in seen_terms:
                    variants = [entry.get("first_target") or entry.get("target", "")]
                hits = [v for v in variants if v and term_occurs(target, v)]
                report = {"glossary_index": gi, "source": entry["source"], "matched_source_variants": matched_sources,
                          "allowed_targets": variants, "matched_targets": hits, "ok": bool(hits), "policy": policy}
                term_reports.append(report)
                glossary_rows.append(dict(report, block_id=block["id"]))
                if not hits:
                    errors.append("%s 术语 %r 未使用约定译法 %r" % (block["id"], matched_sources, variants))
                seen_terms.add(gi)
        if normalize_space(target) == normalize_space(block["text"]) and re.search(r"[A-Za-z]{4}", block["text"]):
            warnings.append("%s 译文与英文原文完全相同；机器无法据此确认已翻译" % block["id"])
        output = {"id": block["id"], "order": block["order"], "kind": block["kind"],
                  "section_path": block["section_path"], "section_kind": block["section_kind"],
                  "location": {"url": corpus["source"]["url"], "snapshot_sha256": corpus["source"]["snapshot_sha256"],
                               "dom_path": block["dom_path"], "html_anchor": block["html_anchor"],
                               "block_order": block["order"], "char_start": block["char_start"], "char_end": block["char_end"]},
                  "quote": block["quote"], "source_sha256": block["text_sha256"], "target": target,
                  "protected_tokens": block.get("protected_tokens", []),
                  "token_changes": changed_tokens, "unexpected_tokens": extra_countable,
                  "table_check": table_report, "term_checks": term_reports}
        if block.get("formulas"):
            output["formulas"] = block["formulas"]
        if block.get("table"):
            output["table"] = block["table"]
        output_paras.append(output)
    if not output_paras:
        errors.append("没有任何可对齐段落")
    status = "failed" if missing or not output_paras or translation.get("corpus_sha256") != corpus.get("corpus_sha256") else "issues" if errors or warnings else "pass"
    verification = {"status": status, "errors": errors, "warnings": warnings,
                    "source_blocks": len(source_ids), "aligned_blocks": len(output_paras), "missing_blocks": missing,
                    "protected_token_violations": total_violations,
                    "glossary_checks": len(glossary_rows),
                    "glossary_consistent_checks": sum(x["ok"] for x in glossary_rows),
                    "metadata_ok": not metadata_errors,
                    "semantic_fidelity": "not_checked_by_tool",
                    "note": "通过只代表结构、哈希、受保护 token、表格形状与词表一致；不替代人工/模型语义审校"}
    return {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION, "kind": "aligned_bilingual",
            "source": corpus["source"], "metadata": corpus["metadata"], "corpus_sha256": corpus["corpus_sha256"],
            "full_text_sha256": corpus["full_text_sha256"], "extraction_status": corpus["extraction_status"],
            "extraction_issues": corpus.get("issues", []), "coverage": corpus.get("coverage", {}),
            "paragraphs": output_paras, "glossary": glossary, "verification": verification}


def command_extract(args):
    try:
        corpus = extract_document(args.snapshot, args.meta)
        write_json(args.out, corpus)
        return emit({"ok": corpus["extraction_status"] != "failed", "status": corpus["extraction_status"],
                     "out": args.out, "coverage": corpus["coverage"], "issues": corpus["issues"],
                     "corpus_sha256": corpus["corpus_sha256"]}, 0 if corpus["extraction_status"] != "failed" else 1)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "status": "failed", "failure": {"kind": "extract_error", "signal": str(exc),
                     "action": "保留快照与错误；标 failed/partial，不生成伪造正文"}}, 1)


def command_align(args):
    try:
        corpus = load_json(args.corpus)
        translation = load_json(args.translation)
        bilingual = align_document(corpus, translation)
        write_json(args.out, bilingual)
        verification = bilingual["verification"]
        return emit({"ok": not verification["errors"] and not verification["warnings"] and not bilingual["extraction_issues"],
                     "status": verification["status"], "out": args.out, "verification": verification,
                     "extraction_issues": bilingual["extraction_issues"]}, 0 if not verification["errors"] and not verification["warnings"] and not bilingual["extraction_issues"] else 1)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "status": "failed", "failure": {"kind": "alignment_interrupted", "signal": str(exc),
                     "action": "保留已写译文并按 id 断点补齐；不重排、不空缺冒充完成"}}, 1)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fetch", help="有界抓取真实 http/https 页面并保存字节级哈希")
    p.add_argument("url"); p.add_argument("--out", required=True); p.add_argument("--meta", required=True)
    p.add_argument("--timeout", type=float, default=20); p.add_argument("--max-bytes", type=int, default=8000000)
    p = sub.add_parser("stamp", help="登记浏览器/题面提供快照的真实来源与 sha256")
    p.add_argument("snapshot"); p.add_argument("--url", required=True); p.add_argument("--out", required=True)
    p.add_argument("--capture-method", choices=["browser_rendered", "provided_snapshot"], required=True)
    p.add_argument("--encoding", default="utf-8"); p.add_argument("--capture-notes", default="")
    p = sub.add_parser("extract", help="从正文 DOM 切块并保留 quote/location/hash")
    p.add_argument("snapshot"); p.add_argument("--meta", required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("align", help="校验逐段译文、公式数字单位、表格、术语并输出双语产物")
    p.add_argument("corpus"); p.add_argument("translation"); p.add_argument("--out", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "fetch":
        return fetch_page(args.url, args.out, args.meta, args.timeout, args.max_bytes)
    if args.command == "stamp":
        return stamp_snapshot(args.snapshot, args.url, args.out, args.capture_method, args.encoding, args.capture_notes)
    if args.command == "extract":
        return command_extract(args)
    if args.command == "align":
        return command_align(args)
    return 2


def entrypoint():
    try:
        return main()
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, json.JSONDecodeError) as exc:
        return emit({"ok": False, "status": "failed", "failure": {"kind": "field_type_error",
                     "signal": str(exc), "action": "修正实际输入类型/路径；不得填假值或静默跳过"}, "tool_version": TOOL_VERSION}, 1)


if __name__ == "__main__":
    sys.exit(entrypoint())
