#!/usr/bin/env python3
"""End-to-end mutation bench for material preflight and answer-anchor binding."""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CLIENT = os.path.join(ROOT, "reader_client.py")
GUARD = os.path.join(ROOT, "scripts", "delivery_guard.py")
TMP = tempfile.mkdtemp(prefix="reader-guard-bench-")
checks = []


def run(args):
    proc = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"raw": proc.stdout[-300:], "stderr": proc.stderr[-300:]}
    return proc.returncode, data


def client(work, command, *args):
    return run([CLIENT, "--workdir", work, command] + list(args))


def add(name, condition, detail=None):
    checks.append((name, bool(condition), str(detail or "")[:220]))


source = os.path.join(TMP, "source.txt")
text = "研究背景与图片中的 /Encrypt 字符串不是 PDF 加密字典。\n样本共 45 例，处理组显著改善。\n本段提供足够正文以建立可核验的阅读会话和原文锚点。"
open(source, "w", encoding="utf-8").write(text)
rc, data = run([GUARD, "inspect", source])
add("inspect正向:纯文本含/Encrypt字样不误杀", rc == 0 and data.get("material_version", {}).get("sha256"), data)

encrypted = os.path.join(TMP, "encrypted.pdf")
open(encrypted, "wb").write(b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\n5 0 obj << /Encrypt 9 0 R >>\n%%EOF")
rc, data = run([GUARD, "inspect", encrypted])
add("inspect变异:加密PDF必命中encrypted_pdf", rc == 1 and data.get("code") == "encrypted_pdf", data)

large = os.path.join(TMP, "large.txt")
open(large, "w", encoding="utf-8").write("x" * 2048)
rc, data = run([GUARD, "inspect", large, "--max-file-mib", "0.001"])
add("inspect变异:超限文件必命中oversized_file", rc == 1 and data.get("code") == "oversized_file", data)

failed_work = os.path.join(TMP, "failed-work")
rc, data = client(failed_work, "open", encrypted)
failed_export = os.path.join(TMP, "failed-output")
rc2, out2 = client(failed_work, "export", "--out", failed_export)
partial = json.load(open(os.path.join(failed_export, "result_draft.json"), encoding="utf-8"))
add("open/export异常:加密仍交付诚实partial与版本字段", rc == 2 and data.get("code") == "encrypted_pdf"
    and rc2 == 0 and partial.get("status") == "partial"
    and partial.get("status_reason") == "encrypted_pdf" and "tool_version" in partial, data)

work = os.path.join(TMP, "work")
out = os.path.join(TMP, "out")
rc_open, opened = client(work, "open", source)
rc_select, selected = client(work, "select", "--quote", "样本共 45 例")
quote = "样本共 45 例，处理组显着改善。"
# Use the exact source text; the deliberate traditional-character variant above
# must not accidentally enter the positive case.
quote = "样本共 45 例，处理组显著改善。"
rc_qa, qa = client(work, "qa", "--question", "样本量是多少？", "--answer", "45 例。", "--evidence", quote)
case_path = os.path.join(TMP, "case.json")
json.dump({"case_id": "synthetic-anchor", "output_contract": {"answers": [], "custom_delivery": "retained"}},
          open(case_path, "w", encoding="utf-8"), ensure_ascii=False)
rc_export, exported = client(work, "export", "--out", out, "--case", case_path)
draft_path = os.path.join(out, "result_draft.json")
rc_audit, report = run([GUARD, "audit", "--workdir", work, "--result", draft_path])
add("audit正向:答案/选区/证据/导出/材料版本完整绑定", rc_open == rc_select == rc_qa == rc_export == 0
    and rc_audit == 0 and report.get("bound_answers") == 1 and not report.get("errors"), report)
final = json.load(open(os.path.join(out, "result.json"), encoding="utf-8"))
add("export正向:case_id与output_contract字段保留", final.get("case_id") == "synthetic-anchor"
    and final.get("custom_delivery") == "retained" and final.get("schema_version") == 3, final)

session_path = os.path.join(work, "session.json")
original_session = json.load(open(session_path, encoding="utf-8"))
original_source = open(source, encoding="utf-8").read()


def restore():
    json.dump(copy.deepcopy(original_session), open(session_path, "w", encoding="utf-8"), ensure_ascii=False)
    open(source, "w", encoding="utf-8").write(original_source)


mutated = copy.deepcopy(original_session)
mutated["qa"][0]["answer"] = "45 例，且治愈。"
json.dump(mutated, open(session_path, "w", encoding="utf-8"), ensure_ascii=False)
rc, report = run([GUARD, "audit", "--workdir", work, "--result", draft_path])
add("audit变异:答案改字未重签必命中answer_hash", rc == 1 and any("answer_hash_mismatch" in e for e in report.get("errors", [])), report)
restore()

mutated = copy.deepcopy(original_session)
mutated["qa"][0]["evidence"][0].update(quote="捏造引文", anchor=dict(
    mutated["qa"][0]["evidence"][0]["anchor"], exact="捏造引文"))
json.dump(mutated, open(session_path, "w", encoding="utf-8"), ensure_ascii=False)
rc, report = run([GUARD, "audit", "--workdir", work, "--result", draft_path])
add("audit变异:引文不在锚定页必命中quote_not_on_anchor_page", rc == 1 and any("quote_not_on_anchor_page" in e for e in report.get("errors", [])), report)
restore()

open(source, "a", encoding="utf-8").write("\n材料被替换。")
rc, report = run([GUARD, "audit", "--workdir", work, "--result", draft_path])
add("audit变异:原文版本漂移必命中source_hash", rc == 1 and any("source_hash_mismatch" in e for e in report.get("errors", [])), report)
restore()

mutated = copy.deepcopy(original_session)
mutated["qa"][0]["selection"]["kind"] = "changed-context"
json.dump(mutated, open(session_path, "w", encoding="utf-8"), ensure_ascii=False)
rc, report = run([GUARD, "audit", "--workdir", work, "--result", draft_path])
add("audit变异:选区上下文漂移必命中selection_hash", rc == 1 and any("selection_hash_mismatch" in e for e in report.get("errors", [])), report)
restore()

broken_result = os.path.join(TMP, "broken_result.json")
draft = json.load(open(draft_path, encoding="utf-8"))
draft.pop("material_version")
json.dump(draft, open(broken_result, "w", encoding="utf-8"), ensure_ascii=False)
rc, report = run([GUARD, "audit", "--workdir", work, "--result", broken_result])
add("audit变异:导出缺材料版本必命中", rc == 1 and any("result_material_version_mismatch" in e for e in report.get("errors", [])), report)

annotations_path = os.path.join(out, "annotations.json")
annotations = json.load(open(annotations_path, encoding="utf-8"))
annotations["annotations"][0]["body"]["answer"] = "被改写的导出答案"
json.dump(annotations, open(annotations_path, "w", encoding="utf-8"), ensure_ascii=False)
rc, report = run([GUARD, "audit", "--workdir", work, "--result", draft_path])
add("audit变异:独立批注答案脱锚必命中annotation_answer", rc == 1 and any("annotation_answer_mismatch" in e for e in report.get("errors", [])), report)

ok = sum(passed for _, passed, _ in checks)
for name, passed, detail in checks:
    print(("PASS" if passed else "FAIL"), name, ("| " + detail if not passed else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
