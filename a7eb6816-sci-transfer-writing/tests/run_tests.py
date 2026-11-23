#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fact_tools.py 夹具自测：正向零误杀、变异必命中、异常与稳定性。仅标准库。
用法：python3 tests/run_tests.py；退出码 0=全部通过，1=有失败。
"""
import json, pathlib, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent
TOOL = ROOT.parent / "scripts" / "fact_tools.py"
FIX = ROOT / "fixtures"
RESULTS = []


def run(args):
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(detail)[:110]) if detail else ""))


def main():
    work = pathlib.Path(tempfile.mkdtemp(prefix="fact_tools_test_"))
    led = work / "ledger.json"
    r = run(["extract", str(FIX / "source.txt"), "-o", str(led)])
    check("extract_base_exit0", r.returncode == 0, r.stderr.strip())
    L = json.loads(led.read_text(encoding="utf-8"))
    check("ledger_fields", bool(L["numbers"]) and len(L["caveats"]) >= 3
          and L["correl_words"] and L["asserted_subject_tier_idx"] == []
          and "图 2" in L["fig_refs"] and "[3]" in L["citations"],
          f"数字键 {len(L['numbers'])}，限定语 {len(L['caveats'])} 组；"
          "限定句中的研究对象不计入已断言层级（保守：更高层级外推必被拦截）")
    check("ledger_no_figcite_digits", "2" not in L["numbers"],
          "图表/引用编号不进数值台账（v3 修复）")

    def check_draft(draft, genre="科普文章", ledger=led):
        out = work / (draft.stem + ".report.json")
        args = ["check", str(ledger), str(draft), "-o", str(out)]
        if genre is not None:
            args += ["--genre", genre]
        r = run(args)
        rep = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
        return r, rep

    VIOL = ["added_numbers_not_in_source", "source_numbers_missing_in_draft",
            "strong_word_escalation", "caveats_missing", "advice_escalation",
            "causal_escalation", "extrapolation_escalation", "unexplained_abbreviations"]

    # 1) 正向夹具：干净稿对 8 类违规字段零误杀
    r, rep = check_draft(FIX / "clean_draft.md")
    viol = {k: rep[k] for k in VIOL if rep[k]}
    check("positive_zero_false_positive", r.returncode == 0 and not viol
          and rep["genre_compliance"]["pass"] is True,
          json.dumps(viol, ensure_ascii=False) or "8 类违规字段全零，体裁合规")
    check("positive_info_fields", rep["fig_refs_missing"] == ["图 2"]
          and rep["citations_missing"] == ["[3]"],
          "提示类字段正常报告（体裁性删除须记入 change_log）")

    # 2) 变异夹具：每类缺陷必命中
    variants = [
        ("v_number", lambda p: any("50" in k for k, _ in p["added_numbers_not_in_source"]), "新增数字50%"),
        ("v_causal", lambda p: any(w == "导致" for w, _, _ in p["causal_escalation"]), "相关→导致"),
        ("v_advice", lambda p: any(w == "应当" for w, _ in p["advice_escalation"]), "新增建议"),
        ("v_extra", lambda p: len(p["extrapolation_escalation"]) >= 1, "外推产业化"),
        ("v_caveat", lambda p: any(n == "待验证" for n, _ in p["caveats_missing"]), "丢限定语"),
        ("v_strong", lambda p: "突破" in p["strong_word_escalation"], "强度词越级"),
        ("v_genre", lambda p: p["genre_compliance"]["pass"] is False, "体裁缺项"),
    ]
    hit = 0
    for name, pred, desc in variants:
        r, rep = check_draft(FIX / (name + ".md"))
        ok = r.returncode == 0 and rep is not None and pred(rep)
        hit += ok
        check("variant_hit_" + name, ok, desc)

    # 3) 论断整体删除：限定语不误报，但被删证据数字必须报遗漏
    r, rep = check_draft(FIX / "v_deleted.md")
    check("deleted_claim_no_caveat_false_positive", rep["caveats_missing"] == [],
          json.dumps(rep["caveats_missing"], ensure_ascii=False))
    check("deleted_evidence_numbers_reported",
          len(rep["source_numbers_missing_in_draft"]) >= 2,
          f"遗漏 {len(rep['source_numbers_missing_in_draft'])} 项（74%、30min 等），可人工处置")

    # 4) 强度词冲突：源文自带“首次”，成稿同级保留不报越级
    led2 = work / "ledger_strong.json"
    run(["extract", str(FIX / "source_strong.txt"), "-o", str(led2)])
    r, rep = check_draft(FIX / "draft_strong_ok.md", ledger=led2)
    check("strong_word_from_source_no_escalation", rep["strong_word_escalation"] == [],
          json.dumps(rep["strong_word_escalation"], ensure_ascii=False))

    # 5) 异常与稳定性
    r = run(["check", str(work / "不存在.json"), str(FIX / "clean_draft.md"), "-o", str(work / "x.json")])
    check("missing_file_friendly", r.returncode == 2 and r.stderr.strip()
          and "Traceback" not in r.stderr, r.stderr.strip())
    r = run(["check", str(led)])
    check("bad_args_exit2", r.returncode == 2 and "Traceback" not in r.stderr, r.stderr.strip())
    r, rep = check_draft(FIX / "clean_draft.md", genre="不存在的体裁")
    check("unknown_genre_skip", r.returncode == 0 and rep["genre_compliance"]["pass"] is None,
          rep["genre_compliance"]["note"])
    r, rep = check_draft(FIX / "clean_draft.md", genre=None)
    check("no_genre_none", r.returncode == 0 and rep["genre_compliance"] is None)

    para = (FIX / "source.txt").read_text(encoding="utf-8")
    long_src = work / "long_source.txt"
    long_src.write_text(para * 300, encoding="utf-8")
    led3 = work / "ledger_long.json"
    r = run(["extract", str(long_src), "-o", str(led3)])
    L3 = json.loads(led3.read_text(encoding="utf-8"))
    check("long_input_stable", r.returncode == 0 and len(L3["numbers"]) == len(L["numbers"]),
          f"长文 {long_src.stat().st_size}B（300 段），数字键仍为 {len(L3['numbers'])}")

    empty = work / "empty.txt"
    empty.write_text("", encoding="utf-8")
    led4 = work / "ledger_empty.json"
    r1 = run(["extract", str(empty), "-o", str(led4)])
    r2, rep2 = check_draft(FIX / "clean_draft.md", ledger=led4)
    check("empty_source_no_crash", r1.returncode == 0 and r2.returncode == 0
          and len(rep2["added_numbers_not_in_source"]) > 0,
          "空材料：稿件数字全部判为新增并告警")

    _, p1 = check_draft(FIX / "clean_draft.md")
    _, p2 = check_draft(FIX / "clean_draft.md")
    check("repeat_deterministic",
          json.dumps(p1, sort_keys=True, ensure_ascii=False)
          == json.dumps(p2, sort_keys=True, ensure_ascii=False))

    passed = sum(1 for _, ok in RESULTS if ok)
    print(f"RESULT {passed}/{len(RESULTS)} 通过")
    print("SUMMARY " + json.dumps({
        "variant_hit": f"{hit}/{len(variants)}",
        "positive_false_positive": len(viol),
        "source_number_keys": len(L["numbers"]),
        "long_input_bytes": long_src.stat().st_size,
    }, ensure_ascii=False))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
