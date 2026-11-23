#!/usr/bin/env python3
"""内容级核验夹具测试：正向零误杀、变异必命中、异常路径诚实降级（仅标准库）。

对 tests/fixtures/positive 的合规样例施加一组单点变异，逐条用真实子进程运行
scripts/evidence_lib.py 与 scripts/check_result.py，断言退出码与规则码：

  - 正向样例必须 rc=0（零误杀，warning 允许）；
  - 每个变异样例必须 rc=1 且输出含对应规则码（必命中）；
  - 异常路径（材料缺失 / 论断超出材料 / 超长输入）按口径 rc=0 且不静默。

结果写 tests/test_results.json；全部符合预期退出 0，否则 1。
用法: python3 tests/run_tests.py
"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
LIB = os.path.join(PKG, "scripts", "evidence_lib.py")
CHK = os.path.join(PKG, "scripts", "check_result.py")
POS = os.path.join(HERE, "fixtures", "positive")
SRC = os.path.join(HERE, "fixtures", "src")


def load_json(name):
    with open(os.path.join(POS, name), encoding="utf-8") as f:
        return json.load(f)


def load_text(name):
    with open(os.path.join(POS, name), encoding="utf-8") as f:
        return f.read()


def run(script, args):
    r = subprocess.run([sys.executable, script] + args,
                       capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout + r.stderr


def check_case(tmp, lib, mat, ms, src_dir=SRC):
    lp = os.path.join(tmp, "evidence_library.json")
    mp = os.path.join(tmp, "claim_matrix.json")
    with open(lp, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(mat, f, ensure_ascii=False, indent=2)
    msp = os.path.join(tmp, "manuscript.md")
    with open(msp, "w", encoding="utf-8") as f:
        f.write(ms)
    args = ["check", lp, mp]
    if src_dir:
        args.append(src_dir)
    args.append(msp)
    return run(LIB, args)


def main():
    base_lib, base_mat = load_json("evidence_library.json"), load_json("claim_matrix.json")
    base_ms = load_text("manuscript.md")
    rows = []

    def expect(name, rc_want, code_want, mutate=None, src_dir=SRC):
        with tempfile.TemporaryDirectory() as tmp:
            lib, mat, ms = copy.deepcopy(base_lib), copy.deepcopy(base_mat), base_ms
            if mutate:
                lib, mat, ms = mutate(lib, mat, ms)
            t0 = time.time()
            rc, out = check_case(tmp, lib, mat, ms, src_dir=src_dir)
            dt = time.time() - t0
        ok = (rc == rc_want) and (code_want is None or code_want in out)
        rows.append({"case": name, "expect_rc": rc_want, "expect_code": code_want,
                     "got_rc": rc, "hit": code_want is None or code_want in out,
                     "seconds": round(dt, 2), "pass": ok})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: rc={rc} (期望 {rc_want}), "
              f"码={code_want or '-'} {'命中' if ok else '未命中'}")

    # ---- 正向：零误杀 ----
    expect("positive_合规样例", 0, None)

    # ---- 变异：必命中 ----
    def m_e1(lib, mat, ms):
        del lib["evidence"][0]["locator"]
        return lib, mat, ms
    expect("E1_缺必填字段", 1, "E1", m_e1)

    def m_e5(lib, mat, ms):
        lib["evidence"][0]["quote"] = "催化剂 X 将反应产率提升了整整三倍"
        return lib, mat, ms
    expect("E5_编造quote", 1, "E5", m_e5)

    def m_e7(lib, mat, ms):
        mat["claims"][0]["text"] = mat["claims"][0]["text"].replace("78%", "98%")
        return lib, mat, ms
    expect("E7_数值与原文不符", 1, "E7", m_e7)

    def m_e9(lib, mat, ms):
        mat["claims"][1]["bindings"] = [b for b in mat["claims"][1]["bindings"]
                                        if b["evidence_id"] == "E2"]
        return lib, mat, ms
    expect("E9_弱证据强结论", 1, "E9", m_e9)

    def m_e10(lib, mat, ms):
        for b in mat["claims"][0]["bindings"]:
            b["scope"] = "partial"
        return lib, mat, ms
    expect("E10_仅partial判supported", 1, "E10", m_e10)

    def m_e2(lib, mat, ms):
        mat["claims"][0]["bindings"][0]["note"] = ""
        return lib, mat, ms
    expect("E2_缺判定理由note", 1, "E2", m_e2)

    def m_e4(lib, mat, ms):
        mat["claims"][1]["verdict"] = "conflicted"
        mat["claims"][1]["bindings"] = mat["claims"][1]["bindings"][:1]
        return lib, mat, ms
    expect("E4_conflicted绑定不足2", 1, "E4", m_e4)

    def m_m1(lib, mat, ms):
        return lib, mat, ms + "\n另有研究支持该结论[C9]。\n"
    expect("M1_正文引用未定义编号", 1, "M1", m_m1)

    def m_dup_ev(lib, mat, ms):
        lib["evidence"].append(copy.deepcopy(lib["evidence"][0]))
        return lib, mat, ms
    expect("E12_证据编号冲突", 1, "E12", m_dup_ev)

    def m_dup_cl(lib, mat, ms):
        mat["claims"].append(copy.deepcopy(mat["claims"][0]))
        return lib, mat, ms
    expect("E12_论断编号冲突", 1, "E12", m_dup_cl)

    def m_e6(lib, mat, ms):
        lib["evidence"][0]["evidence_level"] = "S"
        return lib, mat, ms
    expect("E6_非法证据等级", 1, "E6", m_e6)

    # ---- 异常路径：诚实降级，不误杀、不静默 ----
    def m_unsupported(lib, mat, ms):
        mat["claims"].append({"id": "C3", "text": "催化剂 X 在任意温度下均有效",
                              "verdict": "unsupported", "bindings": []})
        return lib, mat, ms
    expect("ANOM_论断超出材料判unsupported", 0, None, m_unsupported)

    expect("ANOM_材料缺失(E5降级为unchecked)", 0, "E5=unchecked", src_dir=None)

    def long_input():
        with tempfile.TemporaryDirectory() as tmp:
            big = os.path.join(tmp, "src_big")
            os.makedirs(big)
            parts = []
            for fn in ("paper_a.txt", "paper_b.txt"):
                with open(os.path.join(SRC, fn), encoding="utf-8") as f:
                    parts.append(f.read())
            unit = "\n".join(parts)
            with open(os.path.join(big, "big.txt"), "w", encoding="utf-8") as f:
                for _ in range(3000):
                    f.write(unit)
            lib, mat = copy.deepcopy(base_lib), copy.deepcopy(base_mat)
            t0 = time.time()
            rc, out = check_case(tmp, lib, mat, base_ms, src_dir=big)
            dt = time.time() - t0
        ok = rc == 0 and dt < 30
        rows.append({"case": "ANOM_超长输入(~450KB)", "expect_rc": 0,
                     "expect_code": None, "got_rc": rc, "hit": True,
                     "seconds": round(dt, 2), "pass": ok})
        print(f"[{'PASS' if ok else 'FAIL'}] ANOM_超长输入(~450KB): rc={rc}, {dt:.1f}s")
    long_input()

    # ---- result.json 契约校验 ----
    case_p = os.path.join(POS, "case.json")
    rc, out = run(CHK, [case_p, os.path.join(POS, "result.json")])
    ok = rc == 0
    rows.append({"case": "R_合规result.json", "expect_rc": 0, "expect_code": None,
                 "got_rc": rc, "hit": True, "seconds": 0, "pass": ok})
    print(f"[{'PASS' if ok else 'FAIL'}] R_合规result.json: rc={rc}")

    with tempfile.TemporaryDirectory() as tmp:
        bad = load_json("result.json")
        del bad["uncertainty"]
        bp = os.path.join(tmp, "result.json")
        with open(bp, "w", encoding="utf-8") as f:
            json.dump(bad, f, ensure_ascii=False)
        rc, out = run(CHK, [case_p, bp])
    ok = rc == 1 and "uncertainty" in out
    rows.append({"case": "R_缺字段必拒", "expect_rc": 1, "expect_code": "uncertainty",
                 "got_rc": rc, "hit": "uncertainty" in out, "seconds": 0, "pass": ok})
    print(f"[{'PASS' if ok else 'FAIL'}] R_缺字段必拒: rc={rc}")

    n_fail = sum(1 for r in rows if not r["pass"])
    summary = {"total": len(rows), "failed": n_fail,
               "criterion": "正向零误杀(rc=0)；变异必命中(rc=1且码命中)；异常路径按口径降级"}
    out = {"summary": summary, "results": rows}
    rp = os.path.join(HERE, "test_results.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[run_tests] {len(rows)} 项, 失败 {n_fail}；报告已写 {rp}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
