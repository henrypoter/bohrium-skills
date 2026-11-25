#!/usr/bin/env python3
"""search_tool v3 自测：五命令正向零误杀 + 定向变异必命中。"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "scripts", "search_tool.py")
FIX = os.path.join(HERE, "fixtures")
checks = []


def run(cmd, path):
    r = subprocess.run([sys.executable, TOOL, cmd, path], capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)
    except Exception:
        return r.returncode, {"raw": r.stdout[:200]}


def tmp_copy(mutate, name):
    d = json.load(open(os.path.join(FIX, "good_result.json"), encoding="utf-8"))
    mutate(d)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="q7-" + name + "-", suffix=".json", delete=False) as fh:
        json.dump(d, fh, ensure_ascii=False)
        return fh.name


def add(name, cond, detail=""):
    checks.append((name, cond, detail))


# 1) dedup 正向：DOI 精确重复 1 组，且预印本/正式版近似候选被发现
rc, d = run("dedup", os.path.join(FIX, "records.json"))
near_pairs = {(n["a"], n["b"]) for n in d.get("near_duplicate_candidates", [])}
add("dedup正向:精确重复+近似候选", rc == 0 and d.get("exact_duplicate_groups") == 1
    and ("R1", "R3") in near_pairs, str(d)[:160])

# 2) dedup 变异：缺文件失败
rc, _ = run("dedup", os.path.join(FIX, "不存在.json"))
add("dedup变异:缺文件->失败", rc == 1, "rc=%d" % rc)

# 3) audit 正向：闭合通过
rc, d = run("audit", os.path.join(FIX, "good_result.json"))
add("audit正向:计数闭合零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:120])

# 4) audit 变异1：少一条判定 -> 闭合失败
def m1(d):
    d["screening"].pop()
rc, d = run("audit", tmp_copy(m1, "a1.json"))
add("audit变异:少一条判定->不闭合", rc == 1 and any("筛选合计" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 5) audit 变异2：未知理由码
def m2(d):
    d["screening"][0]["reason_code"] = "E99"
rc, d = run("audit", tmp_copy(m2, "a2.json"))
add("audit变异:未知理由码->失败", rc == 1 and any("不在字典内" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 6) audit 变异3：纳入判定却用排除码（方向矛盾）
def m3(d):
    d["screening"][0]["reason_code"] = "E3"
rc, d = run("audit", tmp_copy(m3, "a3.json"))
add("audit变异:码族与方向矛盾->失败", rc == 1 and any("矛盾" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 7) agreement 正向：一致率/kappa/分歧条数
rc, d = run("agreement", os.path.join(FIX, "pairs.json"))
add("agreement正向:一致率与kappa",
    rc == 0 and abs(d.get("decision_agreement", 0) - 2 / 3) < 1e-3
    and abs(d.get("cohen_kappa", 0) - 1 / 3) < 1e-3 and len(d.get("disagreements", [])) == 3,
    str({k: d.get(k) for k in ("decision_agreement", "cohen_kappa")}))

# 8) agreement 变异：空 pairs 失败
p = os.path.join(tempfile.gettempdir(), "p0.json")
json.dump({"pairs": []}, open(p, "w"))
rc, _ = run("agreement", p)
add("agreement变异:空pairs->失败", rc == 1, "rc=%d" % rc)

# 9) schema 正向
rc, d = run("schema", os.path.join(FIX, "good_result.json"))
add("schema正向:合规结果零误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:120])

# 10) schema 变异：记录缺来源
def m4(d):
    d["records"][0].pop("source")
rc, d = run("schema", tmp_copy(m4, "s1.json"))
add("schema变异:记录缺source->失败", rc == 1 and any("source" in e for e in d.get("errors", [])), str(d.get("errors"))[:120])

# 11) rankcheck 正向：逐维证据、复算总分、阈值、k 和稳定平局全部通过
rc, d = run("rankcheck", os.path.join(FIX, "good_result.json"))
add("rankcheck正向:复算/证据/稳定排序零误杀", rc == 0 and d.get("ok") and d.get("largest_tie") == 2,
    str(d.get("errors"))[:240])

# 12) 缺年份是声明后的 unknown 元数据，不误杀，也不暗填 0 年
def valid_missing_year(d):
    d["records"][0]["year"] = None
    d["metadata_issues"].append({"record_id": "R1", "fields": ["year"],
                                 "action": "保留未知；排序不使用年份，待来源核验"})
rc, d = run("rankcheck", tmp_copy(valid_missing_year, "q7-valid-missing-year.json"))
add("rankcheck正向:已声明缺年份不误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:180])

# 13) 缺摘要但仍有题录证据时允许暂定，必须显式披露
def valid_missing_abstract(d):
    d["records"][3]["abstract"] = None
    d["metadata_issues"].append({"record_id": "R4", "fields": ["abstract"],
                                 "action": "只按题名暂定；unknown 信息不补造，列人工复核"})
rc, d = run("rankcheck", tmp_copy(valid_missing_abstract, "q7-valid-missing-abstract.json"))
add("rankcheck正向:已声明缺摘要不误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:180])

# 14) 未解决标准冲突可诚实交付，但受影响项必须隔离到 borderline
def valid_conflict(d):
    d["criteria_conflicts"].append({"rule_ids": ["I1", "E3"], "conflict": "同一设计同时命中纳排条款",
                                    "status": "unresolved", "affected_record_ids": ["R2"],
                                    "next_action": "升级协议维护者裁决"})
    d["ranking"][1]["bucket"] = "borderline"
    d["screening"][1]["decision"] = "maybe"
rc, d = run("rankcheck", tmp_copy(valid_conflict, "q7-valid-conflict.json"))
add("rankcheck正向:冲突隔离不误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:180])

# 15) 真空候选集允许空终态，但须给查询、已完成/未完成和下一步
def valid_empty(d):
    d.update(records=[], scores=[], ranking=[], top_k=[], screening=[])
    d["snapshot"]["record_count"] = 0
    d["counts"] = {"records_raw": 0, "records_dedup": 0, "included": 0, "excluded": 0, "maybe": 0}
    d["status"] = "partial"
    d["empty_result"] = {"reason": "no_candidates", "queries_examined": ["Q1", "Q2"],
                         "completed_parts": ["query execution"], "not_completed": ["scoring"],
                         "next_action": "扩展查询后重跑，不声称无相关文献"}
rc, d = run("rankcheck", tmp_copy(valid_empty, "q7-valid-empty.json"))
add("rankcheck正向:显式空结果终态不误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:180])

# 16) 静默空结果失败
def silent_empty(d):
    d.update(records=[], scores=[], ranking=[], top_k=[], screening=[])
    d["snapshot"]["record_count"] = 0
rc, d = run("rankcheck", tmp_copy(silent_empty, "q7-bad-empty.json"))
add("rankcheck变异:静默空候选->失败", rc == 1 and any("empty_result" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 17) 未声明缺摘要失败
def bad_abstract(d):
    d["records"][0]["abstract"] = None
rc, d = run("rankcheck", tmp_copy(bad_abstract, "q7-bad-abstract.json"))
add("rankcheck变异:缺摘要未声明->失败", rc == 1 and any("abstract" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 18) 总分被篡改失败
def bad_total(d):
    d["scores"][0]["total"] = 0.2
rc, d = run("rankcheck", tmp_copy(bad_total, "q7-bad-total.json"))
add("rankcheck变异:加权总分篡改->失败", rc == 1 and any("复算不符" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 19) 漏掉任一候选评分失败
def missing_score(d):
    d["scores"].pop()
rc, d = run("rankcheck", tmp_copy(missing_score, "q7-missing-score.json"))
add("rankcheck变异:候选评分未全覆盖->失败", rc == 1 and any("scores 必须" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 20) 同分缺一人的平局说明失败（检查首条，而非只检查第二条）
def bad_tie(d):
    d["ranking"][2].pop("tie_resolution")
rc, d = run("rankcheck", tmp_copy(bad_tie, "q7-bad-tie.json"))
add("rankcheck变异:同分说明缺失->失败", rc == 1 and any("同分组" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 21) 手工交换并列项破坏稳定键失败
def bad_order(d):
    d["ranking"][2], d["ranking"][3] = d["ranking"][3], d["ranking"][2]
    d["ranking"][2]["rank"], d["ranking"][3]["rank"] = 3, 4
    d["top_k"] = [r["record_id"] for r in d["ranking"]]
rc, d = run("rankcheck", tmp_copy(bad_order, "q7-bad-order.json"))
add("rankcheck变异:破坏确定性平局次序->失败", rc == 1 and any("稳定键" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 22) top-k 与实际前 k 不一致失败
def bad_k(d):
    d["top_k"] = list(reversed(d["top_k"]))
rc, d = run("rankcheck", tmp_copy(bad_k, "q7-bad-k.json"))
add("rankcheck变异:Top-k与排序不一致->失败", rc == 1 and any("top_k" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 23) 接口超时却报 pass 失败
def bad_timeout(d):
    d["source_status"][0].update(status="timeout", detail="gateway timeout", next_action="retry with backoff")
    d["status"] = "pass"
rc, d = run("rankcheck", tmp_copy(bad_timeout, "q7-bad-timeout.json"))
add("rankcheck变异:接口异常却报pass->失败", rc == 1 and any("接口异常" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 24) 权限不足必须留下处置，不得只有状态码
def bad_permission(d):
    d["source_status"][0] = {"source": "PubMed", "status": "permission_denied"}
    d["status"] = "partial"
rc, d = run("rankcheck", tmp_copy(bad_permission, "q7-bad-permission.json"))
add("rankcheck变异:权限异常无后续处置->失败", rc == 1 and any("next_action" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 25) 标准冲突未解决却仍纳入失败
def bad_conflict(d):
    d["criteria_conflicts"].append({"rule_ids": ["I1", "E3"], "conflict": "条款冲突",
                                    "status": "unresolved", "affected_record_ids": ["R1"],
                                    "next_action": "人工裁决"})
rc, d = run("rankcheck", tmp_copy(bad_conflict, "q7-bad-conflict.json"))
add("rankcheck变异:冲突项未隔离->失败", rc == 1 and any("borderline" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 26) unknown 维度没有理由或降置信失败
def bad_unknown(d):
    d["scores"][0]["dim_scores"]["D1"] = None
    d["scores"][0]["unknown_dimensions"] = ["D1"]
rc, d = run("rankcheck", tmp_copy(bad_unknown, "q7-bad-unknown.json"))
add("rankcheck变异:unknown无原因->失败", rc == 1 and any("unknown_dimensions" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 27) 快照版本缺失失败
def bad_version(d):
    d.pop("artifact_version")
rc, d = run("rankcheck", tmp_copy(bad_version, "q7-bad-version.json"))
add("rankcheck变异:产物版本缺失->失败", rc == 1 and any("artifact_version" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

ok = 0
for name, cond, detail in checks:
    print(("PASS" if cond else "FAIL"), name, ("| " + detail if not cond else ""))
    ok += 1 if cond else 0
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
