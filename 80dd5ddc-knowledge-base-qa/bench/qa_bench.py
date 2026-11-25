#!/usr/bin/env python3
"""qa_tool 合成 bench：正常证据零误杀，坏坐标/缺证/版本/冲突/异常变异必命中。"""
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.abspath(os.path.join(HERE, "..", "scripts", "qa_tool.py"))
TMP = tempfile.mkdtemp(prefix="qa-tool-bench-")
checks = []


def put(path, content="", binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if binary:
        with open(path, "wb") as fh:
            fh.write(content)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return path


def dump(path, data):
    return put(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:500], "stderr": proc.stderr[:500]}


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


def base_result(index):
    return {"case_id": "synthetic-qa", "status": "pass",
            "answers": [], "exceptions": [], "conflicts": [],
            "scope": {"index_sha256": index["index_sha256"],
                      "searched_documents": [d["path"] for d in index["documents"]
                                             if d["include_in_search"] and d["text_status"] == "searchable"],
                      "excluded_documents": [d["path"] for d in index["documents"]
                                             if not (d["include_in_search"] and d["text_status"] == "searchable")],
                      "include_history": False},
            "run": {"tool_version": "1.0.0",
                    "commands": ["qa_tool.py index library --versions versions.json",
                                 "qa_tool.py search index.json --query 温度"],
                    "input_root": index["root"], "started_at": "2026-01-02T03:00:00Z",
                    "completed_at": "2026-01-02T03:05:00Z"},
            "sources": ["synthetic-bench"], "uncertainty": [], "change_log": []}


# 正常库：重复副本不能成为独立证据；显式版本链隔离 history。
ROOT = os.path.join(TMP, "library")
v1 = put(os.path.join(ROOT, "docs", "report_v1.txt"), "实验设置温度为 41 °C。\n\n旧版两次重复。")
v2 = put(os.path.join(ROOT, "docs", "report_v2.txt"), "实验设置温度为 42 °C。\n\n新版三次重复，仪器型号为 A。")
notes = put(os.path.join(ROOT, "notes.txt"), "项目 P1 的采样日期为 2026-01-02。")
put(os.path.join(ROOT, "notes_copy.txt"), "项目 P1 的采样日期为 2026-01-02。")
versions = dump(os.path.join(TMP, "versions.json"), {
    "chains": {"report": {"current": "docs/report_v2.txt", "history": ["docs/report_v1.txt"]}},
    "file_versions": {"notes.txt": "snapshot-2026", "notes_copy.txt": "snapshot-2026"}})
INDEX = os.path.join(TMP, "index.json")
rc, summary = run("index", ROOT, "--versions", versions, "--output", INDEX)
with open(INDEX, encoding="utf-8") as fh:
    index = json.load(fh)
add("index正向:可检索且来源权限完整", rc == 0 and index.get("status") == "pass"
    and index.get("n_documents") == 4 and index.get("searchable_documents") == 2
    and all(len(d["sha256"]) == 64 and d.get("permissions") and d.get("source_locator")
            for d in index.get("documents", [])), str(summary)[:300])
add("index正向:内容重复只留canonical检索", len(index.get("duplicate_groups", [])) == 1
    and next(d for d in index["documents"] if d["path"] == "notes_copy.txt")["role"] == "duplicate",
    str(index.get("duplicate_groups"))[:250])
add("index正向:历史版本默认退出检索", next(d for d in index["documents"] if d["path"] == "docs/report_v1.txt")["role"] == "history"
    and next(d for d in index["documents"] if d["path"] == "docs/report_v2.txt").get("supersedes") == ["docs/report_v1.txt"],
    str(index.get("documents"))[:300])
first_fingerprint = index["index_sha256"]
rc, _ = run("index", ROOT, "--versions", versions, "--output", os.path.join(TMP, "index2.json"))
with open(os.path.join(TMP, "index2.json"), encoding="utf-8") as fh:
    second = json.load(fh)
add("index正向:同输入复跑指纹稳定零误报", first_fingerprint == second.get("index_sha256")
    and not index.get("anomalies"), str(first_fingerprint))

# PDF 文本侧车与扫描件/无文本/空目录。
PDFROOT = os.path.join(TMP, "pdf-library")
put(os.path.join(PDFROOT, "paper.pdf"), b"%PDF-1.4\n/Type /Page\n/Type /Page\n%%EOF", binary=True)
PDFTEXT = os.path.join(TMP, "pdf-text")
put(os.path.join(PDFTEXT, "paper.pdf.txt"), "第一页设置温度为 42 °C。\n\f第二页相对湿度为 50%。\n\f")
rc, pdf = run("index", PDFROOT, "--text-dir", PDFTEXT)
add("index正向:PDF侧车保留页码且不误报扫描", rc == 0 and pdf.get("searchable_documents") == 1
    and [c["locator"]["page"] for c in pdf.get("chunks", [])] == [1, 2]
    and pdf["documents"][0]["extraction_method"] == "provided_text_sidecar", str(pdf)[:300])
EMPTY = os.path.join(TMP, "empty")
os.makedirs(EMPTY)
rc, empty = run("index", EMPTY)
add("index变异:目录为空必命中", rc == 1 and empty.get("status") == "failed"
    and any(a["type"] == "directory_empty" for a in empty.get("anomalies", [])), str(empty)[:250])
SCAN = os.path.join(TMP, "scan")
put(os.path.join(SCAN, "scan.pdf"), b"%PDF-1.4\n/Type /Page\n%%EOF", binary=True)
SCANTEXT = os.path.join(TMP, "scan-text")
put(os.path.join(SCAN, "placeholder.txt"), "占位") if False else None
put(os.path.join(SCANTEXT, "scan.pdf.txt"), " \n\n")
rc, scan = run("index", SCAN, "--text-dir", SCANTEXT)
add("index变异:扫描件无文本必命中", rc == 1 and any(a["type"] == "scanned_no_text"
    for a in scan.get("anomalies", [])), str(scan)[:300])
rc, noextract = run("index", SCAN)
add("index变异:PDF无提取文本不伪造内容", rc == 1 and any(a["type"] == "text_extraction_required"
    for a in noextract.get("anomalies", [])), str(noextract)[:250])
BADTEXT = os.path.join(TMP, "bad-text")
put(os.path.join(BADTEXT, "bad.txt"), b"\xff\xfe\x00", binary=True)
rc, badtext = run("index", BADTEXT)
add("index变异:文件文本不可读必命中", rc == 1 and any(a["type"] == "text_decode_error"
    for a in badtext.get("anomalies", [])), str(badtext)[:250])

# DOCX 纯标准库 XML 提取正向。
DOCXROOT = os.path.join(TMP, "docx")
docx_path = os.path.join(DOCXROOT, "memo.docx")
os.makedirs(DOCXROOT)
document_xml = """<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>DOCX 内设置温度为 43 °C。</w:t></w:r></w:p></w:body></w:document>"""
with zipfile.ZipFile(docx_path, "w") as zf:
    zf.writestr("word/document.xml", document_xml)
rc, docx = run("index", DOCXROOT)
add("index正向:DOCX可检索且不误杀", rc == 0 and docx.get("searchable_documents") == 1
    and "43" in docx["chunks"][0]["text"], str(docx)[:250])

# 无 versions 声明的同 base 不同哈希必须成为版本冲突。
CONFLICTROOT = os.path.join(TMP, "version-conflict")
put(os.path.join(CONFLICTROOT, "report_v1.txt"), "阈值是 10。")
put(os.path.join(CONFLICTROOT, "report_v2.txt"), "阈值是 20。")
CONFLICTINDEX = os.path.join(TMP, "conflict-index.json")
rc, _ = run("index", CONFLICTROOT, "--output", CONFLICTINDEX)
with open(CONFLICTINDEX, encoding="utf-8") as fh:
    conflict_index = json.load(fh)
add("index变异:版本冲突必命中", any(a["type"] == "version_conflict"
    for a in conflict_index.get("anomalies", [])), str(conflict_index)[:300])

# 检索默认 current canonical，显示历史需显式开关；无命中是 no_evidence。
rc, hits = run("search", INDEX, "--query", "设置温度")
add("search正向:关键论断回链当前版本坐标", rc == 0 and hits.get("status") == "ok"
    and hits.get("hit_count") == 1 and hits["hits"][0]["path"] == "docs/report_v2.txt"
    and hits["hits"][0]["locator"]["paragraph"] == 1
    and "42" in hits["hits"][0]["quote"], str(hits)[:350])
rc, nohit = run("search", INDEX, "--query", "绝不存在词XYZQ")
add("search变异:库内无依据显式no_evidence", rc == 0 and nohit.get("status") == "no_evidence"
    and nohit.get("hits") == [] and nohit.get("missing"), str(nohit)[:250])
rc, history_hits = run("search", INDEX, "--query", "设置温度", "--include-history")
add("search异常:历史版本仅显式纳入", rc == 0 and history_hits.get("hit_count") == 2
    and {h["role"] for h in history_hits["hits"]} == {"current", "history"}, str(history_hits)[:350])

# result：一个正常答案 + 一个诚实的无证据答案。
citation = {key: hits["hits"][0][key] for key in
            ("path", "sha256", "version", "role", "chunk_id", "quote", "locator")}
BASE = base_result(index)
BASE["answers"] = [
    {"question": "设置温度是多少？", "answer": "当前 v2 记录为 42 °C。", "status": "answered",
     "claims": [{"claim_id": "c1", "text": "当前 v2 记录设置温度为 42 °C。", "evidence": [citation]}]},
    {"question": "相对湿度是多少？", "answer": "当前资料库没有依据。", "status": "no_evidence",
     "claims": [], "missing": ["当前索引中没有相对湿度记录，需要补充实验记录或原始日志"]}]
BASE_PATH = dump(os.path.join(TMP, "result.json"), BASE)
rc, checked = run("qacheck", BASE_PATH, "--index", INDEX)
add("qacheck正向:精确引文与诚实缺证零误杀", rc == 0 and checked.get("verified_claims") == 1
    and checked.get("verified_citations") == 1 and checked.get("no_evidence_answers") == 1,
    str(checked)[:400])

for name, mutate, expected, expected_rc in [
    ("sha256版本不符", lambda x: x["answers"][0]["claims"][0]["evidence"][0].update(sha256="0" * 64), "sha256", 1),
    ("quote不是原文", lambda x: x["answers"][0]["claims"][0]["evidence"][0].update(quote="温度为 999 °C"), "quote", 1),
    ("version标签不符", lambda x: x["answers"][0]["claims"][0]["evidence"][0].update(version="v1"), "version", 1),
    ("段落坐标不符", lambda x: x["answers"][0]["claims"][0]["evidence"][0]["locator"].update(paragraph=99), "paragraph", 1),
    ("关键论断缺证据", lambda x: x["answers"][0]["claims"][0].update(evidence=[]), "evidence", 1),
    ("无证据却不说明缺什么", lambda x: x["answers"][1].update(missing=[]), "missing", 1),
    ("检索范围指纹造假", lambda x: x["scope"].update(index_sha256="f" * 64), "scope.index_sha256", 1),
    ("检索范围夹带索引外文件", lambda x: x["scope"]["searched_documents"].append("not-in-index.txt"), "索引外路径", 1),
    ("pass但异常未解决", lambda x: x["exceptions"].append({"type": "file_unreadable", "path": "x.pdf", "status": "blocked",
                                                        "action": "排除", "recovery": "补件"}), "status=pass", 1),
]:
    bad = json.loads(json.dumps(BASE))
    mutate(bad)
    bad_path = dump(os.path.join(TMP, "bad-" + str(len(checks)) + ".json"), bad)
    rc, result = run("qacheck", bad_path, "--index", INDEX)
    add("qacheck变异:" + name + "必命中", rc == expected_rc
        and any(expected in error for error in result.get("errors", [])), str(result)[:300])

# 索引被改而指纹未更新：必须拒绝，而非拿错版本继续核对。
tampered = json.loads(json.dumps(index))
tampered["documents"][0]["version"] = "tampered"
TAMPERED = dump(os.path.join(TMP, "tampered-index.json"), tampered)
rc, result = run("qacheck", BASE_PATH, "--index", TAMPERED)
add("qacheck变异:索引损坏/篡改必命中", rc == 2 and any("指纹" in e for e in result.get("errors", [])),
    str(result)[:250])

# 版本冲突必须写进 exceptions；issues + open 可诚实交付，pass 不可。
undisclosed = base_result(conflict_index)
undisclosed["answers"] = [{"question": "阈值？", "answer": "当前无法确定", "status": "no_evidence",
                            "claims": [], "missing": ["v1/v2 版本冲突未声明"]}]
UNDISCLOSED = dump(os.path.join(TMP, "undisclosed.json"), undisclosed)
rc, result = run("qacheck", UNDISCLOSED, "--index", CONFLICTINDEX)
add("qacheck变异:索引版本冲突被静默忽略必命中", rc == 1
    and any("version_conflict" in error for error in result.get("errors", [])), str(result)[:300])
disclosed = json.loads(json.dumps(undisclosed))
disclosed["status"] = "issues"
disclosed["exceptions"] = [{"type": "version_conflict", "path": "report", "status": "open",
                             "action": "v1/v2 分列，不自动选当前", "recovery": "由版本说明确认 current/history 后重建索引"}]
DISCLOSED = dump(os.path.join(TMP, "disclosed.json"), disclosed)
rc, result = run("qacheck", DISCLOSED, "--index", CONFLICTINDEX)
add("qacheck异常:版本冲突有记录则允许issues交付", rc == 0 and result.get("checked_exceptions") == 1,
    str(result)[:300])
false_resolved = json.loads(json.dumps(disclosed))
false_resolved["exceptions"][0]["status"] = "resolved"
FALSE_RESOLVED = dump(os.path.join(TMP, "false-resolved.json"), false_resolved)
rc, result = run("qacheck", FALSE_RESOLVED, "--index", CONFLICTINDEX)
add("qacheck变异:索引仍有冲突却写resolved必命中", rc == 1
    and any("重跑 index" in error for error in result.get("errors", [])), str(result)[:300])

# 冲突答案：不同版本原文必须同时回链，不能只写“存在冲突”。
current_cite = citation
history_raw = next(h for h in history_hits["hits"] if h["role"] == "history")
history_cite = {key: history_raw[key] for key in
                ("path", "sha256", "version", "role", "chunk_id", "quote", "locator")}
conflict_result = base_result(index)
conflict_result["answers"] = [{"question": "两版温度是否一致？", "answer": "不一致：v1 为 41 °C，v2 为 42 °C。",
                                "status": "conflict", "claims": [
    {"claim_id": "old", "text": "v1 为 41 °C", "evidence": [history_cite]},
    {"claim_id": "new", "text": "v2 为 42 °C", "evidence": [current_cite]}]}]
conflict_result["conflicts"] = [{"topic": "设置温度版本差异", "status": "unresolved",
                                  "explanation": "原文数值不同；没有独立校准记录，不裁决哪次实验正确",
                                  "evidence": [history_cite, current_cite]}]
CONFLICT_RESULT = dump(os.path.join(TMP, "evidence-conflict.json"), conflict_result)
rc, result = run("qacheck", CONFLICT_RESULT, "--index", INDEX)
add("qacheck正向:互相矛盾证据分版本并列零误杀", rc == 0 and result.get("conflict_answers") == 1,
    str(result)[:350])
bad_conflict = json.loads(json.dumps(conflict_result))
bad_conflict["conflicts"][0]["evidence"] = [current_cite]
BAD_CONFLICT = dump(os.path.join(TMP, "bad-evidence-conflict.json"), bad_conflict)
rc, result = run("qacheck", BAD_CONFLICT, "--index", INDEX)
add("qacheck变异:冲突只有单条证据必命中", rc == 1 and any("至少两条" in e for e in result.get("errors", [])),
    str(result)[:300])

ok = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
