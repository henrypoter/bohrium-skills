#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py — scifig 正向零误杀 + 变异必命中 夹具(纯标准库,临时目录运行,不改仓库)。

正向: 两个示例 spec + 示例材料全链路(check/render/verify/preview/result),
      断言 exit 0、verdict=pass、score=100、quote/entity/required 零问题、map/result 产物齐备。
变异: 10 类,每类断言命中对应问题:
      m1 编造 quote -> quote.missing; m2 quote 落在别句 -> quote.misplaced;
      m3 编造实体名 -> entity.mismatch(含 top-3 建议)+trace.no_token;
      m4 required 未覆盖 -> required.missing 且 result status 强制 partial;
      m5 SVG 改线色 -> semantic.bad; m6 端点互换 -> direction.bad;
      m7 caption 与 sequence 边数错位(含仓库夹具 route_spec.mutation) -> numbering.bad;
      m8 旧字符串 source -> quote.legacy 仅 warn 不升 fail;
      m9 边缺 source -> direction.unsourced(warn, verdict 仍 pass);
      m10 边方向与来源段落矛盾 -> direction.bad + verdict=issues。
硬伤: SVG 缺失/无法解析 -> verdict=invalid 且 exit 1。
exit 0=全部通过; 1=有失败。用法: python3 scripts/selftest.py
"""
import copy, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCIFIG = os.path.join(ROOT, "scripts", "scifig.py")
EX = os.path.join(ROOT, "examples")
FAILS = []

def run(*args):
    return subprocess.run([sys.executable, SCIFIG] + [str(x) for x in args],
                          capture_output=True, text=True)

def ok(name, cond, detail=""):
    print(("%s %s%s" % ("PASS" if cond else "FAIL", name, (" | " + str(detail)[:160]) if detail and not cond else "")))
    if not cond:
        FAILS.append(name)

def load(p):
    return json.load(open(p, encoding="utf-8"))

def wjson(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)

def chain(work, tag, spec_path, materials, status="success"):
    """全链路; 返回 (verify_report, result_json, svg_path, 各步 exit)。"""
    svg = os.path.join(work, tag + ".svg")
    png = os.path.join(work, tag + ".png")
    ver = os.path.join(work, tag + ".verify.json")
    res = os.path.join(work, tag + ".result.json")
    r1 = run("check", spec_path)
    r2 = run("render", spec_path, svg)
    r3 = run("verify", spec_path, svg, *materials)
    r4 = run("preview", svg, png)
    r5 = run("result", "--case-id", tag, "--spec", spec_path, "--svg", svg, "--preview", png,
             "--verify", ver, "--status", status, "--summary", "夹具", "--out", res)
    v = load(ver) if os.path.isfile(ver) else {}
    j = load(res) if os.path.isfile(res) else {}
    return v, j, svg, (r1, r2, r3, r4, r5)

def positive(work, tag, spec_name, mat_name):
    spec = os.path.join(EX, spec_name)
    mat = os.path.join(EX, mat_name)
    v, j, svg, rs = chain(work, tag, spec, [mat])
    ok(tag + " check/render/verify/result exit=0",
       all(r.returncode == 0 for r in (rs[0], rs[1], rs[2], rs[4])),
       [r.returncode for r in rs])
    ok(tag + " preview exit=0(ok 或诚实降级)", rs[3].returncode == 0)
    ok(tag + " verdict=pass", v.get("verdict") == "pass", v.get("verdict"))
    ok(tag + " score=100", (v.get("score") or {}).get("value") == 100, v.get("score"))
    q = v.get("quote") or {}
    ok(tag + " quote 零误杀(无 missing/misplaced/legacy)",
       not (q.get("missing") or q.get("misplaced") or q.get("legacy")), q)
    ok(tag + " entity 零误杀", not (v.get("entity") or {}).get("mismatch"),
       (v.get("entity") or {}).get("mismatch"))
    ok(tag + " required 全覆盖", not (v.get("required") or {}).get("missing"),
       v.get("required"))
    dr = v.get("direction") or {}
    ok(tag + " 箭头方向全部 supported", not (dr.get("unknown") or dr.get("unsourced") or dr.get("bad")),
       dr)
    ok(tag + " 六类检查点齐备",
       [c.get("name") for c in v.get("checks") or []]
       == ["entity", "semantic", "direction", "legend", "layout", "export"], v.get("checks"))
    ok(tag + " SVG 分层命名齐全",
       not (v.get("export") or {}).get("layers_missing"), v.get("export"))
    ok(tag + " connections 带 direction 字段",
       all(c.get("direction") == "supported" for c in (j.get("connections") or [])),
       j.get("connections"))
    ok(tag + " figure_map.md 已产出且含命中行",
       os.path.isfile(svg.rsplit(".", 1)[0] + "_map.md") and
       "命中" in open(svg.rsplit(".", 1)[0] + "_map.md", encoding="utf-8").read())
    ok(tag + " result status=success", j.get("status") == "success", j.get("status"))
    ok(tag + " result outputs 四角色齐备",
       all(k in (j.get("outputs") or {}) for k in ("editable_source", "preview", "mapping", "report")))
    ok(tag + " result sources 为覆盖率摘要", "entities_total" in (j.get("sources") or {})
       and "required_covered" in (j.get("sources") or {}))
    ok(tag + " result changes 两记录位", "changes" in j and "decisions" in j["changes"])
    return spec, mat

def mutate(spec, fn):
    s = copy.deepcopy(load(spec))
    fn(s)
    return s

def main():
    work = tempfile.mkdtemp(prefix="scifig_selftest_")
    print("workdir:", work)
    spec_a, mat_a = positive(work, "pos_apparatus", "apparatus_spec.example.json", "apparatus_material.example.txt")
    spec_r, mat_r = positive(work, "pos_route", "route_spec.example.json", "route_material.example.txt")

    def run_mut(tag, spec, mat, fn, check):
        s = mutate(spec, fn)
        sp = os.path.join(work, tag + ".json")
        wjson(sp, s)
        v, j, svg, rs = chain(work, tag, sp, [mat])
        ok(tag + " verify advisory exit=0", rs[2].returncode == 0, rs[2].returncode)
        check(v, j)

    run_mut("m1_quote_missing", spec_a, mat_a,
            lambda s: s["nodes"][1]["source"].update(quote="量子纠缠发生器"),
            lambda v, j: ok("m1 编造quote -> quote.missing + verdict=issues",
                            "mfc" in (v.get("quote") or {}).get("missing", []) and v.get("verdict") == "issues",
                            v.get("quote")))
    run_mut("m2_quote_misplaced", spec_r, mat_r,
            lambda s: s["nodes"][0]["source"].update(quote="并做稳定性 500h 测试"),
            lambda v, j: ok("m2 quote在他句 -> quote.misplaced",
                            "s1" in (v.get("quote") or {}).get("misplaced", []), v.get("quote")))
    run_mut("m3_entity_fabricated", spec_a, mat_a,
            lambda s: s["nodes"][2].update(label="量子纠缠发生器"),
            lambda v, j: ok("m3 编造实体 -> entity.mismatch 含 top-3 建议 + trace.no_token",
                            any(m["element"] == "mix" and m["suggestions"] for m in (v.get("entity") or {}).get("mismatch", []))
                            and "mix" in ((v.get("trace") or {}).get("no_token") or []),
                            v.get("entity")))
    def m4_check(v, j):
        ok("m4 required未覆盖 -> required.missing", "质谱联用" in (v.get("required") or {}).get("missing", []), v.get("required"))
        ok("m4 result status 强制 partial", j.get("status") == "partial", j.get("status"))
        ok("m4 uncertainty 记录强制降级原因", any("required" in str(u) for u in j.get("uncertainty") or []))
    run_mut("m4_required_missing", spec_a, mat_a,
            lambda s: s.update(required=(s.get("required") or []) + ["质谱联用"]), m4_check)
    # m5 SVG 改线色(渲染产物被篡改)
    s5 = load(spec_a); sp5 = os.path.join(work, "m5.json"); wjson(sp5, s5)
    svg5 = os.path.join(work, "m5.svg")
    run("render", sp5, svg5)
    t = open(svg5, encoding="utf-8").read().replace('stroke="#1565c0"', 'stroke="#e53935"')
    open(svg5, "w", encoding="utf-8").write(t)
    r5 = run("verify", sp5, svg5, mat_a)
    v5 = load(os.path.join(work, "m5.verify.json"))
    ok("m5 线色篡改 -> semantic.bad + exit=0 advisory",
       r5.returncode == 0 and len((v5.get("semantic") or {}).get("bad", [])) >= 5, v5.get("semantic"))
    # m6 端点互换: 用原 spec 渲染的 SVG + 互换端点的 spec 验(方向校验检渲染端点是否落在 to 侧)
    s6 = mutate(spec_a, lambda s: s["edges"][0].update(**{"from": "mfc", "to": "n2"}))
    sp6 = os.path.join(work, "m6.json"); wjson(sp6, s6)
    svg6 = os.path.join(work, "m6.svg")
    run("render", spec_a, svg6)
    r6 = run("verify", sp6, svg6, mat_a)
    v6 = load(os.path.join(work, "m6.verify.json"))
    ok("m6 端点互换 -> direction.bad + exit=0 advisory",
       r6.returncode == 0 and (v6.get("direction") or {}).get("bad"), v6.get("direction"))
    run_mut("m7_caption_mismatch", spec_r, mat_r,
            lambda s: s.update(caption_steps=s["caption_steps"][:5]),
            lambda v, j: ok("m7 caption≠sequence -> numbering.bad",
                            (v.get("numbering") or {}).get("bad"), v.get("numbering")))
    run_mut("m8_legacy_source", spec_a, mat_a,
            lambda s: s["nodes"][0].update(source="句1"),
            lambda v, j: ok("m8 旧字符串source -> legacy 仅 warn, verdict 仍 pass",
                            "n2" in (v.get("quote") or {}).get("legacy", []) and v.get("verdict") == "pass",
                            v.get("quote")))
    run_mut("m9_edge_unsourced", spec_a, mat_a,
            lambda s: s["edges"][0].pop("source", None),
            lambda v, j: ok("m9 边缺 source -> direction.unsourced + 降级 unknown(warn, 不臆造), verdict 仍 pass",
                            "edge-0" in (v.get("direction") or {}).get("unsourced", [])
                            and v.get("verdict") == "pass"
                            and (v.get("score") or {}).get("value") < 100,
                            v.get("direction")))
    def m10_check(v, j):
        ok("m10 边方向与来源段落矛盾 -> direction.bad + verdict=issues",
           "edge-6 source-reversed" in (v.get("direction") or {}).get("bad", [])
           and v.get("verdict") == "issues", v.get("direction"))
        ok("m10 result connections 登记 direction=contradicted",
           any(c.get("id") == "edge-6" and c.get("direction") == "contradicted"
               for c in (j.get("connections") or [])), j.get("connections"))
        ok("m10 uncertainty 登记方向矛盾", any("矛盾" in str(u) for u in j.get("uncertainty") or []))
    run_mut("m10_direction_contradicted", spec_a, mat_a,
            lambda s: s["edges"][6].update(**{"from": "rx", "to": "tc"}), m10_check)
    # 仓库变异夹具(编号-图注错位)
    mf = os.path.join(EX, "route_spec.mutation.example.json")
    msvg = os.path.join(work, "mf.svg")
    run("render", mf, msvg)
    rf = run("verify", mf, msvg)
    vf = load(os.path.join(work, "mf.verify.json"))
    ok("repo夹具 route_spec.mutation -> numbering.bad + exit=0",
       rf.returncode == 0 and (vf.get("numbering") or {}).get("bad"), vf.get("numbering"))
    ok("repo夹具 legacy source 记 warn 不阻断", vf.get("verdict") == "issues" and vf.get("fails") >= 1)
    # 硬伤: SVG 缺失 / 无法解析 -> invalid + exit 1
    rh1 = run("verify", spec_a, os.path.join(work, "no_such.svg"), mat_a)
    ok("硬伤 svg缺失 -> invalid + exit=1",
       rh1.returncode == 1 and "invalid" in rh1.stdout, rh1.returncode)
    bad_svg = os.path.join(work, "bad.svg")
    open(bad_svg, "w", encoding="utf-8").write("<svg><unclosed>")
    rh2 = run("verify", spec_a, bad_svg, mat_a)
    ok("硬伤 svg无法解析 -> invalid + exit=1",
       rh2.returncode == 1 and "invalid" in rh2.stdout, rh2.returncode)

    print("=" * 50)
    print("selftest: %d 项失败" % len(FAILS) if FAILS else "selftest: 全部通过(正向零误杀,变异必命中)")
    sys.exit(1 if FAILS else 0)

if __name__ == "__main__":
    main()
