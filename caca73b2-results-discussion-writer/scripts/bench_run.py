#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_run.py - 确定性路径对照与回归夹具(仅标准库)。

用法: python3 bench_run.py [--write]
在 bench/cases 的 4 个自拟夹具上跑 rd_check.py 并断言预期:
  bio_good / phys_good / degraded : 正向零误杀(fail=0 且 warn=0, exit 0)
  bio_mutant                      : 变异必命中(7 类注入错误全部被检出, exit 1)
另做超长输入稳定性测试(phys_good 内容重复 200 倍, 判定不变且限时)。
对照度量(使用增益): 同一份材料, "直写不核查"路径(bio_mutant 模拟基础 Agent
常见失败模式) vs "本核查流程"路径(bio_good), 比较 fail/warn、按评分维度计数、
spin 检出数与产物数。诚实声明见 bench/bench_report.md。
退出码 0=全部断言通过, 1=有断言失败, 2=环境错误。
"""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # submission/
CASES = os.path.join(ROOT, "bench", "cases")
RD = os.path.join(HERE, "rd_check.py")

# 变异稿注入的 7 类错误 -> 预期 (level, kind); 全部命中才算"变异必命中"
MUTANT_EXPECT = [
    ("fail", "fig_ref"),            # 引用不存在的图3
    ("warn", "fig_ref"),            # 图2 声明却未被引用
    ("fail", "claim"),              # 对不显著数据(S5)用"显著改善"(spin)
    ("warn", "purity"),             # 结果段混解释词+文献引用(2 条)
    ("warn", "number"),             # 55.5% 无来源(及 p=0.2 无来源)
    ("warn", "statcheck"),          # t(18)=3.21 配 p=0.2 重算不符
    ("warn", "source_consistency"),  # S7 significant=true 与 p=0.2 矛盾
    ("warn", "structure"),          # 缺局限小节
    ("warn", "discussion_block"),   # 讨论缺局限落位
    ("warn", "claim"),              # 因果表述无缓冲词
]


def run_check(case):
    d = os.path.join(CASES, case)
    t0 = time.time()
    p = subprocess.run([sys.executable, RD,
                        os.path.join(d, "draft.md"),
                        os.path.join(d, "sources.json")],
                       capture_output=True, text=True)
    rep = json.loads(p.stdout)
    return p.returncode, rep, time.time() - t0


def count(items, level, kind):
    return sum(1 for i in items if i["level"] == level and i["kind"] == kind)


def main():
    if not os.path.isfile(RD):
        print("找不到 rd_check.py", file=sys.stderr)
        return 2
    results, failures = {"cases": {}, "compare": {}, "scale": {}}, []

    # --- 1. 正向夹具: 零误杀 ---
    for case in ("bio_good", "phys_good", "degraded"):
        code, rep, dt = run_check(case)
        s = rep["summary"]
        ok = code == 0 and s["fail"] == 0 and s["warn"] == 0
        results["cases"][case] = {"exit": code, "fail": s["fail"], "warn": s["warn"],
                                  "used_values": s["used_values"],
                                  "total_values": s["total_values"],
                                  "seconds": round(dt, 3), "expect": "fail=0,warn=0,exit=0",
                                  "pass": ok}
        if not ok:
            failures.append("%s 正向误杀: exit=%d fail=%d warn=%d" %
                            (case, code, s["fail"], s["warn"]))

    # --- 2. 变异夹具: 必命中 ---
    code, rep, dt = run_check("bio_mutant")
    items, s = rep["items"], rep["summary"]
    missed = [(lv, k) for lv, k in MUTANT_EXPECT if count(items, lv, k) == 0]
    spin_hits = sum(1 for i in items if i["kind"] == "claim")
    ok = code == 1 and not missed
    results["cases"]["bio_mutant"] = {
        "exit": code, "fail": s["fail"], "warn": s["warn"],
        "expect": "exit=1 且注入的 10 项错误预期全部命中",
        "seeded_expectations": len(MUTANT_EXPECT), "missed": missed,
        "claim_items(spin/强表述检出数)": spin_hits,
        "by_score_dimension": s["by_score_dimension"],
        "seconds": round(dt, 3), "pass": ok}
    if not ok:
        failures.append("bio_mutant 变异漏检: %s (exit=%d)" % (missed, code))

    # --- 3. 对照度量: 直写不核查 vs 本核查流程(同一份生物材料) ---
    base = results["cases"]["bio_mutant"]
    flow = results["cases"]["bio_good"]
    results["compare"] = {
        "说明": "同一材料; 直写路径=bio_mutant(模拟基础 Agent 常见失败模式), "
                "流程路径=bio_good(sources.json+rd_check 修复后)",
        "fail_直写": base["fail"], "fail_流程": flow["fail"],
        "warn_直写": base["warn"], "warn_流程": flow["warn"],
        "错误检出_命中/注入": "%d/%d" % (len(MUTANT_EXPECT) - len(missed),
                                        len(MUTANT_EXPECT)),
        "spin与强表述检出数": spin_hits,
        "产物数_直写": 1,
        "产物数_流程": 4,
        "产物_流程": ["sources.json 证据清单", "draft.md 章节稿",
                      "report.json 核查报告", "result.json 契约结果"],
        "核查耗时秒_变异稿": base["seconds"], "核查耗时秒_流程稿": flow["seconds"]}

    # --- 4. 超长输入稳定性: phys_good 重复 200 倍(~230KB) ---
    draft = open(os.path.join(CASES, "phys_good", "draft.md"), encoding="utf-8").read()
    srcc = os.path.join(CASES, "phys_good", "sources.json")
    big = draft.replace("## Results", "## Results") * 200
    fd, bigp = tempfile.mkstemp(suffix=".md")
    try:
        os.write(fd, big.encode("utf-8"))
        os.close(fd)
        t0 = time.time()
        p = subprocess.run([sys.executable, RD, bigp, srcc],
                           capture_output=True, text=True)
        dt = time.time() - t0
        s = json.loads(p.stdout)["summary"]
        ok = p.returncode == 0 and s["fail"] == 0 and s["warn"] == 0 and dt < 10
        results["scale"] = {"repeat": 200, "bytes": len(big.encode("utf-8")),
                            "exit": p.returncode, "fail": s["fail"], "warn": s["warn"],
                            "seconds": round(dt, 3), "limit_seconds": 10,
                            "expect": "判定与单倍一致(0/0)且 <10s", "pass": ok}
        if not ok:
            failures.append("超长输入不稳定: exit=%d fail=%d warn=%d %.1fs" %
                            (p.returncode, s["fail"], s["warn"], dt))
    finally:
        os.unlink(bigp)

    results["all_pass"] = not failures
    results["failures"] = failures
    blob = json.dumps(results, ensure_ascii=False, indent=1)
    if "--write" in sys.argv:
        out = os.path.join(ROOT, "bench", "bench_results.json")
        open(out, "w", encoding="utf-8").write(blob + "\n")
        print("已写出", out)
    print(blob)
    for f in failures:
        print("FAIL:", f, file=sys.stderr)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
