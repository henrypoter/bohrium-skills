#!/usr/bin/env python3
"""科研知识库问答/证据定位工具（纯 Python 标准库）。

  index <dir> [--text-dir extracted/] [--versions versions.json] [--output index.json]
      建立带来源、权限、完整 SHA-256、版本角色和页/段/行坐标的全文索引。
      PDF/扫描件需先有逐来源文本侧车；无文本、不可读、空目录和版本冲突均显式报告。
  search <index.json> --query QUERY [--limit N] [--include-history] [--path PREFIX]
      在当前 canonical 文档中检索；返回可直接用于引用的原文和精确坐标。
  qacheck <result.json> --index index.json
      逐论断核对文件、内容版本、版本标签/角色、chunk、原文子串和页段行坐标；
      同时检查缺证回答的 missing/search 记录、证据冲突及索引异常是否均已交代。

退出码：index 在完全不可检索时 1，部分可检索但有 issues 时 0；qacheck 有错 1；
参数/IO/JSON 错误 2。search 无命中是合法的 no_evidence，不当作工具故障。
"""
import datetime as dt
import hashlib
import html.parser
import json
import os
import re
import stat
import sys
import zipfile
import xml.etree.ElementTree as ET

TOOL_VERSION = "1.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TEXT_EXTS = {".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml",
             ".xml", ".html", ".htm", ".tex", ".r", ".py", ".c", ".h", ".cpp", ".java", ".js"}
VERSION_RE = re.compile(r"(?i)(?:^|[_\-\s])(v\d+|ver\d+|rev\d+|final|draft)(?:$|[_\-\s.])")
VER_TOKENS = re.compile(
    r"(?i)(?:[_\-\s]?(?:v|ver|rev|final|draft|copy)\d*|[_\-\s]?\(\d+\)|[_\-\s]?\d{8})"
)


def _emit(data, output=None):
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        parent = os.path.dirname(os.path.abspath(output))
        os.makedirs(parent, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(json.dumps({"ok": data.get("ok", False), "status": data.get("status"),
                          "output": output, "index_sha256": data.get("index_sha256"),
                          "documents": data.get("n_documents"),
                          "searchable_documents": data.get("searchable_documents")},
                         ensure_ascii=False))
    else:
        print(text, end="")


def _sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _fingerprint(data):
    payload = {key: value for key, value in data.items() if key not in {"index_sha256", "ok", "status"}}
    return _sha_bytes(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")).encode("utf-8"))


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _mode(value):
    return "%04o" % stat.S_IMODE(value)


def _version_label(path, explicit=None):
    if explicit and path in explicit:
        return str(explicit[path])
    match = VERSION_RE.search(os.path.basename(path))
    return match.group(1).lower() if match else "unversioned"


def _base(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"\s+", " ", VER_TOKENS.sub("", stem)).strip().lower()


class _HTMLText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.ignored += 1
        elif tag.lower() in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style"} and self.ignored:
            self.ignored -= 1
        elif tag.lower() in {"p", "div", "li", "tr", "h1", "h2", "h3", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def _html_text(data):
    parser = _HTMLText()
    parser.feed(data.decode("utf-8-sig"))
    parser.close()
    return "".join(parser.parts)


def _docx_text(path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        text = "".join(node.text or "" for node in paragraph.iter(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs)


def _pdf_pages(path):
    try:
        with open(path, "rb") as fh:
            head = fh.read(2 * 1024 * 1024)
        return len(re.findall(rb"/Type\s*/Page\b", head))
    except OSError:
        return 0


def _paragraphs(text):
    """返回原文段落；行号相对提取文本，页码按 form feed（pdftotext 常用）。"""
    # str.splitlines() 会把 form feed 当作换行并吞掉页界，必须只按换行符切分。
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks, buf = [], []
    start_line = start_page = None
    line_no = 0
    page = 1

    def flush(end_line, end_page):
        nonlocal buf, start_line, start_page
        if buf:
            content = "\n".join(part for _, part in buf)
            blocks.append({"text": content, "start_line": start_line, "end_line": end_line,
                           "start_page": start_page, "end_page": end_page})
        buf, start_line, start_page = [], None, None

    for raw in lines:
        line_no += 1
        pieces = raw.split("\f")
        for index, piece in enumerate(pieces):
            if index:
                flush(line_no - 1, page)
                page += 1
            if not piece.strip():
                flush(line_no - 1, page)
                continue
            if not buf:
                start_line, start_page = line_no, page
            buf.append((line_no, piece))
        if raw.endswith("\f"):
            flush(line_no, page)
    flush(line_no, page)
    return blocks


def _load_versions(path):
    if not path:
        return {"chains": {}, "file_versions": {}}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not isinstance(data.get("chains", {}), dict):
        raise ValueError("versions JSON 必须含 chains 对象")
    return {"chains": data.get("chains", {}), "file_versions": data.get("file_versions", {})}


def _build_index(root, text_dir=None, versions_path=None):
    anomalies, documents, directories = [], [], []
    if not os.path.isdir(root):
        return {"ok": False, "status": "failed", "tool_version": TOOL_VERSION, "root": root,
                "n_documents": 0, "searchable_documents": 0, "documents": [], "chunks": [],
                "duplicate_groups": [], "version_candidates": [],
                "anomalies": [{"type": "directory_missing", "path": root, "status": "blocked",
                               "recovery": "确认实际输入目录后重跑 index"}]}
    root = os.path.abspath(root)
    text_root = os.path.abspath(text_dir) if text_dir else None
    try:
        version_config = _load_versions(versions_path)
    except (OSError, ValueError) as exc:
        return {"ok": False, "status": "failed", "tool_version": TOOL_VERSION, "root": root,
                "n_documents": 0, "searchable_documents": 0, "documents": [], "chunks": [],
                "duplicate_groups": [], "version_candidates": [],
                "anomalies": [{"type": "versions_unreadable", "path": versions_path,
                               "status": "blocked", "detail": str(exc)}]}

    paths = []
    def onerror(exc):
        anomalies.append({"type": "directory_unreadable", "path": getattr(exc, "filename", root),
                          "status": "blocked", "detail": str(exc),
                          "recovery": "补充遍历权限后重跑 index；缺失范围不计为已检索"})
    for current, dirs, names in os.walk(root, onerror=onerror):
        kept = []
        for name in sorted(dirs):
            path = os.path.join(current, name)
            if os.path.islink(path):
                anomalies.append({"type": "directory_symlink", "path": _rel(path, root), "status": "open",
                                  "recovery": "确认目标、避免越界后改为实体目录"})
            else:
                kept.append(name)
        dirs[:] = kept
        for name in kept:
            directories.append(_rel(os.path.join(current, name), root))
        if not dirs and not names:
            rel = _rel(current, root)
            anomalies.append({"type": "directory_empty", "path": rel, "status": "open",
                              "recovery": "确认为空是真实状态还是资料未挂载；不声称已检索到答案"})
        for name in sorted(names):
            paths.append(os.path.join(current, name))

    by_hash = {}
    for path in sorted(paths):
        rel = _rel(path, root)
        ext = os.path.splitext(path)[1].lower()
        if os.path.islink(path):
            anomalies.append({"type": "file_symlink", "path": rel, "status": "open",
                              "recovery": "确认来源后用实体文件替换并重算哈希"})
            continue
        try:
            info = os.stat(path)
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            anomalies.append({"type": "file_unreadable", "path": rel, "status": "blocked", "detail": str(exc),
                              "recovery": "授权或重新提供文件；该文件排除在已检索范围之外"})
            continue
        digest = _sha_bytes(raw)
        document = {"doc_id": "doc-" + digest[:16], "path": rel, "sha256": digest, "size": len(raw),
                    "file_type": ext or "no_extension", "permissions": _mode(info.st_mode),
                    "mtime_ns": info.st_mtime_ns, "source": root,
                    "source_locator": os.path.join(root, *rel.split("/")),
                    "version": _version_label(rel, version_config["file_versions"]),
                    "base": _base(rel), "role": "current", "include_in_search": True,
                    "text_status": "pending", "text_source": None, "chunks": []}
        by_hash.setdefault(digest, []).append(rel)
        if not raw:
            document.update({"text_status": "empty_file", "include_in_search": False})
            anomalies.append({"type": "empty_file", "path": rel, "sha256": digest, "status": "open",
                              "recovery": "核对来源；若为空占位则说明，若漏采则重采"})
            documents.append(document)
            continue
        extracted, method, sidecar = None, None, None
        if text_root:
            candidates = [os.path.join(text_root, *rel.split("/")) + ".txt",
                          os.path.join(text_root, *(os.path.splitext(rel)[0] + ".txt").split("/"))]
            for candidate in candidates:
                if os.path.isfile(candidate):
                    sidecar = candidate
                    break
            if sidecar:
                try:
                    with open(sidecar, encoding="utf-8-sig") as fh:
                        extracted = fh.read()
                    method = "provided_text_sidecar"
                    document["text_source"] = _rel(sidecar, text_root)
                except (OSError, UnicodeDecodeError) as exc:
                    anomalies.append({"type": "extraction_unreadable", "path": rel, "status": "blocked",
                                      "detail": str(exc), "text_source": sidecar,
                                      "recovery": "重新提取为 UTF-8；保留页分隔符和提取方法"})
        if extracted is None and ext in TEXT_EXTS and not sidecar:
            try:
                extracted = _html_text(raw) if ext in {".html", ".htm"} else raw.decode("utf-8-sig")
                method = "stdlib_html_text" if ext in {".html", ".htm"} else "utf8_direct"
                document["text_source"] = rel
            except UnicodeDecodeError as exc:
                anomalies.append({"type": "text_decode_error", "path": rel, "sha256": digest,
                                  "status": "blocked", "detail": str(exc),
                                  "recovery": "确认原编码，转为带回链的 UTF-8 侧车后重跑；不得替换坏字符"})
        elif extracted is None and ext == ".docx" and not sidecar:
            try:
                extracted = _docx_text(path)
                method = "stdlib_docx_xml"
                document["text_source"] = rel + "#word/document.xml"
            except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
                anomalies.append({"type": "file_unreadable", "path": rel, "sha256": digest,
                                  "status": "blocked", "detail": str(exc),
                                  "recovery": "修复 DOCX/ZIP 或提供有来源定位的文本侧车"})
        if extracted is None and not any(a.get("path") == rel and a.get("status") == "blocked" for a in anomalies):
            issue = "text_extraction_required" if ext == ".pdf" else "unsupported_text_extraction"
            anomalies.append({"type": issue, "path": rel, "sha256": digest, "status": "blocked",
                              "recovery": "用实际可用工具提取/OCR为 UTF-8 侧车，记录方法；PDF 页间用 form feed"})
        if extracted is not None:
            if not extracted.strip():
                document.update({"text_status": "no_text", "include_in_search": False})
                issue = "scanned_no_text" if ext == ".pdf" else "empty_text"
                anomalies.append({"type": issue, "path": rel, "sha256": digest, "status": "blocked",
                                  "text_source": document.get("text_source"), "pdf_page_markers": _pdf_pages(path),
                                  "recovery": "扫描件执行 OCR 并抽样核对；仍无文本则标 no_evidence，不猜测"})
            else:
                blocks = _paragraphs(extracted)
                document["extraction_method"] = method
                for number, block in enumerate(blocks, 1):
                    locator = {"page": block["start_page"] if method == "provided_text_sidecar" and ext == ".pdf" else None,
                               "paragraph": number, "start_line": block["start_line"], "end_line": block["end_line"]}
                    if block["end_page"] != block["start_page"] and locator["page"] is not None:
                        locator["end_page"] = block["end_page"]
                    chunk_id = "%s:p%04d" % (document["doc_id"], number)
                    document["chunks"].append({"chunk_id": chunk_id, "locator": locator,
                                               "text": block["text"], "text_sha256": _sha_bytes(block["text"].encode("utf-8"))})
                if blocks:
                    document["text_status"] = "searchable"
                else:
                    document.update({"text_status": "no_text", "include_in_search": False})
                    anomalies.append({"type": "empty_text", "path": rel, "status": "blocked",
                                      "recovery": "重新提取/OCR；不得将不可检索写成无答案依据"})
        else:
            document.update({"text_status": "unavailable", "include_in_search": False})
        documents.append(document)

    duplicates = []
    for digest, group in sorted(by_hash.items()):
        if len(group) < 2:
            continue
        ordered = sorted(group)
        canonical = ordered[0]
        duplicates.append({"sha256": digest, "canonical": canonical, "duplicates": ordered[1:], "files": ordered})
        for document in documents:
            if document["path"] in ordered[1:]:
                document.update({"role": "duplicate", "include_in_search": False, "duplicate_of": canonical})

    # 同 base 且内容不同才是版本候选；纯重复副本不形成版本冲突。
    groups = {}
    for document in documents:
        groups.setdefault(document["base"], []).append(document)
    candidates = []
    for base, group in sorted(groups.items()):
        distinct = {document["sha256"]: document for document in group}
        if len(distinct) < 2:
            continue
        ordered = sorted(distinct.values(), key=lambda d: (d["mtime_ns"], d["path"]))
        candidates.append({"base": base, "current_candidate": ordered[-1]["path"],
                           "files": [{"path": d["path"], "sha256": d["sha256"], "version": d["version"],
                                      "mtime_ns": d["mtime_ns"]} for d in ordered],
                           "basis": ["normalized_base", "distinct_sha256", "mtime_ns"]})
    candidate_bases = {candidate["base"] for candidate in candidates}
    doc_by_path = {document["path"]: document for document in documents}
    declared_bases = set()
    for base, chain in version_config["chains"].items():
        if not isinstance(chain, dict):
            anomalies.append({"type": "versions_invalid", "path": base, "status": "blocked",
                              "detail": "chain 必须是对象"})
            continue
        current, history = chain.get("current"), chain.get("history", [])
        if current not in doc_by_path or not isinstance(history, list) or any(p not in doc_by_path for p in history):
            anomalies.append({"type": "versions_invalid", "path": base, "status": "blocked",
                              "recovery": "current/history 必须都是 index 中的实际相对路径"})
            continue
        if current in history or not history:
            anomalies.append({"type": "versions_invalid", "path": base, "status": "blocked",
                              "recovery": "history 至少一个且不得包含 current"})
            continue
        declared_bases.add(base)
        for old in history:
            if doc_by_path[old]["sha256"] == doc_by_path[current]["sha256"]:
                anomalies.append({"type": "versions_invalid", "path": old, "status": "blocked",
                                  "recovery": "相同内容应记 duplicate，不得伪作历史版本"})
                continue
            doc_by_path[old].update({"role": "history", "include_in_search": False, "superseded_by": current})
        doc_by_path[current].update({"role": "current", "supersedes": history})
    for candidate in candidates:
        if candidate["base"] not in declared_bases:
            anomalies.append({"type": "version_conflict", "path": candidate["base"], "status": "open",
                              "candidates": candidate["files"],
                              "recovery": "提供 versions.json 声明 current/history，或在冲突答案中分版本并列证据"})

    all_chunks = []
    for document in sorted(documents, key=lambda d: d["path"]):
        for chunk in document.pop("chunks"):
            chunk.update({"doc_id": document["doc_id"], "path": document["path"],
                          "sha256": document["sha256"], "version": document["version"], "role": document["role"],
                          "include_in_search": document["include_in_search"]})
            all_chunks.append(chunk)
    result = {"tool_version": TOOL_VERSION, "root": root, "text_root": text_root,
              "versions_file": os.path.abspath(versions_path) if versions_path else None,
              "n_documents": len(documents),
              "searchable_documents": sum(1 for d in documents if d["include_in_search"] and d["text_status"] == "searchable"),
              "readable_documents": sum(1 for d in documents if d["text_status"] == "searchable"),
              "directories": sorted(directories), "documents": sorted(documents, key=lambda d: d["path"]),
              "chunks": all_chunks, "duplicate_groups": duplicates, "version_candidates": candidates,
              "anomalies": anomalies,
              "search_policy": "默认仅 include_in_search=true 的 current canonical 文档；history/duplicate 可显式引用，不默认合并",
              "coordinate_policy": "行号相对提取文本；PDF page 仅在带 form feed 的来源侧车中给出，否则为 null，不猜页码"}
    result["index_sha256"] = _fingerprint(result)
    result["status"] = "failed" if result["searchable_documents"] == 0 else ("issues" if anomalies else "pass")
    result["ok"] = result["status"] != "failed"
    return result


def cmd_index(root, text_dir=None, versions_path=None, output=None):
    result = _build_index(root, text_dir, versions_path)
    _emit(result, output)
    return 0 if result.get("ok") else 1


def _load_index(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict) or not SHA256_RE.fullmatch(str(data.get("index_sha256", ""))):
        raise ValueError("索引缺完整 index_sha256")
    actual = _fingerprint(data)
    if actual != data["index_sha256"]:
        raise ValueError("索引指纹不符：文件被修改或损坏；从原资料重跑 index")
    return data


def _query_terms(query):
    weighted = {}
    for match in re.finditer(r"[\u4e00-\u9fff]+|[A-Za-z0-9_]+", query.casefold()):
        token = match.group(0)
        if not token:
            continue
        weight = max(1, min(4, len(token) // 2)) if re.search(r"[\u4e00-\u9fff]", token) else 2
        weighted[token] = max(weighted.get(token, 0), weight)
        if len(token) > 2 and re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for index in range(len(token) - 1):
                bigram = token[index:index + 2]
                weighted[bigram] = max(weighted.get(bigram, 0), 1)
    return weighted


def cmd_search(index_path, query, limit=8, include_history=False, path_prefix=None):
    try:
        index = _load_index(index_path)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "status": "failed", "error": str(exc)})
        return 2
    if not query.strip():
        _emit({"ok": False, "status": "failed", "error": "query 不能为空"})
        return 2
    terms = _query_terms(query)
    hits = []
    excluded = {"history": 0, "duplicate": 0, "unreadable_or_empty": 0, "path_filter": 0}
    for chunk in index.get("chunks", []):
        if path_prefix and not chunk["path"].startswith(path_prefix):
            excluded["path_filter"] += 1
            continue
        if not chunk["include_in_search"]:
            if chunk["role"] == "history" and include_history:
                pass
            else:
                key = chunk["role"] if chunk["role"] in {"history", "duplicate"} else "unreadable_or_empty"
                excluded[key] += 1
                continue
        text_fold = chunk["text"].casefold()
        matched = {term: text_fold.count(term) for term in terms if text_fold.count(term)}
        if not matched:
            continue
        score = sum(terms[term] * count for term, count in matched.items())
        hits.append({"score": score, "matched_terms": sorted(matched), "doc_id": chunk["doc_id"],
                     "path": chunk["path"], "sha256": chunk["sha256"], "version": chunk["version"],
                     "role": chunk["role"], "chunk_id": chunk["chunk_id"], "locator": chunk["locator"],
                     "quote": chunk["text"], "text_sha256": chunk["text_sha256"]})
    hits.sort(key=lambda hit: (-hit["score"], hit["path"], hit["chunk_id"]))
    status = "ok" if hits else "no_evidence"
    _emit({"ok": True, "status": status, "query": query, "index_sha256": index["index_sha256"],
           "include_history": include_history, "path_prefix": path_prefix, "terms": sorted(terms),
           "hits": hits[:max(1, min(100, int(limit)))], "hit_count": len(hits), "excluded_chunks": excluded,
           "missing": [] if hits else ["当前索引范围内没有包含查询词的段落；需扩大已读资料范围或明确回答无依据"],
           "scope": {"root": index["root"], "searchable_documents": index["searchable_documents"]}})
    return 0


def _check_citation(citation, chunks_by_id, docs_by_path, label, errors):
    if not isinstance(citation, dict):
        errors.append(label + " 必须是对象")
        return
    for key in ("path", "sha256", "version", "role", "chunk_id", "quote", "locator"):
        if key not in citation or citation[key] in (None, ""):
            errors.append("%s 缺或空 %s" % (label, key))
    chunk = chunks_by_id.get(citation.get("chunk_id"))
    document = docs_by_path.get(citation.get("path"))
    if not chunk or not document or chunk["path"] != citation.get("path"):
        errors.append(label + " 的 path/chunk_id 无法在索引中回链")
        return
    if citation.get("sha256") != document["sha256"] or citation.get("sha256") != chunk["sha256"]:
        errors.append(label + " 内容 sha256 与索引版本不符")
    if citation.get("version") != document["version"]:
        errors.append(label + " version 与索引不符")
    if citation.get("role") != chunk["role"]:
        errors.append(label + " role 与索引不符")
    if not isinstance(citation.get("quote"), str) or not citation["quote"] or citation["quote"] not in chunk["text"]:
        errors.append(label + " quote 不是目标 chunk 原文的精确子串")
    locator = citation.get("locator")
    if not isinstance(locator, dict):
        errors.append(label + " locator 必须是对象")
    else:
        for key in ("page", "paragraph", "start_line", "end_line"):
            if key not in locator:
                errors.append("%s locator 缺 %s" % (label, key))
            elif locator[key] != chunk["locator"].get(key):
                errors.append("%s locator.%s 与原文坐标不符" % (label, key))


def cmd_qacheck(result_path, index_path):
    try:
        index = _load_index(index_path)
        with open(result_path, encoding="utf-8") as fh:
            result = json.load(fh)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "errors": ["输入无法读取/解析或索引损坏: %s" % exc]})
        return 2
    if not isinstance(result, dict):
        _emit({"ok": False, "errors": ["result 顶层必须是对象"]})
        return 1
    errors, warnings = [], []
    for key in ("case_id", "status", "answers", "exceptions", "conflicts", "scope", "run",
                "sources", "uncertainty", "change_log"):
        if key not in result:
            errors.append("缺顶层字段 " + key)
    if result.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    scope = result.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope 必须是对象")
        scope = {}
    for key in ("index_sha256", "searched_documents", "excluded_documents", "include_history"):
        if key not in scope:
            errors.append("scope 缺 " + key)
    if scope.get("index_sha256") != index.get("index_sha256"):
        errors.append("scope.index_sha256 与实际索引不符")
    actual_doc_paths = {document.get("path") for document in index.get("documents", [])}
    for key in ("searched_documents", "excluded_documents"):
        if not isinstance(scope.get(key), list):
            errors.append("scope.%s 必须是数组" % key)
        else:
            for path in scope[key]:
                if path not in actual_doc_paths:
                    errors.append("scope.%s 含索引外路径: %s" % (key, path))
    run = result.get("run")
    if not isinstance(run, dict):
        errors.append("run 必须是对象")
        run = {}
    for key in ("tool_version", "commands", "input_root", "started_at", "completed_at"):
        if key not in run or run[key] in (None, "", []):
            errors.append("run 缺或空 " + key)
    commands = run.get("commands", [])
    if not isinstance(commands, list):
        errors.append("run.commands 必须是数组")
        commands = []

    docs_by_path = {document["path"]: document for document in index.get("documents", [])}
    chunks_by_id = {chunk["chunk_id"]: chunk for chunk in index.get("chunks", [])}
    answers = result.get("answers", [])
    if not isinstance(answers, list) or not answers:
        errors.append("answers 必须是非空数组")
        answers = []
    verified_claims = verified_citations = no_evidence_answers = conflict_answers = 0
    for ai, answer in enumerate(answers):
        label = "answers[%d]" % ai
        if not isinstance(answer, dict):
            errors.append(label + " 必须是对象")
            continue
        for key in ("question", "answer", "status", "claims"):
            if key not in answer:
                errors.append(label + " 缺 " + key)
        answer_status = answer.get("status")
        if answer_status not in {"answered", "no_evidence", "conflict", "partial"}:
            errors.append(label + " status 非法")
        claims = answer.get("claims", [])
        if not isinstance(claims, list):
            errors.append(label + ".claims 必须是数组")
            continue
        if answer_status in {"answered", "conflict"} and not claims:
            errors.append(label + " 已回答/冲突状态必须至少一个关键论断")
        if answer_status == "no_evidence":
            no_evidence_answers += 1
            if claims:
                errors.append(label + " no_evidence 不得同时存在无证据claims；有证据应拆成partial")
            if not answer.get("missing"):
                errors.append(label + " no_evidence 必须说明 missing（缺什么资料/证据）")
            if not any("search" in str(command) for command in commands):
                errors.append(label + " no_evidence 的 run.commands 缺实际 search 记录")
        if answer_status == "partial" and not answer.get("missing"):
            errors.append(label + " partial 必须说明 missing")
        if answer_status == "conflict":
            conflict_answers += 1
        for ci, claim in enumerate(claims):
            clabel = "%s.claims[%d]" % (label, ci)
            if not isinstance(claim, dict):
                errors.append(clabel + " 必须是对象")
                continue
            for key in ("claim_id", "text", "evidence"):
                if key not in claim or claim[key] in (None, "", []):
                    errors.append(clabel + " 缺或空 " + key)
            evidence = claim.get("evidence", [])
            if not isinstance(evidence, list) or not evidence:
                errors.append(clabel + " 每个关键论断必须至少一条证据")
                continue
            verified_claims += 1
            for ei, citation in enumerate(evidence):
                _check_citation(citation, chunks_by_id, docs_by_path,
                                "%s.evidence[%d]" % (clabel, ei), errors)
                verified_citations += 1

    conflicts = result.get("conflicts", [])
    if not isinstance(conflicts, list):
        errors.append("conflicts 必须是数组")
        conflicts = []
    if conflict_answers and not conflicts:
        errors.append("存在 conflict 答案但顶层 conflicts 为空")
    for ci, conflict in enumerate(conflicts):
        label = "conflicts[%d]" % ci
        if not isinstance(conflict, dict):
            errors.append(label + " 必须是对象")
            continue
        for key in ("topic", "status", "explanation", "evidence"):
            if key not in conflict or conflict[key] in (None, "", []):
                errors.append(label + " 缺或空 " + key)
        if conflict.get("status") not in {"unresolved", "resolved"}:
            errors.append(label + " status 非法")
        if conflict.get("status") == "resolved" and not conflict.get("resolution"):
            errors.append(label + " resolved 必须有独立依据的 resolution")
        evidence = conflict.get("evidence", [])
        if not isinstance(evidence, list) or len(evidence) < 2:
            errors.append(label + " 至少两条互相独立的证据坐标")
            continue
        anchors = set()
        for ei, citation in enumerate(evidence):
            _check_citation(citation, chunks_by_id, docs_by_path,
                            "%s.evidence[%d]" % (label, ei), errors)
            if isinstance(citation, dict):
                anchors.add((citation.get("path"), citation.get("sha256"), citation.get("chunk_id")))
        if len(anchors) < 2:
            errors.append(label + " 冲突证据不能重复指向同一锚点")

    exceptions = result.get("exceptions", [])
    if not isinstance(exceptions, list):
        errors.append("exceptions 必须是数组")
        exceptions = []
    exception_records = {}
    for ei, exception in enumerate(exceptions):
        label = "exceptions[%d]" % ei
        if not isinstance(exception, dict):
            errors.append(label + " 必须是对象")
            continue
        for key in ("type", "path", "status", "action", "recovery"):
            if key not in exception:
                errors.append(label + " 缺 " + key)
        if exception.get("status") not in {"resolved", "open", "blocked"}:
            errors.append(label + " status 非法")
        exception_records.setdefault((exception.get("type"), exception.get("path")), []).append(exception)
        if result.get("status") == "pass" and exception.get("status") != "resolved":
            errors.append("status=pass 但 %s 未解决" % label)
    for anomaly in index.get("anomalies", []):
        key = (anomaly.get("type"), anomaly.get("path"))
        matches = exception_records.get(key, [])
        if not matches:
            errors.append("索引异常未在 result.exceptions 交代: %s %s" % key)
        elif any(exception.get("status") == "resolved" for exception in matches):
            errors.append("索引仍存在异常但 exceptions 错写 resolved: %s %s；修复后须重跑 index" % key)
    for citation in []:  # 预留：语义蕴含仍需人工核对，不宣称字符串匹配等于科学正确。
        warnings.append(citation)
    if index.get("version_candidates"):
        warnings.append("存在版本候选；qacheck 只核对显式版本坐标，不自动裁决版本语义")
    if errors:
        _emit({"ok": False, "errors": errors, "warnings": warnings,
               "verified_claims": verified_claims, "verified_citations": verified_citations})
        return 1
    _emit({"ok": True, "verified_claims": verified_claims, "verified_citations": verified_citations,
           "no_evidence_answers": no_evidence_answers, "conflict_answers": conflict_answers,
           "checked_exceptions": len(exceptions), "index_sha256": index["index_sha256"],
           "warnings": warnings,
           "limit": "已验证引文存在性与坐标；论断-原文语义蕴含仍需逐条人工/模型复核"})
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    command, args = argv[0], argv[1:]
    try:
        if command == "index" and args:
            return cmd_index(args[0],
                             args[args.index("--text-dir") + 1] if "--text-dir" in args else None,
                             args[args.index("--versions") + 1] if "--versions" in args else None,
                             args[args.index("--output") + 1] if "--output" in args else None)
        if command == "search" and len(args) >= 3 and "--query" in args:
            return cmd_search(args[0], args[args.index("--query") + 1],
                              int(args[args.index("--limit") + 1]) if "--limit" in args else 8,
                              "--include-history" in args,
                              args[args.index("--path") + 1] if "--path" in args else None)
        if command == "qacheck" and len(args) >= 3 and "--index" in args:
            return cmd_qacheck(args[0], args[args.index("--index") + 1])
    except (IndexError, OSError, ValueError) as exc:
        _emit({"ok": False, "error": "参数或运行错误", "detail": str(exc)})
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
