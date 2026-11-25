#!/usr/bin/env python3
"""科研可视化标准库回归：正向零误杀 + 变异必命中；全部使用合成数据。"""
import copy
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TOOL = os.path.join(ROOT, "scripts", "visual_tool.py")
TMP = tempfile.mkdtemp(prefix="scientific-visual-bench-")
CHECKS = []


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f: h.update(f.read())
    return h.hexdigest()


def dump(path, obj):
    with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
    return path


def load(path):
    with open(path, encoding="utf-8") as f: return json.load(f)


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True, timeout=25)
    try: data = json.loads(proc.stdout)
    except Exception: data = {"raw": proc.stdout[:300], "stderr": proc.stderr[:300]}
    return proc.returncode, data


def add(name, condition, detail=""):
    CHECKS.append((name, bool(condition), detail))


def write(name, content):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f: f.write(content)
    return path


FIXTURE = os.path.join(HERE, "fixtures", "sample_data.csv")
DATA = write("xy.csv", """x,y,group,date
1,2,A,2026-01-01
2,4,A,2026-01-02
3,6,A,2026-01-03
1.5,2.5,B,2026-01-01
2.5,4.8,B,2026-01-02
3.5,7.2,B,2026-01-03
4,8,B,2026-01-04
5,,B,2026-01-05
""")


def spec(chart, data=DATA, stem=None):
    sid = stem or ("F-" + chart)
    base = {"spec_version":"2.0.0", "case_id":"SYNTHETIC-BENCH", "id":sid,
            "data":data, "source_sha256":digest(data), "output_dir":os.path.join(TMP,sid),
            "chart":chart, "purpose":{"bar":"comparison","scatter":"correlation","line":"trend","box":"distribution","hist":"distribution"}[chart],
            "x":{"column":"x","label":"X value","unit":"mm","type":"continuous"},
            "y":{"column":"y","label":"Y value","unit":"mg/L"},
            "missing_values":["", "-999"], "export":{"width_mm":85,"height_mm":60,"dpi":300},
            "min_font_pt":7, "requirements":{"panel":"a"}}
    if chart == "bar":
        base.update(data=FIXTURE, source_sha256=digest(FIXTURE), where={"unit":"mg/L"}, drop_duplicates=["sample_id"],
                    x={"column":"group","label":"Treatment group","unit":""},
                    y={"column":"measure","label":"Concentration","unit":"mg/L"}, group=None, error="sem",
                    title="Synthetic comparison", purpose="comparison")
    elif chart == "scatter":
        base["group"] = {"column":"group","label":"Group"}; base["title"] = "Synthetic correlation"
    elif chart == "line":
        base["x"] = {"column":"date","label":"Date","unit":"","type":"datetime"}; base["title"] = "Synthetic trend"
    elif chart == "box":
        base["x"] = {"column":"group","label":"Group","unit":""}; base.pop("group",None)
    elif chart == "hist":
        base["x"] = {"column":"y","label":"Y value","unit":"mg/L","type":"continuous"}; base["bins"] = 3
    return base


def make_result(manifest_path, sid="SYNTHETIC-BENCH"):
    m = load(manifest_path); source_hash = m["source_sha256"]
    return {"schema_version":"2.0.0","skill_version":"2.0.0","case_id":sid,"status":"pass",
            "questions":[{"id":"Q1","answer":"合成示例：图件与声明源数据一致。",
                          "evidence":[{"artifact":m["source"],"location":"whole CSV -> figure-data rows","sha256":source_hash}]}],
            "figures":[{"id":m["id"],"manifest":manifest_path,"manifest_sha256":digest(manifest_path),
                        "svg":m["svg"],"png":m["png"],"figure_data":m["figure_data"],
                        "caption":m["caption"],"source_sha256":source_hash}],
            "lineage":{"snapshot":"synthetic-v1","tables":[m["source"]],"source_sha256":source_hash,
                       "commands":["python3 visual_tool.py render figure-spec.json"],
                       "plot_spec":"embedded in manifest","code":os.path.abspath(TOOL)},
            "gain":{"protocol_version":"1.0.0","same_input":True,"same_permissions":True,
                    "baseline":{"status":"not_checked","quality":{"figure_correctness":None},"efficiency":{"redraw_rounds":None},"evidence":[]},
                    "skill":{"status":"not_checked","quality":{"figure_correctness":None},"efficiency":{"redraw_rounds":None},"evidence":[]}},
            "coverage":{k:{"status":"pass","evidence":manifest_path} for k in ("cleaning","statistics","chart_selection","encoding","annotation","readability","export")},
            "unchecked":[],"sources":[{"path":m["source"],"sha256":source_hash}],"uncertainty":[],"change_log":[]}


def render_and_result(s):
    sp = dump(os.path.join(TMP, s["id"] + "-spec.json"), s)
    rc, out = run("render", sp)
    if rc != 0: return rc, out, None, None
    result = make_result(out["manifest"])
    rp = dump(os.path.join(s["output_dir"], "result.json"), result)
    return rc, out, rp, result

# 1) 图型推荐：连续相关/时间趋势/无序比较/分布/构成，不推荐项有理由。
for chart,purpose in (("scatter","correlation"),("line","trend"),("box","distribution"),("hist","distribution")):
    s = spec(chart); s["purpose"] = purpose
    sp = dump(os.path.join(TMP,"recommend-"+chart+".json"),s)
    rc,out = run("recommend",sp)
    expected = "box" if chart == "line" and purpose == "distribution" else chart
    add("recommend 正向："+chart, rc == 0 and out["recommended"] == expected and out["reason"] and out["rejected"], str(out)[:250])
s = spec("bar"); sp = dump(os.path.join(TMP,"recommend-bar.json"),s)
rc,out = run("recommend",sp)
add("recommend 正向：无序类别比较选柱图", rc == 0 and out["recommended"] == "bar" and "pie" in out["rejected"])
s = spec("bar"); s["purpose"] = "composition"; sp = dump(os.path.join(TMP,"recommend-composition.json"),s)
rc,out = run("recommend",sp)
add("recommend 边界：构成建议长度且标明未实现", rc == 0 and out["recommended"] == "stacked_bar" and not out["render_supported"])
s = spec("scatter"); s["purpose"] = "comparison"; sp = dump(os.path.join(TMP,"recommend-bad.json"),s)
rc,out = run("recommend",sp)
add("recommend 变异：字段类型与目的不匹配失败", rc == 1 and not out.get("ok",True))

# 2) 五种图真渲染并全链审计（SVG/PNG/数据/图注/manifest）。
RENDERED = {}
for chart in ("bar","scatter","line","box","hist"):
    rc,out,rp,result = render_and_result(spec(chart))
    add("render 正向：%s 真 SVG+300dpi PNG" % chart, rc == 0 and os.path.isfile(out.get("png","")) and os.path.isfile(out.get("svg","")), str(out)[:400])
    if rp:
        rc2,audit = run("audit",rp)
        add("audit 正向：%s 源数据到视觉元素一致" % chart, rc2 == 0 and audit.get("checked_plot_records",0) > 0, str(audit)[:500])
        RENDERED[chart] = (rp,result,out)

# 3) 数值逐项：bar 均值/SEM/n/原始行定位真实计算。
rp,result,out = RENDERED["bar"]
m = load(out["manifest"])
with open(m["figure_data"],encoding="utf-8",newline="") as f:
    bar_rows = {r["x"]:r for r in csv.DictReader(f)}
add("bar 数据复算：treat=12.8/control=8.6",
    math.isclose(float(bar_rows["treat"]["mean"]),12.8) and math.isclose(float(bar_rows["control"]["mean"]),8.6)
    and bar_rows["treat"]["source_rows"] == "2;3" and bar_rows["control"]["source_rows"] == "5;8", str(bar_rows)[:300])
add("bar 图注：独立 n/SEM/缺失说明", "n=" in m["caption"] and "SEM" in m["caption"] and "排除缺失行" in m["caption"])
add("bar 编码：零基线+单栏宽度", m["axes"]["y"]["domain"][0] <= 0 and m["export"]["width_mm"] == 85)

# 4) 篡改绘图数据，即使重填 figure_data/manifest 哈希也必命中。
bad = copy.deepcopy(result); bm = copy.deepcopy(m)
row_path = bm["figure_data"]
# 文件替换后同步更新两层哈希，测试审计是否仍回源复算。
with open(row_path,encoding="utf-8") as f: content = f.read()
content = content.replace("12.8","999",1)
with open(row_path,"w",encoding="utf-8") as f: f.write(content)
bm["figure_data_sha256"] = digest(row_path)
dump(bm["figure_data"].replace("-figure-data.csv","-manifest.json"),bm)
bad["figures"][0]["manifest_sha256"] = digest(bad["figures"][0]["manifest"])
badp = dump(os.path.join(TMP,"mutated-data-result.json"),bad)
rc,a = run("audit",badp)
add("audit 变异：篡改均值并重填哈希必命中", rc == 1 and "源数据" in str(a["errors"]), str(a)[:400])
# 恢复原图供后续测试
rc,out,rp,result = render_and_result(spec("bar",stem="F-bar-clean")); m = load(out["manifest"])

# 5) 直接改 SVG 后同步重填哈希，确定性重绘仍命中。
svg = m["svg"]
with open(svg,encoding="utf-8") as f: original = f.read()
with open(svg,"w",encoding="utf-8") as f: f.write(original.replace("<svg ","<svg data-tampered='yes' ",1))
m["svg_sha256"] = digest(svg); dump(m["figure_data"].replace("-figure-data.csv","-manifest.json"),m)
result["figures"][0]["manifest_sha256"] = digest(result["figures"][0]["manifest"])
with open(svg,"w",encoding="utf-8") as f: f.write(original)  # 原件恢复，manifest 的篡改哈希仍应失败
# 用新完整渲染制造真正“图和哈希都改”的自洽篡改
rc,out,bad_r,bad_result = render_and_result(spec("scatter",stem="F-tamper-svg"))
bm = load(out["manifest"])
with open(bm["svg"],encoding="utf-8") as f: changed = f.read().replace("<svg ","<svg data-tampered='yes' ",1)
with open(bm["svg"],"w",encoding="utf-8") as f: f.write(changed)
bm["svg_sha256"] = digest(bm["svg"]); dump(bad_result["figures"][0]["manifest"],bm)
bad_result["figures"][0]["manifest_sha256"] = digest(bad_result["figures"][0]["manifest"])
rc,a = run("audit",bad_r)
add("audit 变异：SVG 与哈希同步篡改仍由重绘命中", rc == 1 and any("SVG 视觉元素" in str(e) for e in a["errors"]), str(a)[:400])

# 6) render 异常：哨兵未声明、样本量不足、类别过多、低 DPI、空结果、显著性无证据。
s = spec("bar",stem="F-sentinel"); s["missing_values"] = [""]
sp = dump(os.path.join(TMP,"sentinel.json"),s); rc,out = run("render",sp)
add("render 变异：-999 未声明不得当真实值", rc == 1 and "哨兵" in out.get("error",""))
small = write("small.csv","group,measure\nA,1\n")
s = spec("bar",small,"F-small"); s.update(data=small,source_sha256=digest(small),where={},
    x={"column":"group","label":"Group","unit":""},y={"column":"measure","label":"Measure","unit":"mg/L"},drop_duplicates=False)
sp = dump(os.path.join(TMP,"small.json"),s); rc,out = run("render",sp)
add("render 变异：误差线样本量不足必命中", rc == 1 and "样本量不足" in out.get("error",""))
many = write("many.csv","x,y,group,date\n" + "".join("%d,%d,G%d,2026-01-01\n"%(i,i,i) for i in range(9)))
s = spec("scatter",many,"F-many"); sp = dump(os.path.join(TMP,"many.json"),s); rc,out = run("render",sp)
add("render 变异：类别>8 停止单图硬塞", rc == 1 and "类别数" in out.get("error",""))
s = spec("bar",stem="F-dpi"); s["export"]["dpi"] = 72; sp = dump(os.path.join(TMP,"dpi.json"),s); rc,out = run("render",sp)
add("render 变异：低于300dpi不交付", rc == 1 and "dpi" in out.get("error",""))
s = spec("bar",stem="F-empty"); s["where"] = {"unit":"not-present"}; sp = dump(os.path.join(TMP,"empty.json"),s); rc,out = run("render",sp)
add("render 变异：清洗后空集不画空壳", rc == 1 and "没有可绘制" in out.get("error",""))
s = spec("bar",stem="F-sig"); s["significance"] = [{"x":"A","label":"*","p":0.01}]
sp = dump(os.path.join(TMP,"sig.json"),s); rc,out = run("render",sp)
add("render 变异：显著性缺方法/证据必拒绝", rc == 1 and "显著性" in out.get("error",""))
s = spec("scatter",stem="F-log"); s["log_y"] = True
sp = dump(os.path.join(TMP,"log.json"),s); rc,out = run("render",sp)
add("render 正向：正值 log_y 标注且可执行", rc == 0 and "log10" in load(out["manifest"])["axes"]["y"]["type"], str(out)[:300])

# 7) 中文字体：未映射显式降级，映射后 SVG 原文+PNG 可读替代可审计。
s = spec("bar",stem="F-chinese-missing"); s["y"]["label"] = "浓度"
sp = dump(os.path.join(TMP,"chinese-missing.json"),s); rc,out = run("render",sp)
add("render 变异：中文未映射不静默乱码通过", rc == 1 and out.get("warnings"), str(out)[:250])
s = spec("bar",stem="F-chinese-mapped"); s["y"]["label"] = "浓度"; s["y"]["label_png"] = "Concentration"
rc,out,rp,result = render_and_result(s)
add("render+audit 正向：中文 SVG+显式 PNG 替代", rc == 0 and run("audit",rp)[0] == 0, str(out)[:300])

# 8) schema：示例及版本、图注、证据、覆盖与增益变异。
static_result = os.path.join(HERE,"fixtures","good_result.json")
rc,out = run("schema",static_result)
add("发布夹具：good_result schema 零误杀", rc == 0, str(out)[:300])
base = make_result(load(os.path.join(TMP,"F-line","F-line-manifest.json"))["figure_data"].replace("-figure-data.csv","-manifest.json"))
for name,mutate,needle in [
    ("版本缺失",lambda x:x.pop("schema_version"),"版本"),
    ("图注缺失",lambda x:x["figures"][0].update(caption=""),"caption"),
    ("证据无定位",lambda x:x["questions"][0]["evidence"][0].pop("location"),"location"),
    ("覆盖未检无理由",lambda x:x["coverage"].update(export={"status":"not_checked"}),"reason"),
    ("对照权限不同",lambda x:x["gain"].update(same_permissions=False),"gain"),
    ("pass隐藏不确定性",lambda x:x["uncertainty"].append("hidden"),"pass")]:
    bad = copy.deepcopy(base); mutate(bad); path = dump(os.path.join(TMP,"schema-%d.json"%len(CHECKS)),bad)
    rc,out = run("schema",path)
    add("schema 变异："+name, rc == 1 and needle in str(out.get("errors",[])), str(out)[:250])

# 9) 资源真实存在且 SVG 是可编辑文本、PNG 是真实二进制而非改名文件。
m = load(os.path.join(TMP,"F-line","F-line-manifest.json"))
with open(m["svg"],encoding="utf-8") as f: svg_text = f.read()
with open(m["png"],"rb") as f: signature = f.read(8)
add("产物格式：SVG 可编辑+PNG 真签名", "<text" in svg_text and "viewBox" in svg_text and signature == b"\x89PNG\r\n\x1a\n")
add("产物版本：manifest/spec/result 可定位", m["manifest_version"] == "2.0.0" and m["spec"]["data"] == DATA and len(m["source_sha256"]) == 64)

passed = sum(ok for _,ok,_ in CHECKS)
for name,ok,detail in CHECKS:
    print(("PASS" if ok else "FAIL"),name,("| "+detail if not ok else ""))
print("total %d/%d"%(passed,len(CHECKS)))
sys.exit(0 if passed == len(CHECKS) else 1)
