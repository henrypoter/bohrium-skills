#!/usr/bin/env python3
"""检索工具链自测：每个命令均有正向零误杀与变异必命中测试。仅标准库。"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.abspath(os.path.join(HERE, "..", "scripts", "file_tool.py"))
TMP = tempfile.mkdtemp(prefix="retrieval-bench-")
ROOT = os.path.join(TMP, "library")
INDEX = os.path.join(TMP, "index.json")
checks = []


def dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def run(*args, timeout=120):
    r = subprocess.run([sys.executable, TOOL, *map(str, args)], capture_output=True, text=True, timeout=timeout)
    try:
        data = json.loads(r.stdout)
    except Exception:
        data = {"raw": r.stdout[-800:], "stderr": r.stderr[-800:]}
    return r.returncode, data


def add(name, condition, detail=""):
    checks.append((name, bool(condition), str(detail)[:500]))


def put(rel, text):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def make_zip_package(rel, entries):
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)
    return path


def make_docx(rel, paragraphs):
    body = []
    for i, text in enumerate(paragraphs):
        style = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if i == 0 else ""
        body.append('<w:p>%s<w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % (style, text))
    xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
          '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>' % "".join(body)
    return make_zip_package(rel, {"[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
                                  "word/document.xml": xml})


def make_pptx(rel, slide_texts):
    entries = {"[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'}
    for i, text in enumerate(slide_texts, 1):
        entries["ppt/slides/slide%d.xml" % i] = '''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>%s</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>''' % text
    return make_zip_package(rel, entries)


def col(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def make_xlsx(rel, rows):
    rows_xml = []
    for ri, values in enumerate(rows, 1):
        cells = []
        for ci, value in enumerate(values, 1):
            cells.append('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' % (col(ci), ri, value))
        rows_xml.append('<row r="%d">%s</row>' % (ri, "".join(cells)))
    entries = {
        "[Content_Types].xml": '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "xl/workbook.xml": '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Experiments" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>',
        "xl/worksheets/sheet1.xml": '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>' % "".join(rows_xml)
    }
    return make_zip_package(rel, entries)


def make_pdf(rel, lines=(), printed_page=None):
    """生成最小真实 PDF，供系统 pdftotext 测试；不预生成答案层。"""
    all_lines = list(lines)
    if printed_page is not None:
        all_lines += [""] * 4 + [str(printed_page)]
    stream = "BT /F1 10 Tf 50 790 Td 14 TL " + " ".join("(%s) Tj T*" % x.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for x in all_lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        "<< /Length %d >>\nstream\n%s\nendstream" % (len(stream.encode()), stream),
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    raw = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(raw))
        raw.extend(("%d 0 obj\n%s\nendobj\n" % (i, obj)).encode())
    xref = len(raw)
    raw.extend(("xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)).encode())
    for off in offsets[1:]:
        raw.extend(("%010d 00000 n \n" % off).encode())
    raw.extend(("trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)).encode())
    path = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(raw)
    return path


# ---------- 合成科研库（仅自测，不是平台案例或预置答案） ----------
protocol = "# 实验方法\n\n本 protocol 使用流式细胞术分析样本。\n\n## 缓冲液配方\n\nFACS buffer: 1x PBS, 2% FBS, 2 mM EDTA. Batch B-7.\n"
put("2024/P1/protocol_v1.md", protocol)
put("2024/P1/protocol_copy.md", protocol)
put("2025/P2/protocol_v2.md", "# Methods\n\nFACS buffer: 1x PBS, 1% BSA. Project P2 version v2.\n")
put("2024/P2/other.md", "# Recipe\n\nFACS buffer: 0.5% BSA. Wrong project for P1.\n")
put("2024/P1/unrelated.md", "# Notes\n\n procurement calendar and room booking.\n")
put("2024/P1/results.csv", "sample,batch,result\nS1,B-7,figure 2 uses this dataset\nS2,B-8,negative control\n")
put("2024/P1/empty.txt", "")
make_docx("2024/P1/methods.docx", ["实验方法", "细胞计数后与流式细胞术上机。", "缓冲液配方为 1x PBS + 2% FBS。"])
make_pptx("2024/P1/slides.pptx", ["Experiment overview", "缓冲液配方: PBS / FBS / EDTA；见图 2。"])
make_xlsx("2024/P1/batches.xlsx", [["project", "batch", "buffer"], ["P1", "B-7", "FACS buffer 2% FBS"], ["P1", "B-8", "PBS only"]])
if shutil.which("pdftotext"):
    make_pdf("2024/P1/paper.pdf", ["Methods", "FACS buffer recipe: 2% FBS in PBS.", "Figure 2 shows gated cells."], 17)
    make_pdf("2024/P1/scan.pdf", [])
else:
    put("2024/P1/parser_unavailable.txt", "plain fallback")
put("2024/P1/broken.pdf", "%PDF broken")

metadata = []
for name in os.listdir(os.path.join(ROOT, "2024", "P1")):
    row = {"path": "2024/P1/" + name, "year": 2024, "project": "P1", "version": "v1",
           "permission": "read"}
    if name != "batches.xlsx":
        row["batch"] = "B-7"  # 行级表不能拿整文件批次覆盖每一行。
    metadata.append(row)
metadata += [
    {"path": "2025/P2/protocol_v2.md", "year": 2025, "project": "P2", "version": "v2", "permission": "read"},
    {"path": "2024/P2/other.md", "year": 2024, "project": "P2", "version": "v1", "permission": "read"},
]
META = dump(os.path.join(TMP, "metadata.json"), {"files": metadata})
ALIASES = dump(os.path.join(TMP, "aliases.json"), {"groups": [["cell counting", "细胞计数"]],
                                                  "field_aliases": {"课题": "project"}})

# ---------- inventory：正向 + 变异 ----------
rc, inv = run("inventory", ROOT)
add("inventory 正向:合法目录零误杀", rc == 0 and inv["ok"] and inv["file_count"] >= 10, inv)
add("inventory 嵌套/类型/大小完整", any(x["path"] == "2024/P1/results.csv" and x["size"] > 0 for x in inv["files"]), inv.get("files"))
dups = [g for g in inv["duplicate_groups"] if set(g["files"]) == {"2024/P1/protocol_v1.md", "2024/P1/protocol_copy.md"}]
add("inventory 同哈希副本归并", len(dups) == 1 and dups[0]["independent_evidence_count"] == 1, inv.get("duplicate_groups"))
add("inventory 变异:不同内容不误判重复", all(set(g["files"]) != {"2024/P1/protocol_v1.md", "2025/P2/protocol_v2.md"} for g in inv["duplicate_groups"]), inv.get("duplicate_groups"))
add("inventory 空文件显式登记", "2024/P1/empty.txt" in inv["empty_files"], inv.get("empty_files"))
rc, bad = run("inventory", os.path.join(TMP, "not-mounted"))
add("inventory 变异:失效路径必命中", rc == 1 and bad["anomalies"][0]["status"] == "path_invalid", bad)

# ---------- index：OOXML/PDF/异常 ----------
rc, idx = run("index", ROOT, "--output", INDEX, "--metadata", META, "--aliases", ALIASES)
add("index 正向:命令与索引文件可执行", rc == 0 and os.path.isfile(INDEX) and idx["indexed_block_count"] >= 15, idx.get("indexed_block_count"))
files = {x["path"]: x for x in idx["files"]}
blocks = idx["blocks"]
add("index 原文块带哈希/定位", all(b.get("sha256") and b.get("block_id") and b.get("locator") for b in blocks), len(blocks))
add("index DOCX 章节与段落", any(b["path"].endswith("methods.docx") and b["section"] == "实验方法" and b["locator"]["paragraph"] for b in blocks), "docx")
add("index PPTX 幻灯片定位", any(b["path"].endswith("slides.pptx") and b["locator"]["slide"] == 2 for b in blocks), "pptx")
add("index XLSX 工作表与行定位", any(b["path"].endswith("batches.xlsx") and b["locator"]["sheet"] == "Experiments" and b["locator"]["row"] == 2 for b in blocks), "xlsx")
add("index CSV 行级字段", any(b["path"].endswith("results.csv") and b.get("row_metadata", {}).get("batch") == "B-7" for b in blocks), "csv")
if "2024/P1/paper.pdf" in files:
    add("index PDF 物理页/印刷页错位", files["2024/P1/paper.pdf"]["status"] == "indexed" and all(b["locator"]["page"] == 1 and b["locator"]["printed_page"] == "17" for b in blocks if b["path"].endswith("paper.pdf")), files.get("2024/P1/paper.pdf"))
    add("index 变异:无文本层扫描件标 needs_ocr", files["2024/P1/scan.pdf"]["status"] == "needs_ocr", files.get("2024/P1/scan.pdf"))
add("index 变异:损坏 PDF 不伪造文本", files["2024/P1/broken.pdf"]["status"] in {"corrupt_or_unreadable", "encrypted"} and files["2024/P1/broken.pdf"]["block_count"] == 0, files.get("2024/P1/broken.pdf"))
rc, invalid_index = run("index", os.path.join(TMP, "gone-library"), "--output", os.path.join(TMP, "gone-index.json"))
add("index 变异:失效根目录返回失败", rc == 1 and invalid_index["index_status"] == "issues", invalid_index)
add("index 缺过滤元数据不推断", files["2024/P1/unrelated.md"]["metadata"].get("project") is not None and files["2025/P2/protocol_v2.md"]["metadata"]["project"] == "P2", "metadata")
add("index 版本名只产候选不猜当前", any(v["relation"] == "candidate_only" and v["current"] is None for v in idx["version_candidates"]) and not idx["version_groups"], idx.get("version_candidates"))
# 重名不同内容不是副本；内容副本有 canonical，但可独立按路径检索。
add("index 副本不增加独立证据", files["2024/P1/protocol_copy.md"]["independent_evidence_id"] == files["2024/P1/protocol_v1.md"]["independent_evidence_id"] and any(f.get("duplicate_of") for f in (files["2024/P1/protocol_copy.md"], files["2024/P1/protocol_v1.md"])), files.get("2024/P1/protocol_copy.md"))

# ---------- search：语义、章节、硬过滤 ----------
filters = dump(os.path.join(TMP, "filters.json"), {"year": 2024, "project": "P1", "type": ["md", "docx", "pptx", "pdf", "xlsx"], "permission": "read"})
SEARCH = os.path.join(TMP, "search.json")
rc, hits = run("search", INDEX, "--query", "缓冲液配方写在哪一版", "--filters", filters, "--output", SEARCH, "--limit", 30)
add("search 正向:跨文件命中", rc == 0 and len(hits["hits"]) >= 3, hits.get("hits"))
add("search 同义/缩写跨语言扩展", any(h["semantic_matches"] for h in hits["hits"]) or any("FACS" in h["quote"] for h in hits["hits"]), hits.get("semantic_expansions"))
add("search 章节级而非整篇", any(h["section"] in {"缓冲液配方", "实验方法"} for h in hits["hits"]), [(h["path"], h["section"]) for h in hits["hits"]])
add("search 证据字段齐全", all(all(k in h for k in ("path", "sha256", "block_id", "version", "locator", "paragraph_first_sentence", "quote", "source_uri")) for h in hits["hits"]), "evidence")
add("search 变异:项目硬过滤零放宽", all(h["metadata"]["project"] == "P1" and h["metadata"]["year"] == 2024 for h in hits["hits"]), hits.get("hits"))
add("search 副本不冒充独立证据", hits["independent_evidence_count"] < len(hits["hits"]) or not any(h.get("copy_aliases") for h in hits["hits"]), hits.get("independent_evidence_count"))
rc, p2 = run("search", INDEX, "--query", "FACS buffer recipe", "--filters", dump(os.path.join(TMP, "p2.json"), {"project": "P2", "year": 2024}))
add("search 变异:P2 只回 P2", rc == 0 and p2["hits"] and all(h["path"] == "2024/P2/other.md" for h in p2["hits"]), p2.get("hits"))
rc, missing = run("search", INDEX, "--query", "FACS buffer", "--filters", dump(os.path.join(TMP, "missing.json"), {"grant_code": "X-1"}))
add("search 变异:缺过滤字段即排除并列缺口", rc == 0 and not missing["hits"] and missing["coverage_gaps"] and missing["no_hit"]["reason"] == "filters_excluded_all", missing)
rc, none = run("search", INDEX, "--query", "nonexistent-zebra-quasar", "--filters", filters)
add("search 空结果如实给恢复动作", rc == 0 and not none["hits"] and none["no_hit"]["action"], none)
NONE = dump(os.path.join(TMP, "no-hit.json"), none)
rc, nv = run("verify", NONE, "--index", INDEX)
add("verify 正向:有轨迹的合法空结果零误杀", rc == 0 and nv["ok"], nv)
rc, batch = run("search", INDEX, "--query", "FACS buffer", "--filters", dump(os.path.join(TMP, "batch.json"), {"project": "P1", "batch": "B-8", "type": "xlsx"}))
add("search 行级批次硬过滤", rc == 0 and len(batch["hits"]) == 1 and batch["hits"][0]["locator"]["row"] == 3, batch.get("hits"))

# ---------- verify：逐字回链 + 版本 + 定位 ----------
rc, ver = run("verify", SEARCH, "--index", INDEX, "--root", ROOT)
add("verify 正向:真实证据零误杀", rc == 0 and ver["checked_evidence"] == len(hits["hits"]), ver)

def mutation(name, mutate, needle, use_root=False):
    obj = copy.deepcopy(hits)
    mutate(obj)
    path = dump(os.path.join(TMP, name + ".json"), obj)
    rc, out = run("verify", path, "--index", INDEX, *( ["--root", ROOT] if use_root else []))
    add("verify 变异:" + name + "必命中", rc == 1 and any(needle in e for e in out["errors"]), out)

mutation("引文改字", lambda x: x["hits"][0].__setitem__("quote", "伪造原文 quote"), "逐字子串")
mutation("版本哈希替换", lambda x: x["hits"][0].__setitem__("sha256", "0" * 64), "版本哈希")
mutation("物理页错位", lambda x: x["hits"][0]["locator"].__setitem__("page", 999), "定位字段 page")
mutation("证据跨文件错配", lambda x: x["hits"][0].__setitem__("block_id", "f999:b999"), "block_id")
mutation("路径失效", lambda x: None, "当前路径失效", use_root=False) if False else None
# 单独传一个不存在的当前根，验证恢复时能区分索引命中与路径失效。
rc, gone = run("verify", SEARCH, "--index", INDEX, "--root", os.path.join(TMP, "gone"))
add("verify 变异:当前路径失效必命中", rc == 1 and any("当前路径失效" in e for e in gone["errors"]), gone)
# 过滤后篡改证据路径为 P2，同时保留该路径真实 block。
p2hit = copy.deepcopy(p2["hits"][0])
tampered = copy.deepcopy(hits)
tampered["hits"] = [p2hit]
TAMPER = dump(os.path.join(TMP, "tampered-filter.json"), tampered)
rc, tv = run("verify", TAMPER, "--index", INDEX)
add("verify 变异:复制他项目证据违反硬过滤", rc == 1 and any("违反硬过滤" in e for e in tv["errors"]), tv)

# ---------- schema：完整交付契约 ----------
q = {"question": hits["query"], "filters": hits["filters_applied"], "hits": hits["hits"],
     "search_trace": hits["search_trace"], "uncertainty": hits["uncertainty"]}
result = {
    "case_id": "synthetic-demo", "status": "issues",
    "input_fingerprint": "sha256:same-input", "permissions_fingerprint": "sha256:read-only",
    "inventory": {"file_count": len(idx["files"]), "indexed_blocks": idx["indexed_block_count"]},
    "files": [{k: f.get(k) for k in ("path", "sha256", "size", "status", "type", "metadata")} for f in idx["files"]],
    "version_groups": [], "queries": [q],
    "operations": [{"action": "index", "target": "library", "result": "issues", "reversible": True}],
    "skipped": [], "failures": [{"path": "2024/P1/broken.pdf", "reason": "corrupt"}],
    "conflicts": [], "recovery": ["修复 broken.pdf 后重跑 index"],
    "sources": ["synthetic library"], "uncertainty": ["扫描件未 OCR"],
    "change_log": ["only synthetic temporary files"], "gain": {"comparison_status": "platform_pending"},
    "unchecked": []
}
RESULT = dump(os.path.join(TMP, "result.json"), result)
rc, schema = run("schema", RESULT, "--index", INDEX, "--root", ROOT)
add("schema 正向:完整真实交付零误杀", rc == 0 and schema["ok"], schema)

def schema_mutation(name, mutate, needle):
    obj = copy.deepcopy(result)
    mutate(obj)
    path = dump(os.path.join(TMP, "schema-" + name + ".json"), obj)
    rc, out = run("schema", path, "--index", INDEX)
    add("schema 变异:" + name + "必命中", rc == 1 and any(needle in e for e in out["errors"]), out)

schema_mutation("缺case_id", lambda x: x.pop("case_id"), "case_id")
schema_mutation("清单数量不一致", lambda x: x["inventory"].__setitem__("file_count", 999), "数量不一致")
schema_mutation("空结果无no_hit", lambda x: x["queries"][0].update({"hits": [], "no_hit": None}) or x["queries"][0].pop("no_hit", None), "no_hit")
schema_mutation("版本关系无证据", lambda x: x["version_groups"].append({"current": "final"}) , "关系判据")
schema_mutation("pass掩盖失败", lambda x: x.__setitem__("status", "pass"), "status=pass")
schema_mutation("伪造已测增益", lambda x: x.__setitem__("gain", {"comparison_status": "measured", "same_input": True, "same_permissions": False}), "same_input")
schema_mutation("最终证据绕过项目过滤", lambda x: x["queries"][0].__setitem__("hits", [copy.deepcopy(p2["hits"][0])]), "违反硬过滤")

# ---------- compare：同输入同权限公平对照 ----------
baseline = copy.deepcopy(result)
baseline["queries"] = [dict(q, hits=hits["hits"][:1])]
baseline["metrics"] = {"elapsed_seconds": 20.0}
result["metrics"] = {"elapsed_seconds": 8.0}
BASE = dump(os.path.join(TMP, "baseline.json"), baseline)
RESULT = dump(os.path.join(TMP, "result.json"), result)
gold_expected = [{"path": h["path"], "block_id": h["block_id"]} for h in hits["hits"]]
GOLD = dump(os.path.join(TMP, "gold.json"), {"expected": gold_expected})
rc, comp = run("compare", "--baseline", BASE, "--skill", RESULT, "--index", INDEX, "--gold", GOLD)
add("compare 正向:同输入同权限可计算增益", rc == 0 and comp["fairness"]["same_input"] and comp["fairness"]["same_permissions"], comp)
add("compare 质量/效率字段来自实际输出", comp["skill"]["valid_evidence_count"] == len(hits["hits"]) and comp["efficiency_gain"]["seconds_saved"] == 12.0, comp)
add("compare 金标准召回可复核", comp["skill"]["gold_recall"] == 1.0 and 0 < comp["baseline"]["gold_recall"] <= 1.0, comp.get("quality_gain"))
for name, mutate, needle in [
    ("case不同", lambda x: x.__setitem__("case_id", "other"), "case_id"),
    ("输入不同", lambda x: x.__setitem__("input_fingerprint", "changed"), "input_fingerprint"),
    ("权限不同", lambda x: x.__setitem__("permissions_fingerprint", "changed"), "permissions_fingerprint"),
]:
    b = copy.deepcopy(baseline)
    mutate(b)
    bp = dump(os.path.join(TMP, "compare-" + name + ".json"), b)
    rc, co = run("compare", "--baseline", bp, "--skill", RESULT, "--index", INDEX)
    add("compare 变异:" + name + "必命中", rc == 1 and any(needle in e for e in co["fairness"]["errors"]), co)

# ---------- 汇总 ----------
passed = sum(c for _, c, _ in checks)
for name, ok, detail in checks:
    print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
print("total %d/%d" % (passed, len(checks)))
print("fixtures:", TMP)
sys.exit(0 if passed == len(checks) else 1)
