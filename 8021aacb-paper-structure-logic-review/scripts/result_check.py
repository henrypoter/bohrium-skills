#!/usr/bin/env python3
# result_check.py: result.json 契约自查(仅标准库)。用法: python3 result_check.py result.json | --selftest。仅不可解析/交付缺失 FAIL(exit 1)，其余记 ADVICE。
import json, sys, os, re

REQUIRED = ["case_id","status","summary","deliverables","diagnosis","edit_plan",
            "change_log","sources","fact_source_map","uncertainty",
            "human_confirmation","material_gaps","anomalies","budget",
            "artifact_version","input_manifest","logic_audit"]
STATUS = {"success","partial","failed"}
DIMS = {"research_question","section_structure","argument_chain",
        "paragraph_relation","redundancy","conclusion_boundary"}
SEV = {"high","mid","low"}
NUM = re.compile(r"-?\d+(?:\.\d+)?%?")
CITE = re.compile(r"\[\d+(?:[-,]\d+)*\]|\([A-Z][A-Za-z]+(?: et al\.)?,? \d{4}\)")
ACRO = re.compile(r"\b[A-Z]{2,7}\b")
TERM = re.compile(r"[“\"]{1}[^”\"]{2,24}[”\"]{1}")
NEG = ["不","非","无","未","没有","无法","否认","拒绝","never","no","not","without","unable","fail"]
LABEL = ["数值","引用","实体","术语","否定词"]

def fact_tokens(s):
    sl = s.lower()
    return (set(NUM.findall(s)), set(CITE.findall(s)), set(ACRO.findall(s)),
            set(TERM.findall(s)), {w for w in NEG if w in sl})

def check(r, base):
    hard, adv = [], []
    for k in REQUIRED:
        if k not in r:
            adv.append("缺字段: " + k)
    if r.get("status") not in STATUS:
        adv.append("status 非法")
    if not r.get("case_id"):
        adv.append("case_id 为空")
    for d in r.get("deliverables", []):
        fp = d.get("path", "")
        if not fp:
            hard.append("deliverables 空 path")
            continue
        if not os.path.exists(fp if os.path.isabs(fp) else os.path.join(base, fp)):
            hard.append("交付缺失: " + fp)
    covered = set()
    for i, f in enumerate(r.get("diagnosis", [])):
        for k in ("dimension","location","evidence","criterion","type","severity","action"):
            if k not in f:
                adv.append("diagnosis[%d] 缺 %s" % (i, k))
        if f.get("dimension") not in DIMS:
            adv.append("diagnosis[%d] 维度非法" % i)
        else:
            covered.add(f["dimension"])
        if f.get("severity") not in SEV:
            adv.append("diagnosis[%d] severity 非法" % i)
        loc = str(f.get("location", ""))
        if not (("S" in loc and "P" in loc) or "sec" in loc.lower() or "章" in loc or "节" in loc):
            adv.append("diagnosis[%d] 锚点不规范: %s" % (i, loc))
        if not str(f.get("evidence", "")).strip():
            adv.append("diagnosis[%d] 缺证据" % i)
        if not str(f.get("criterion", "")).strip():
            adv.append("diagnosis[%d] 缺判据" % i)
    for i, c in enumerate(r.get("change_log", [])):
        for k in ("anchor","original","revised","reason","level"):
            if k not in c:
                adv.append("change_log[%d] 缺 %s" % (i, k))
        if c.get("level") not in ("L1","L2"):
            adv.append("change_log[%d] level 应 L1/L2（L3 只建议）" % i)
        ot, vt = fact_tokens(str(c.get("original",""))), fact_tokens(str(c.get("revised","")))
        for k in range(5):
            miss = ot[k] - vt[k]
            if miss:
                if c.get("fact_note"):
                    adv.append("change_log[%d] 有意改动 %s(%s)（fact_note 已解释）" % (i, LABEL[k], ",".join(sorted(miss)[:4])))
                else:
                    adv.append("change_log[%d] 事实漂移:%s 丢 %s，回退 L3/补 fact_note" % (i, LABEL[k], ",".join(sorted(miss)[:4])))
    # 诊断无命中场景：dimensions_checked 记录已逐维核查的维度，与 diagnosis 合并计覆盖
    covered |= {d for d in r.get("dimensions_checked", []) if d in DIMS}
    miss_dims = DIMS - covered
    if miss_dims and r.get("status") == "success":
        adv.append("六维未覆盖: " + ",".join(sorted(miss_dims)))
    if not r.get("diagnosis") and not r.get("dimensions_checked"):
        adv.append("diagnosis 为空且未填 dimensions_checked，无法区分「无命中」与「未核查」")
    # 六维 source-grounded 修改方案显式化：dimension_plan 须逐维给出状态与诊断/编辑编号
    dp = r.get("dimension_plan")
    if dp is None:
        adv.append("缺 dimension_plan：六维 source-grounded 修改方案未显式化")
    else:
        d_ids = {d.get("id") for d in r.get("diagnosis", [])}
        e_ids = {e.get("id") for e in r.get("edit_plan", [])}
        for dim in sorted(DIMS):
            v = dp.get(dim)
            if v is None:
                adv.append("dimension_plan 缺维度: " + dim)
                continue
            st = v.get("status")
            if st not in ("no_finding", "diagnosed"):
                adv.append("dimension_plan[%s] status 非法: %s" % (dim, st))
            di = set(v.get("diagnosis_ids", []))
            ei = set(v.get("edit_ids", []))
            if st == "diagnosed" and not di:
                adv.append("dimension_plan[%s] 标 diagnosed 但无 diagnosis_ids" % dim)
            if st == "no_finding" and (di or ei):
                adv.append("dimension_plan[%s] 标 no_finding 却含 id" % dim)
            bad = di - d_ids
            if bad:
                adv.append("dimension_plan[%s] 引用不存在的 diagnosis id: %s" % (dim, ",".join(sorted(bad))))
            bad = ei - e_ids
            if bad:
                adv.append("dimension_plan[%s] 引用不存在的 edit id: %s" % (dim, ",".join(sorted(bad))))
        # 一致性：每条 diagnosis 的维度必须在 dimension_plan 标 diagnosed 并收录该 id
        for d in r.get("diagnosis", []):
            dim = d.get("dimension")
            if dim in DIMS and dp.get(dim, {}).get("status") != "diagnosed":
                adv.append("diagnosis[%s] 维度 %s 未在 dimension_plan 标 diagnosed" % (d.get("id", "?"), dim))
        # 一致性：edit_plan.ref_diagnosis 的维度须在 dimension_plan 收录该 edit id
        for e in r.get("edit_plan", []):
            rid = e.get("ref_diagnosis")
            dd = next((x for x in r.get("diagnosis", []) if x.get("id") == rid), None)
            if dd:
                dim = dd.get("dimension")
                if dim in DIMS and e.get("id") not in dp.get(dim, {}).get("edit_ids", []):
                    adv.append("edit_plan[%s] 未录入 dimension_plan[%s].edit_ids" % (e.get("id", "?"), dim))
    if r.get("status") == "partial" and not (r.get("material_gaps") or r.get("anomalies")):
        adv.append("partial 但未说明缺口/异常")
    return hard, adv

POS = '{"case_id":"fx","status":"partial","summary":"ok","deliverables":[{"path":"d1.md","kind":"r"}],"diagnosis":[{"id":"D1","dimension":"redundancy","location":"S2.P1.s2","criterion":"same role","evidence":"proposes a scheduler","type":"rep","severity":"mid","action":"delete"}],"edit_plan":[{"id":"E1","action":"delete","level":"L1","anchor":"S2.P1.s2","target":null,"detail":"delete","ref_diagnosis":"D1"}],"change_log":[{"anchor":"S2.P1.s2","level":"L1","original":"proposes a greedy scheduler.","revised":"(deleted)","reason":"dup","fact_note":"delete"}],"sources":["in.md"],"fact_source_map":[],"uncertainty":[],"human_confirmation":[],"material_gaps":["fx"],"anomalies":[],"artifact_version":"paper-structure-logic-review-1.1.0","input_manifest":{"algorithm":"sha256","sha256":"0000000000000000000000000000000000000000000000000000000000000000","bytes":0},"logic_audit":{"rule_version":"logic-audit-1.0.0"},"budget":{"model_requests_used":1,"seconds_used":5,"note":"t"}}'

def dim_plan_from(r):
    """按 diagnosis/edit_plan 生成合法的六维 dimension_plan；无诊断的维度标 no_finding。"""
    dp = {d: {"status": "no_finding", "diagnosis_ids": [], "edit_ids": []} for d in DIMS}
    did2dim = {x.get("id"): x.get("dimension") for x in r.get("diagnosis", [])}
    for d in r.get("diagnosis", []):
        dim = d.get("dimension")
        if dim in dp:
            dp[dim]["status"] = "diagnosed"
            dp[dim]["diagnosis_ids"].append(d.get("id"))
    for e in r.get("edit_plan", []):
        dim = did2dim.get(e.get("ref_diagnosis"))
        if dim in dp:
            dp[dim]["edit_ids"].append(e.get("id"))
    return dp

def selftest():
    pos = json.loads(POS)
    pos["deliverables"][0]["path"] = os.path.abspath(__file__)
    pos["dimension_plan"] = dim_plan_from(pos)
    base = os.path.dirname(os.path.abspath(__file__))
    hard, adv = check(pos, base)
    assert not hard, hard
    assert not adv, adv
    mut = json.loads(json.dumps(pos))
    mut["diagnosis"][0].pop("criterion", None)
    mut["change_log"].append({"anchor":"S4.P1.s1","level":"L3","original":"delay 12%","revised":"delay 9%","reason":"unauthorized"})
    hard2, adv2 = check(mut, base)
    assert not hard2, hard2
    txt = " ".join(adv2)
    assert "criterion" in txt and "L3" in txt and "事实漂移" in txt, adv2
    # 夹具 3：诊断无命中的干净稿——diagnosis 为空 + dimensions_checked 六维齐全 + dimension_plan 全 no_finding → 0 告警
    clean = json.loads(json.dumps(pos))
    clean["status"] = "success"
    clean["diagnosis"], clean["edit_plan"], clean["change_log"] = [], [], []
    clean["material_gaps"] = []
    clean["dimensions_checked"] = sorted(DIMS)
    clean["dimension_plan"] = {d: {"status": "no_finding", "diagnosis_ids": [], "edit_ids": []} for d in DIMS}
    hard3, adv3 = check(clean, base)
    assert not hard3, hard3
    assert not adv3, adv3
    # 夹具 4：diagnosis 空且未填 dimensions_checked → 必须提示无法区分无命中/未核查
    clean2 = json.loads(json.dumps(clean))
    clean2.pop("dimensions_checked")
    hard4, adv4 = check(clean2, base)
    assert not hard4 and any("未核查" in a for a in adv4), adv4
    # 夹具 5：缺 dimension_plan → 必须提示六维方案未显式化
    clean3 = json.loads(json.dumps(pos))
    clean3.pop("dimension_plan")
    hard5, adv5 = check(clean3, base)
    assert not hard5 and any("dimension_plan" in a for a in adv5), adv5
    # 夹具 6：diagnosis 维度未在 dimension_plan 标 diagnosed → 一致性告警
    bad = json.loads(json.dumps(pos))
    bad["dimension_plan"]["redundancy"] = {"status": "no_finding", "diagnosis_ids": [], "edit_ids": []}
    hard6, adv6 = check(bad, base)
    assert not hard6 and any("dimension_plan" in a for a in adv6), adv6
    print("SELFTEST OK: 正向 0 硬伤/0 告警；变异 %d 告警；无命中 0 告警；空诊断 %d 告警；缺/错 dimension_plan 各 %d/%d 告警"
          % (len(adv2), len(adv4), len(adv5), len(adv6)))

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        return selftest()
    if len(sys.argv) < 2:
        print("用法: result_check.py result.json | --selftest")
        sys.exit(1)
    p = sys.argv[1]
    try:
        r = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print("FAIL: result.json 不可解析:", e)
        sys.exit(1)
    hard, adv = check(r, os.path.dirname(os.path.abspath(p)))
    for a in adv:
        print("ADVICE:", a)
    if hard:
        for h in hard:
            print("FAIL:", h)
        sys.exit(1)
    print("PASS: 契约通过（%d 条提示）" % len(adv))

if __name__ == "__main__":
    main()
