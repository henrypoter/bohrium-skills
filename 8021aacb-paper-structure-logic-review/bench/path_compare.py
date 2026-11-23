#!/usr/bin/env python3
# path_compare.py: 同稿双路径确定性对照（仅标准库）。
# 路径 A = 无诊断直接重写（确定性模拟该流程类别的典型动作：通篇改写、去引用、数值模糊化、无留痕无锚点）；
# 路径 B = 本 Skill 诊断-改稿流程（skeleton 信号→四元组诊断→L1/L2 落笔留痕、L3 只建议、事实保持 diff）。
# 度量：事实漂移数(无解释)/修改留痕数/锚点覆盖/诊断条目/产物数。
# 边界：这是流程级确定性对照，不模拟也不声称 LLM 端到端质量；平台白板对照由组织方生成。
import json, os, re, subprocess, sys, tempfile, importlib.util

ROOT = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.dirname(ROOT)
FIX = os.path.join(ROOT, "fixtures")

def load(mod, path):
    spec = importlib.util.spec_from_file_location(mod, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

sk = load("skeleton_mod", os.path.join(SUB, "scripts", "skeleton.py"))
rc_mod = load("result_check_mod", os.path.join(SUB, "scripts", "result_check.py"))
fact_tokens = rc_mod.fact_tokens

def resolve(text, anchor):
    # 锚点 Si.Pj.sk → 原文句子（复用 skeleton 的切分，保证可复算）
    m = re.match(r"S(\d+)\.P(\d+)\.s(\d+)$", anchor)
    if not m:
        return ""
    si, pi, qi = int(m.group(1)), int(m.group(2)), int(m.group(3))
    secs = sk.split_sections(text)
    if si > len(secs) or pi > len(secs[si - 1][1]):
        return ""
    sents = sk.split_sents(secs[si - 1][1][pi - 1])
    return sents[qi - 1] if qi <= len(sents) else ""

def path_a_rewrite(s, cjk):
    # 确定性模拟「直接通篇改写」的三类典型漂移动作
    r = re.sub(r"\[[\d,\s\-]+\]", "", s)                      # 去引用标记
    r = re.sub(r"（表\s*\d+）|\(Table\s*\d+\)", "", r)          # 去图表锚
    r = re.sub(r"\d+(?:\.\d+)?%", "显著" if cjk else "significantly", r)  # 数值模糊化
    return re.sub(r"\s{2,}", " ", r).strip()

def drift_count(pairs):
    # 返回 (有漂移的修改条数, 丢失事实项总数, 明细)
    n_sent, n_items, detail = 0, 0, []
    for orig, new in pairs:
        ot, vt = fact_tokens(orig), fact_tokens(new)
        lost = []
        for k in range(5):
            miss = ot[k] - vt[k]
            if miss:
                lost.append("%s丢%s" % (rc_mod.LABEL[k], ",".join(sorted(miss)[:3])))
        if lost:
            n_sent += 1
            n_items += sum(len(ot[k] - vt[k]) for k in range(5))
            detail.append("; ".join(lost))
    return n_sent, n_items, detail

def run_case(name):
    path = os.path.join(FIX, name + ".md")
    text = open(path, encoding="utf-8").read()
    paras = [p for _, ps, _ in sk.split_sections(text) for p in ps]
    sents = [s for p in paras for s in sk.split_sents(p)]
    cjk = bool(re.search(r"[一-鿿]", text))

    # ---- 路径 A：无诊断直接重写（通篇逐句改写，无锚点、无留痕） ----
    a_pairs = [(s, path_a_rewrite(s, cjk)) for s in sents]
    a_dsent, a_ditems, a_detail = drift_count(a_pairs)

    # ---- 路径 B：诊断-改稿流程（skeleton → 诊断 → 授权编辑） ----
    out = os.path.join(tempfile.mkdtemp(prefix="w3q5_pc_"), "skel.json")
    subprocess.run([sys.executable, os.path.join(SUB, "scripts", "skeleton.py"), path, "-o", out],
                   capture_output=True, text=True, timeout=90, check=True)
    skel = json.load(open(out, encoding="utf-8"))
    diagnosis, edit_plan, change_log = [], [], []
    cross = [c for c in skel["redundancy_candidates"]
             if c["channel"] == "shingle" and c["position"] == "cross"]
    if cross:
        tgt = cross[0]["pair"][1]
        diagnosis.append({"id": "D1", "dimension": "redundancy", "location": tgt,
                          "criterion": "与 %s 近逐字重复(shingle=%.2f)且非引言-结论呼应" % (cross[0]["pair"][0], cross[0]["similarity"]),
                          "evidence": resolve(text, tgt)[:40], "type": "跨章节复述",
                          "severity": "mid", "action": "delete"})
        edit_plan.append({"id": "E1", "action": "delete", "level": "L1", "anchor": tgt,
                          "target": None, "detail": "删除与 %s 重复的句子" % cross[0]["pair"][0], "ref_diagnosis": "D1"})
        change_log.append({"anchor": tgt, "level": "L1", "original": resolve(text, tgt),
                           "revised": "（删除）", "reason": "与 %s 重复" % cross[0]["pair"][0],
                           "fact_note": "整句删除为 D1 授权的 delete 动作"})
    strong = [b for b in skel["boundary_candidates"] if "强因果" in b["reason"]]
    if strong:
        loc = strong[0]["para"]
        diagnosis.append({"id": "D2", "dimension": "conclusion_boundary", "location": loc,
                          "criterion": "强因果表述且全节无限定词，证据范围限于已报告实验",
                          "evidence": strong[0]["reason"][:40], "type": "结论越界",
                          "severity": "high", "action": "narrow"})
        edit_plan.append({"id": "E2", "action": "narrow", "level": "L3", "anchor": loc,
                          "target": None, "detail": "结论收窄到证据范围（L3 只建议，不落笔）", "ref_diagnosis": "D2"})
    b_pairs = [(c["original"], c["revised"]) for c in change_log]
    b_dsent_raw, _, _ = drift_count(b_pairs)
    b_unexplained = sum(1 for c in change_log
                        if drift_count([(c["original"], c["revised"])])[0] and not c.get("fact_note"))

    return {
        "case": name,
        "path_A_no_diagnosis_rewrite": {
            "rewritten_sentences": len(a_pairs),
            "fact_drift_sentences": a_dsent, "fact_drift_items": a_ditems,
            "fact_drift_detail": a_detail[:4],
            "change_traces": 0, "anchored_edits": 0, "diagnosis_items": 0,
            "l3_guard": "无权限概念：结论句一并被改写", "deliverables": 1},
        "path_B_diagnosis_edit_flow": {
            "rewritten_sentences": len(change_log),
            "fact_drift_sentences_unexplained": b_unexplained,
            "fact_drift_sentences_explained_by_fact_note": b_dsent_raw - b_unexplained,
            "change_traces": len(change_log), "anchored_edits": len(change_log),
            "diagnosis_items": len(diagnosis),
            "edit_plan_items": len(edit_plan),
            "l3_suggestions_not_applied": sum(1 for e in edit_plan if e["level"] == "L3"),
            "deliverables": 4},
        "diagnosis_sample": diagnosis,
    }

def main():
    results = [run_case(n) for n in ("var_zh", "var_en")]
    out = os.path.join(ROOT, "bench_results.json")
    json.dump({"note": "同稿双路径确定性流程对照；非平台白板；不声称 LLM 端到端质量增益",
               "cases": results}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("| 口径 | A 无诊断直接重写 | B 诊断-改稿流程 |")
    print("|-|-|-|")
    for r in results:
        a, b = r["path_A_no_diagnosis_rewrite"], r["path_B_diagnosis_edit_flow"]
        print("| [%s] 事实漂移（无解释，条/项） | %d/%d | %d/0 |"
              % (r["case"], a["fact_drift_sentences"], a["fact_drift_items"], b["fact_drift_sentences_unexplained"]))
        print("| [%s] 修改留痕数 | %d | %d |" % (r["case"], a["change_traces"], b["change_traces"]))
        print("| [%s] 锚点可复核修改 | %d | %d |" % (r["case"], a["anchored_edits"], b["anchored_edits"]))
        print("| [%s] 四元组诊断条目 | %d | %d |" % (r["case"], a["diagnosis_items"], b["diagnosis_items"]))
        print("| [%s] L3 越权落笔 | 结论句被直接改写 | 0（%d 条仅建议） |"
              % (r["case"], b["l3_suggestions_not_applied"]))
        print("| [%s] 产物数 | %d | %d |" % (r["case"], a["deliverables"], b["deliverables"]))
    print("-> %s" % out)

if __name__ == "__main__":
    main()
