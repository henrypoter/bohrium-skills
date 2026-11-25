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
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix="q9-" + name + "-", suffix=".json", delete=False) as fh:
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

# 11) covercheck 正向：独立复算 2/4 -> 3/4，真实新增仅 REF3
rc, d = run("covercheck", os.path.join(FIX, "good_result.json"))
add("covercheck正向:覆盖闭环零误杀", rc == 0 and d.get("ok")
    and d.get("baseline", {}).get("coverage_rate") == 0.5
    and d.get("final", {}).get("coverage_rate") == 0.75
    and d.get("true_incremental_hits") == ["REF3"], str(d.get("errors"))[:240])

# 12) 合规撤稿排除与无全文保留均不误杀（已在正向夹具内）
add("covercheck正向:撤稿出分母且无全文留分母", d.get("denominator") == 4 and d.get("ok"),
    str(d)[:180])

# 13) 已解决标识冲突允许人工裁决命中
add("covercheck正向:已解决标识冲突不误杀", d.get("ok"), str(d.get("errors"))[:180])

# 14) 来源超时如实标为未决时，允许部分交付而不是误报系统崩溃
def valid_timeout(d):
    d["status"] = "partial"
    d["search_rounds"].append({"round_id": "S2", "query": "pyroptosis", "fields": "title",
                               "source": "Embase", "run_date": "2026-11-20", "status": "timeout",
                               "target_miss_codes": ["M4"], "new_hit_ids": [],
                               "detail": "source timeout after 30s", "next_action": "重试并保留原响应"})
    d["coverage"]["complete"] = False
    d["coverage"]["unresolved_sources"] = ["Embase"]
rc, d = run("covercheck", tmp_copy(valid_timeout, "q9-valid-timeout.json"))
add("covercheck正向:超时诚实部分交付不误杀", rc == 0 and d.get("ok"), str(d.get("errors"))[:180])

# 15) 撤稿仍计入分母失败
def bad_retraction(d):
    d["reference_set"]["records"][4]["countable"] = True
rc, d = run("covercheck", tmp_copy(bad_retraction, "q9-bad-retraction.json"))
add("covercheck变异:撤稿计入分母->失败", rc == 1 and any("撤稿" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 16) 撤稿没有可核验证据失败
def bad_retraction_evidence(d):
    d["reference_set"]["records"][4].pop("retraction_evidence")
rc, d = run("covercheck", tmp_copy(bad_retraction_evidence, "q9-bad-retraction-evidence.json"))
add("covercheck变异:撤稿无来源证据->失败", rc == 1 and any("retraction_evidence" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 17) 用无全文缩小分母失败
def bad_fulltext(d):
    d["reference_set"]["records"][3].update(countable=False, exclusion_reason="无法获取全文")
rc, d = run("covercheck", tmp_copy(bad_fulltext, "q9-bad-fulltext.json"))
add("covercheck变异:无全文被移出分母->失败", rc == 1 and any("无全文" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 18) 未解决 DOI 冲突仍用标识符命中失败
def bad_identifier(d):
    ref = d["reference_set"]["records"][1]
    ref["identifier_conflicts"][0]["resolution_status"] = "unresolved"
    ref["identifier_conflicts"][0].pop("resolution")
    for row in d["hit_matrix"]:
        if row["ref_id"] == "REF2":
            row["baseline_match_rule"] = "identifier"
            row["final_match_rule"] = "identifier"
rc, d = run("covercheck", tmp_copy(bad_identifier, "q9-bad-identifier.json"))
add("covercheck变异:标识冲突未决仍命中->失败", rc == 1 and any("标识未决" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 19) 分母被篡改失败
def bad_denominator(d):
    d["coverage"]["eligible_total"] = 5
rc, d = run("covercheck", tmp_copy(bad_denominator, "q9-bad-denominator.json"))
add("covercheck变异:分母篡改->失败", rc == 1 and any("eligible_total" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 20) 覆盖率被抬高失败
def bad_rate(d):
    d["coverage"]["coverage_rate"] = 1.0
rc, d = run("covercheck", tmp_copy(bad_rate, "q9-bad-rate.json"))
add("covercheck变异:覆盖率虚报->失败", rc == 1 and any("coverage_rate" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 21) 漏掉参考集一条命中状态失败
def bad_matrix(d):
    d["hit_matrix"].pop(0)
rc, d = run("covercheck", tmp_copy(bad_matrix, "q9-bad-matrix.json"))
add("covercheck变异:参考集未逐条比对->失败", rc == 1 and any("hit_matrix" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 22) 残余漏检被静默删除失败
def bad_attribution(d):
    d["miss_attributions"] = []
rc, d = run("covercheck", tmp_copy(bad_attribution, "q9-bad-attribution.json"))
add("covercheck变异:残余漏检无归因->失败", rc == 1 and any("每条最终漏检" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 23) M2 只写数据库覆盖不足失败
def bad_vague(d):
    d["miss_attributions"][0]["attribution"] = {"source": "PubMed", "evidence": "字段太窄"}
rc, d = run("covercheck", tmp_copy(bad_vague, "q9-bad-vague.json"))
add("covercheck变异:M2未指到查询字段->失败", rc == 1 and any("query_id" in e or "field" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 24) 把基线已有命中冒充新增失败
def fake_increment(d):
    d["search_rounds"][0]["new_hit_ids"].append("REF1")
rc, d = run("covercheck", tmp_copy(fake_increment, "q9-fake-increment.json"))
add("covercheck变异:基线命中冒充补检新增->失败", rc == 1 and any("非真实新增" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 25) 声称覆盖提升却删除补检记录失败
def missing_round(d):
    d["search_rounds"] = []
rc, d = run("covercheck", tmp_copy(missing_round, "q9-missing-round.json"))
add("covercheck变异:提升无补检记录->失败", rc == 1 and any("恢复集合" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 26) 超时来源报 pass/complete 失败
def bad_timeout(d):
    valid_timeout(d)
    d["status"] = "pass"
    d["coverage"]["complete"] = True
rc, d = run("covercheck", tmp_copy(bad_timeout, "q9-bad-timeout.json"))
add("covercheck变异:超时却报完整成功->失败", rc == 1 and any("超时" in e or "complete" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 27) 失败查询不能产生新增命中
def bad_failed_hit(d):
    d["search_rounds"][0]["status"] = "timeout"
    d["search_rounds"][0]["detail"] = "timeout"
    d["search_rounds"][0]["next_action"] = "retry"
rc, d = run("covercheck", tmp_copy(bad_failed_hit, "q9-bad-failed-hit.json"))
add("covercheck变异:超时查询伪造新增->失败", rc == 1 and any("不得报告新增" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 28) 命中规则必须来自可复核枚举
def bad_rule(d):
    d["hit_matrix"][0]["final_match_rule"] = "looks_similar"
rc, d = run("covercheck", tmp_copy(bad_rule, "q9-bad-rule.json"))
add("covercheck变异:命中规则不可复核->失败", rc == 1 and any("match_rule" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 29) 冻结版本缺失失败
def bad_freeze(d):
    d["reference_set"].pop("version")
rc, d = run("covercheck", tmp_copy(bad_freeze, "q9-bad-freeze.json"))
add("covercheck变异:参考集未冻结版本->失败", rc == 1 and any("version" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 30) 停止规则缺失失败
def bad_stop(d):
    d.pop("stop_rule")
rc, d = run("covercheck", tmp_copy(bad_stop, "q9-bad-stop.json"))
add("covercheck变异:补检无停止条件->失败", rc == 1 and any("stop_rule" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

# 31) 漏检分类汇总必须与逐条表一致
def bad_code_count(d):
    d["coverage"]["missed_by_code"] = {"M1": 1}
rc, d = run("covercheck", tmp_copy(bad_code_count, "q9-bad-code-count.json"))
add("covercheck变异:漏检分类汇总不一致->失败", rc == 1 and any("missed_by_code" in e for e in d.get("errors", [])),
    str(d.get("errors"))[:180])

ok = 0
for name, cond, detail in checks:
    print(("PASS" if cond else "FAIL"), name, ("| " + detail if not cond else ""))
    ok += 1 if cond else 0
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
