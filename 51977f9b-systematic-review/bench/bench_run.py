#!/usr/bin/env python3
"""syn_tool v2 全量 bench：每命令正向零误杀 + 变异必命中；仅标准库。

样例是合成接口夹具，不是平台正式案例、白板或科研结论。
"""
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TOOL = os.path.join(ROOT, "scripts", "syn_tool.py")
EXAMPLE = os.path.join(ROOT, "examples", "minimal")
TMP = tempfile.mkdtemp(prefix="syn-tool-bench-")
FIXTURE = os.path.join(TMP, "minimal")
shutil.copytree(EXAMPLE, FIXTURE)
checks = []
_counter = 0


def run(*args):
    process = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, timeout=30)
    try:
        data = json.loads(process.stdout)
    except Exception:
        data = {"raw": process.stdout[-500:], "stderr": process.stderr[-500:]}
    return process.returncode, data


def dump(value, prefix="case"):
    global _counter
    _counter += 1
    path = os.path.join(FIXTURE, "%s-%03d.json" % (prefix, _counter))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
    return path


def add(name, passed, detail=""):
    checks.append((name, bool(passed), str(detail)[:500]))


def errors(data, code):
    return any(x.get("code") == code for x in data.get("errors", []))


def positive(command, result="result.example.json", *extra):
    return run(command, os.path.join(FIXTURE, result), *extra)


def mutant(command, value, code, label, *extra):
    path = dump(value, command + "-mutant")
    rc, data = run(command, path, *extra)
    add(label, rc == 1 and not data.get("ok") and errors(data, code), data.get("errors", data))


with open(os.path.join(FIXTURE, "result.example.json"), encoding="utf-8") as f:
    GOOD = json.load(f)


def mutation():
    return copy.deepcopy(GOOD)


# hash：正向与文件变异。
case_path = os.path.join(FIXTURE, "case.json")
with open(case_path, "rb") as f:
    original_hash = hashlib.sha256(f.read()).hexdigest()
rc, data = run("hash", case_path)
add("hash 正向：真实 SHA-256 与字节数", rc == 0 and data["metrics"]["files"][0]["sha256"] == original_hash, data)
hash_copy = os.path.join(FIXTURE, "hash-mutant.txt")
with open(hash_copy, "w", encoding="utf-8") as f:
    f.write("changed")
rc, data = run("hash", hash_copy)
add("hash 变异：内容变化导致摘要变化", rc == 0 and data["metrics"]["files"][0]["sha256"] != original_hash, data)
rc, data = run("not_a_command")
add("调用边界：未知命令JSON报错且退出2", rc == 2 and errors(data, "cli_usage"), data)
malformed = os.path.join(FIXTURE, "malformed.json")
with open(malformed, "w", encoding="utf-8") as f:
    f.write("{not-json")
rc, data = run("schema", malformed)
add("输入边界：非法JSON结构化报错而非traceback", rc == 1 and errors(data, "runtime_input"), data)
rc, data = run("schema", os.path.join(FIXTURE, "does-not-exist.json"))
add("输入边界：缺文件结构化报错且退出1", rc == 1 and errors(data, "runtime_input"), data)

# schema：版本、原始 output_contract、哈希与产物。
rc, data = positive("schema", "result.example.json", "--case", os.path.join(FIXTURE, "case.json"), "--verify-artifacts")
add("schema 正向：版本/契约/产物零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad.pop("schema_version")
mutant("schema", bad, "missing_field", "schema 变异：缺版本字段必命中")
bad = mutation(); bad["schema_version"] = "1.0.0"
mutant("schema", bad, "schema_version", "schema 变异：版本错配必命中")
bad = mutation(); bad["counts"]["records_raw"] = 99
mutant("schema", bad, "count_identity", "schema 变异：原始计数恒等式破坏必命中")
unknown = mutation(); unknown["run"]["model_requests"] = None; unknown["run"]["metric_notes"] = {"model_requests": "not_checked: platform has not exported this metric"}
rc, data = run("schema", dump(unknown, "schema-unknown-metric"))
add("schema 边界：未知效率指标显式 null+not_checked 零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["run"]["model_requests"] = None
mutant("schema", bad, "metric_unknown", "schema 变异：效率指标未知却不说明必命中")
artifact_path = os.path.join(FIXTURE, "review.md")
with open(artifact_path, "a", encoding="utf-8") as f:
    f.write("\nartifact mutation\n")
rc, data = positive("schema", "result.example.json", "--verify-artifacts")
add("schema 变异：产物篡改必命中", rc == 1 and errors(data, "artifact_hash"), data.get("errors"))
with open(artifact_path, "w", encoding="utf-8") as dst, open(os.path.join(EXAMPLE, "review.md"), encoding="utf-8") as src:
    dst.write(src.read())

# protocol：检索式、预注册时序、标准版本与空检索。
rc, data = positive("protocol_check")
add("protocol_check 正向：结构化问题/检索式/标准零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["search"]["queries"][0]["query"] = "alpha adults recovery"
mutant("protocol_check", bad, "query_not_executable", "protocol_check 变异：关键词串退化必命中")
bad = mutation(); bad["protocol"]["criteria_sha256"] = "0" * 64
mutant("protocol_check", bad, "criteria_hash", "protocol_check 变异：事后偷改标准必命中")
bad = mutation(); bad["decisions"][0]["decided_at"] = "2025-01-01T00:00:00Z"
mutant("protocol_check", bad, "criteria_not_prospective", "protocol_check 变异：判定早于标准必命中")
bad = mutation(); bad["search"]["queries"][0]["result_count"] = 0
mutant("protocol_check", bad, "missing_field", "protocol_check 变异：空检索无分类动作必命中")

# screen：逐条理由、两轮终判、去重、双人分歧、计数重算。
rc, data = positive("screen_check")
add("screen_check 正向：纳排/去重/裁决/计数零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["decisions"][6]["reason_codes"] = []
mutant("screen_check", bad, "reason_codes", "screen_check 变异：排除缺理由码必命中")
bad = mutation(); bad["decisions"][6]["evidence"]["quote"] = ""
mutant("screen_check", bad, "decision_evidence", "screen_check 变异：排除缺逐字依据必命中")
bad = mutation(); bad["decisions"][0]["protocol_version"] = "P-old"
mutant("screen_check", bad, "decision_protocol", "screen_check 变异：使用旧标准未迁移必命中")
bad = mutation(); bad["decisions"] = [x for x in bad["decisions"] if x["id"] != "D5"]
mutant("screen_check", bad, "unresolved_disagreement", "screen_check 变异：双人分歧静默不裁决必命中")
bad = mutation(); bad["duplicates"][0]["match_basis"]["normalized_value"] = ""
mutant("screen_check", bad, "dedup_basis", "screen_check 变异：去重无规范化依据必命中")
bad = mutation(); bad["duplicates"] = []
mutant("screen_check", bad, "unregistered_duplicate", "screen_check 变异：删除重复簇造成去重链断裂必命中")
# 独立精确测试计数重算。
bad = mutation(); bad["counts"]["included"] = 2
mutant("screen_check", bad, "count_recompute", "screen_check 变异：纳入计数与终判不符必命中")

# quality：逐维度证据与总等级重算。
rc, data = positive("quality_check")
add("quality_check 正向：逐维度评分重算零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["quality_appraisals"][0]["overall"]["score"] = 3
mutant("quality_check", bad, "quality_score", "quality_check 变异：质量总分造假必命中")
bad = mutation(); bad["quality_appraisals"][0]["overall"]["rating"] = "high"
mutant("quality_check", bad, "quality_rating", "quality_check 变异：质量等级越阈值必命中")
bad = mutation(); bad["quality_appraisals"][0]["items"][0]["evidence"]["location"] = "p.1"
mutant("quality_check", bad, "quality_evidence", "quality_check 变异：质量评价只有模糊位置必命中")
bad = mutation(); bad["quality_appraisals"] = []
mutant("quality_check", bad, "quality_coverage", "quality_check 变异：纳入研究漏质量评价必命中")

# citations：引用清单、纳入集、事实/推断分类与精确定位。
rc, data = positive("cite_check")
add("cite_check 正向：论断-引用回路零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["claims"][0]["citations"] = []
mutant("cite_check", bad, "uncited_claims", "cite_check 变异：无论断引用必命中")
bad = mutation(); bad["claims"][0]["citations"][0]["record_id"] = "R999"
mutant("cite_check", bad, "dangling_citations", "cite_check 变异：悬空引用必命中")
bad = mutation(); bad["claims"][0]["citations"][0]["record_id"] = "R2"
mutant("cite_check", bad, "citation_outside_included", "cite_check 变异：以排除文献支撑综合论断必命中")
bad = mutation(); bad["claims"][0]["citations"][0]["location"] = "结果第3段"
mutant("cite_check", bad, "citation_evidence", "cite_check 变异：定位不到句/字段必命中")
bad = mutation(); bad["claims"][1]["kind"] = "inference"; bad["claims"][1]["inference_rationale"] = ""
mutant("cite_check", bad, "inference_rationale", "cite_check 变异：事实与推断边界缺失必命中")

# verbatim quote：双哈希锁定原文，而非只看 location 字符串。
rc, data = positive("quote_check")
add("quote_check 正向：逐字引文与双哈希零误杀", rc == 0 and data["metrics"].get("verbatim_rate") == 1.0, data)
bad = mutation(); bad["claims"][0]["citations"][0]["quote"] = "At 4 weeks, the mean recovery score was 99.9."
bad["claims"][0]["citations"][0]["quote_sha256"] = hashlib.sha256(bad["claims"][0]["citations"][0]["quote"].encode()).hexdigest()
mutant("quote_check", bad, "quote_not_verbatim", "quote_check 变异：编造引文即使哈希自洽也必命中")
bad = mutation(); bad["claims"][0]["citations"][0]["source_sha256"] = "0" * 64
mutant("quote_check", bad, "source_link", "quote_check 变异：证据挂错原文版本必命中")
bad = mutation(); bad["records"][0]["source"]["text_sha256"] = "0" * 64
mutant("quote_check", bad, "text_file_hash", "quote_check 变异：抽取文本哈希错配必命中")

# themes：实际引用记录集合必须等于归纳来源，不能先设主题再凑文献。
rc, data = positive("theme_check")
add("theme_check 正向：主题由实际引用归纳零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["themes"][0]["derived_from"] = []
mutant("theme_check", bad, "theme_derivation", "theme_check 变异：主题无文献来源必命中")
bad = mutation(); bad["themes"][0]["claim_ids"] = []
mutant("theme_check", bad, "theme_claims", "theme_check 变异：预设主题无论断必命中")
bad = mutation(); bad["claims"][0]["theme"] = "T-other"
mutant("cite_check", bad, "claim_theme", "cite_check 变异：论断挂未声明主题必命中")

# gaps/conflicts：空白必须有排除证据，冲突必须保留两端。
rc, data = positive("synthesis_check")
add("synthesis_check 正向：有界空白/冲突状态零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["research_gaps"][0]["evidence"]["excluded_record_ids"] = []
mutant("synthesis_check", bad, "gap_exclusions", "synthesis_check 变异：把无排除证据当研究空白必命中")
bad = mutation(); bad["research_gaps"][0]["evidence"]["reason_codes"] = ["E-NOT-USED"]
mutant("synthesis_check", bad, "gap_reason_backlink", "synthesis_check 变异：空白理由码不回链判定必命中")
bad = mutation(); bad["research_gaps"][0]["evidence"]["query_ids"] = []
mutant("synthesis_check", bad, "gap_queries", "synthesis_check 变异：空白无实际检索式必命中")
bad = mutation(); bad["conflicts"] = [{"id": "X", "claim_ids": ["C1"], "record_ids": ["R1"], "positions": [], "resolution": "unresolved", "impact_on_claims": "none"}]
mutant("synthesis_check", bad, "conflict_positions", "synthesis_check 变异：冲突矩阵只留单方/无证据必命中")

# exceptions：题面七类失败的数据契约 + 可自动发现的空检索/超时/全文缺失。
rc, data = positive("exception_check")
add("exception_check 正向：异常识别-动作-状态闭环零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["search"]["queries"][0]["result_count"] = 0
mutant("exception_check", bad, "empty_search_unhandled", "exception_check 变异：检索为空未处置必命中")
bad = mutation(); bad["search"]["queries"][0]["error"] = {"type": "timeout", "message": "synthetic timeout"}
mutant("exception_check", bad, "timeout_unhandled", "exception_check 变异：数据库超时未处置必命中")
bad = mutation(); bad["exceptions"] = [x for x in bad["exceptions"] if x["type"] != "full_text_unavailable"]
mutant("exception_check", bad, "full_text_unhandled", "exception_check 变异：全文不可得未标注必命中")
bad = mutation(); bad["exceptions"][0]["status"] = "pending"; bad["status"] = "pass"
mutant("exception_check", bad, "pending_on_pass", "exception_check 变异：待人工却宣称 pass 必命中")

# gain：同 case/task 哈希、同权限，所有比率由原始结果重算。
rc, data = positive("gain_check", "result.example.json", "--baseline", "baseline.example.json")
add("gain_check 正向：公平对照及质量/效率重算零误杀", rc == 0 and data.get("ok"), data)
bad = mutation(); bad["gain"]["skill"]["metrics"]["claim_citation_coverage"] = 999
mutant("gain_check", bad, "gain_recompute", "gain_check 变异：增益指标篡改必命中", "--baseline", "baseline.example.json")
bad = mutation(); bad["run"]["permissions"] = "different permission"
mutant("gain_check", bad, "different_permissions", "gain_check 变异：对照权限不公平必命中", "--baseline", "baseline.example.json")
bad = mutation(); bad["run"]["input"]["case"]["sha256"] = "0" * 64
mutant("gain_check", bad, "different_input", "gain_check 变异：对照输入不同必命中", "--baseline", "baseline.example.json")
update_case = mutation(); update_case["gain"] = {"comparison_status": "not_run", "reason": "bench update"}
update_path = dump(update_case, "gain-update")
rc, data = run("gain_check", update_path, "--baseline", "baseline.example.json", "--update")
with open(update_path, encoding="utf-8") as f:
    updated = json.load(f)
add("gain_check --update 正向：从原始记录生成 gain", rc == 0 and updated["gain"]["comparison_status"] == "completed" and updated["gain"]["design"]["same_input"], data)

# audit 总闸门：任一核心链路失败不可交付；产物和 case 契约也纳入。
rc, data = positive("audit", "result.example.json", "--baseline", "baseline.example.json", "--case", os.path.join(FIXTURE, "case.json"), "--verify-artifacts")
add("audit 正向：10项核心检查全绿零误杀", rc == 0 and data["metrics"].get("all_checks_passed"), data)
bad = mutation(); bad["claims"][0]["citations"] = []
mutant("audit", bad, "uncited_claims", "audit 变异：任一核心错误使总闸门失败", "--baseline", "baseline.example.json")
bad = mutation(); bad["gain"] = {"comparison_status": "not_run", "reason": "platform did not provide baseline"}
rc, data = run("audit", dump(bad, "audit-no-baseline"), "--allow-gain-not-run")
add("audit 边界：无基线诚实标 not_checked 而不伪增益", rc == 0 and any(x["code"] == "gain_not_run" for x in data.get("not_checked", [])), data)

# 空纳入集：允许诚实降级，但禁止用排除文献拼论断。
empty = mutation(); empty["included"] = []; empty["claims"] = []; empty["themes"] = []; empty["quality_appraisals"] = []
for command in ("cite_check", "quote_check", "theme_check"):
    rc, data = run(command, dump(empty, "empty-included"))
    # quote_check 仍应核验真实存在的筛选排除证据，因此只有 cite/theme 必报 not_checked。
    boundary_ok = rc == 0 and (command == "quote_check" or data.get("not_checked"))
    add(command + " 边界：空纳入集诚实降级零误杀", boundary_ok, data)
empty_bad = copy.deepcopy(empty); empty_bad["claims"] = copy.deepcopy(GOOD["claims"][:1])
rc, data = run("cite_check", dump(empty_bad, "empty-included-mutant"))
add("cite_check 边界变异：空纳入集却引用排除文献必命中", rc == 1 and errors(data, "citation_outside_included"), data.get("errors"))

# 千级记录/论断的稳定性与变异检测；不是性能分数或正式案例结果。
scale = mutation()
scale["records"] = []
scale["included"] = []
scale["claims"] = []
source = copy.deepcopy(GOOD["records"][0]["source"])
for i in range(1200):
    rid = "S%04d" % i
    scale["records"].append({"id": rid, "title": "Synthetic %d" % i, "source": copy.deepcopy(source)})
    scale["included"].append({"id": rid})
    citation = copy.deepcopy(GOOD["claims"][0]["citations"][0]); citation["record_id"] = rid
    scale["claims"].append({"id": "SC%04d" % i, "text": "synthetic", "kind": "material_fact", "theme": "T1", "citations": [citation]})
scale_path = dump(scale, "scale-1200")
start = time.monotonic(); rc, data = run("cite_check", scale_path); elapsed = time.monotonic() - start
add("规模正向：1200记录/1200论断引用闭合零误杀", rc == 0 and data["metrics"].get("claims") == 1200, "elapsed=%.3fs errors=%s" % (elapsed, data.get("errors")))
scale["claims"][-1]["citations"][0]["record_id"] = "DANGLING"
rc, data = run("cite_check", dump(scale, "scale-1200-mutant"))
add("规模变异：1200论断中的单个悬空引用必命中", rc == 1 and errors(data, "dangling_citations"), data.get("errors"))

ok = sum(1 for _, passed, _ in checks if passed)
for name, passed, detail in checks:
    print(("PASS" if passed else "FAIL"), name, ("| " + detail if not passed else ""))
print("total %d/%d" % (ok, len(checks)))
print("fixture=%s (synthetic only)" % FIXTURE)
shutil.rmtree(TMP)
sys.exit(0 if ok == len(checks) else 1)
