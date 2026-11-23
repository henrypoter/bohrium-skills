#!/usr/bin/env python3
"""自测（纯标准库，可复跑）：成稿优先主路径的回归线。

证明三条纪律：
  正向零误杀 —— 干净 5 章小论文 issue=warn=0（含 [0,1] 区间、表编号回归）
  变异必命中 —— 植入变异覆盖 5 条核心规则（引用/图表编号/术语/数据），advisory 不阻断（exit 0）
  篇幅纪律   —— plan 落 min_words/min_total_words；assemble 报 LENGTH 与短章，仍 exit 0（只提示不阻断）
另含异常场景夹具：材料缺失 / 中断续写 / 提纲空行与单行多行并存 / 渲染失败降级 / 超长材料。
"""
import json, os, shutil, subprocess, sys, tempfile

D = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
POS = {
    "01_绪论.md": "# 第1章 绪论\n\n此前研究[1]提出注意力机制，[2]改进。流程如图1-1所示。\n\n图1-1 系统流程\n",
    "02_方法.md": "# 第2章 研究方法\n\n本研究采用卷积神经网络（CNN）提取特征，CNN层数为5，结构如图2-1所示。权重归一化到[0,1]区间。\n\n图2-1 网络结构\n",
    "03_结果.md": "# 第3章 结果与分析\n\n在50个样本上准确率达到88.5%，统计如表3-1所示。\n\n表3-1 准确率统计\n",
    "04_结论.md": "# 第4章 结论与展望\n\n实验表明准确率达到88.5%，方法有效。\n",
    "05_参考文献.md": "# 参考文献\n\n[1] Vaswani A. Attention. 2017.\n[2] Li J. Improve. 2020.\n",
}
MUT = dict(POS)
MUT["01_绪论.md"] = "# 第1章 绪论\n\n此前研究[1]提出注意力机制，[2]改进，[3]优化。本文沿用CNN范式，流程如图1-1所示，扩展如图4-1所示。\n\n图1-1 系统流程\n"
MUT["02_方法.md"] = ("# 第2章 研究方法\n\n本研究采用卷积神经网络（CNN）提取特征，结构如图2-1所示，变体如图2-3所示。"
                    "基线为支持向量机（SVM）。\n\n图2-1 网络结构\n\n图2-1 网络结构副本\n\n图2-3 另一结构\n")
MUT["03_结果.md"] = "# 第3章 结果与分析\n\n在50个样本上准确率达到88.5%，支持向量机模型（SVM）为对照。使用GPU加速，GPU集群训练。\n\n表3-1 未被引用统计\n"
MUT["04_结论.md"] = "# 第4章 结论与展望\n\n实验表明准确率达到92.0%，方法有效。\n"
MUT["05_参考文献.md"] = "# 参考文献\n\n[1] Vaswani A. Attention. 2017.\n[2] Li J. Improve. 2020.\n[4] Extra. 2021.\n"

def run(args, env=None):
    e = dict(os.environ)
    if env: e.update(env)
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=e)

def write_chapters(wd, chs):
    cd = os.path.join(wd, "chapters"); os.makedirs(cd, exist_ok=True)
    for fn in sorted(chs):
        open(os.path.join(cd, fn), "w", encoding="utf-8").write(chs[fn])
    return cd

def consistency(wd, out):
    r = run([PY, os.path.join(D, "consistency.py"), os.path.join(wd, "chapters"), "--out", out])
    return r.returncode, json.load(open(out, encoding="utf-8"))

def thesis(*args, env=None):
    return run([PY, os.path.join(D, "thesis.py")] + list(args), env=env)

def main():
    fails = []
    wd = tempfile.mkdtemp(prefix="lwdtest-")
    try:
        # 1) 正向夹具：零误杀（issue=warn=info=0）
        write_chapters(wd, POS)
        rc, rep = consistency(wd, os.path.join(wd, "cons.json"))
        s = rep["summary"]
        print("[正向] exit=%d issue=%d warn=%d info=%d" % (rc, s["issue"], s["warn"], s["info"]))
        if rc != 0 or s != {"issue": 0, "warn": 0, "info": 0}:
            fails.append("正向应零误杀(issue=warn=info=0)")

        # 2) 变异夹具：5 条核心规则逐条必命中（引用/图表编号/术语/数据）
        write_chapters(wd, MUT)
        rc, rep = consistency(wd, os.path.join(wd, "cons-mut.json"))
        types = {x["type"] for x in rep["issues"]}
        s = rep["summary"]
        print("[变异] exit=%d issue=%d warn=%d types=%s" % (rc, s["issue"], s["warn"], sorted(types)))
        if rc != 0: fails.append("advisory 检查应 exit=0")
        if rep.get("rule_count") != 5 or len(rep.get("rules") or []) != 5:
            fails.append("核心规则应恰为 5 条")
        for want in ("cite-missing", "float-missing", "float-number", "term-abbr", "number-unsourced"):
            if want not in types: fails.append("未检出 %s" % want)

        # 3) 管线主路径：plan→write→assemble→render→init→finalize
        twd = os.path.join(wd, "run"); os.makedirs(twd)
        task = os.path.join(twd, "task.md")
        open(task, "w", encoding="utf-8").write("写一篇3000字小论文。提纲：1. 绪论 2. 方法 3. 结果 4. 结论 5. 参考文献\n")
        case = os.path.join(twd, "case.json")
        json.dump({"case_id": "demo", "output_contract": {"manuscript": ""}}, open(case, "w", encoding="utf-8"))
        rc = thesis("--plan", "--task", task, "--materials", twd, "--workdir", twd).returncode
        print("[plan] exit=%d" % rc)
        if rc != 0: fails.append("--plan 失败")
        pl = json.load(open(os.path.join(twd, "plan.json"), encoding="utf-8"))
        if not pl.get("min_total_words") or any(not c.get("min_words") for c in pl["chapters"]):
            fails.append("plan 未落篇幅下限(min_words/min_total_words)")
        write_chapters(twd, POS)
        ms = os.path.join(twd, "manuscript.md")
        r = thesis("--assemble", "--workdir", twd, "--title", "自测论文", "--out", ms)
        print("[assemble] exit=%d manuscript=%s" % (r.returncode, ms))
        if r.returncode != 0 or not os.path.exists(ms): fails.append("--assemble 未产出")
        # 篇幅纪律：短章只提示不阻断；assemble 自带渲染（一条命令出预览）
        if "LENGTH" not in r.stdout or "ASSEMBLE OK" not in r.stdout:
            fails.append("--assemble 未报 LENGTH")
        html = os.path.splitext(ms)[0] + ".html"
        print("[assemble+render] 预览=%s 短章提示=%s" % (os.path.exists(html), "SHORT" in r.stdout))
        rc = thesis("--render", "--src", ms, "--title", "自测论文").returncode
        print("[render] exit=%d" % rc)
        if rc != 0: fails.append("--render 失败")
        out = os.path.join(twd, "result.json")
        thesis("--init", "--case", case, "--out", out)
        rc = thesis("--finalize", "--out", out, "--consistency", os.path.join(wd, "cons.json")).returncode
        print("[finalize] exit=%d" % rc)
        if rc != 0: fails.append("--finalize 失败")

        # 4) 异常夹具
        # 4a 材料缺失：空材料目录 → 缺口章 + 骨架【缺口】，不编造不失败
        gwd = os.path.join(wd, "gap"); os.makedirs(gwd)
        r = thesis("--plan", "--task", task, "--materials", os.path.join(gwd, "none"), "--workdir", gwd)
        gp = json.load(open(os.path.join(gwd, "plan.json"), encoding="utf-8"))
        ngap = sum(1 for c in gp["chapters"] if c["gaps"])
        skel = open(os.path.join(gwd, gp["chapters"][0]["file"]), encoding="utf-8").read()
        print("[异常-材料缺失] exit=%d 缺口章=%d 骨架缺口=%s" % (r.returncode, ngap, "【缺口】" in skel))
        if r.returncode != 0 or ngap == 0 or "【缺口】" not in skel: fails.append("材料缺失未诚实标缺口")

        # 4b 提纲：空行分隔多行提纲（回归）+ 单行多行并存确定性（多行优先）
        tb = os.path.join(gwd, "task_blanks.md")
        open(tb, "w", encoding="utf-8").write("要求如下。\n\n提纲：\n1. 绪论\n\n2. 研究方法\n\n3. 结果与分析\n")
        thesis("--plan", "--task", tb, "--materials", os.path.join(gwd, "none"), "--workdir", os.path.join(wd, "b1"))
        b1 = [c["title"] for c in json.load(open(os.path.join(wd, "b1", "plan.json"), encoding="utf-8"))["chapters"]]
        open(tb, "w", encoding="utf-8").write("提纲：9. 干扰章\n\n提纲：\n1. 绪论\n2. 研究方法\n")
        thesis("--plan", "--task", tb, "--materials", os.path.join(gwd, "none"), "--workdir", os.path.join(wd, "b2"))
        b2 = [c["title"] for c in json.load(open(os.path.join(wd, "b2", "plan.json"), encoding="utf-8"))["chapters"]]
        print("[异常-提纲] 空行提纲=%s 并存提纲=%s" % (b1, b2))
        if b1 != ["绪论", "研究方法", "结果与分析"]: fails.append("空行提纲解析丢章")
        if b2 != ["绪论", "研究方法"]: fails.append("单行多行并存应多行优先")

        # 4c 中断续写：占位未清仍产出（ADVISORY 不阻断）+ --init 不覆盖已有 result.json
        ms2 = os.path.join(gwd, "manuscript.md")
        r = thesis("--assemble", "--workdir", gwd, "--title", "续写", "--out", ms2)
        kept = os.path.exists(ms2) and "【占位" in open(ms2, encoding="utf-8").read()
        r1 = thesis("--init", "--case", case, "--out", out)
        before = open(out, encoding="utf-8").read()
        r2 = thesis("--init", "--case", case, "--out", out)
        same = open(out, encoding="utf-8").read() == before and "EXISTS" in r2.stdout
        print("[异常-中断续写] assemble exit=%d 占位保留=%s init重跑=%s" % (r.returncode, kept, "EXISTS" in r2.stdout))
        if r.returncode != 0 or not kept: fails.append("中断(占位)应仍产出且不阻断")
        if r1.returncode != 0 or r2.returncode != 0 or not same: fails.append("--init 应不覆盖已有 result.json")

        # 4c2 篇幅纪律：故意写 20 字的短章 → 报 SHORT/LENGTH 但 exit=0 仍导出，绝不阻断
        swd2 = os.path.join(wd, "short"); os.makedirs(swd2)
        shutil.copytree(twd, os.path.join(swd2, "wd"), ignore=shutil.ignore_patterns("manuscript.*"))
        for fn in ("01_绪论.md", "02_方法.md"):
            open(os.path.join(swd2, "wd", "chapters", fn), "w", encoding="utf-8").write("# 短章\n\n太短。\n")
        ms3 = os.path.join(swd2, "manuscript.md")
        r = thesis("--assemble", "--workdir", os.path.join(swd2, "wd"), "--title", "短稿", "--out", ms3)
        ok = r.returncode == 0 and os.path.exists(ms3) and "SHORT" in r.stdout and "达标=no" in r.stdout
        print("[篇幅纪律] exit=%d 短章提示=%s 仍导出=%s" % (r.returncode, "SHORT" in r.stdout, os.path.exists(ms3)))
        if not ok: fails.append("短章应只提示(SHORT)不阻断(exit=0)")

        # 4d 渲染失败降级：PATH 无 pandoc → 跳过仅记，exit 0；源缺失 → 跳过，exit 0
        r = thesis("--render", "--src", ms, "--title", "降级", env={"PATH": "/nonexistent"})
        noenv = r.returncode == 0 and "仅 Markdown 直出" in r.stdout
        r2 = thesis("--render", "--src", os.path.join(wd, "no.md"))
        print("[异常-渲染失败] 无pandoc exit=%d 降级=%s 源缺失 exit=%d" % (r.returncode, noenv, r2.returncode))
        if not noenv or r2.returncode != 0: fails.append("渲染失败应诚实降级 exit=0")

        # 4e 超长材料：200KB 材料 → 扫描成功不超限（head 截断），exit 0
        big = os.path.join(wd, "big"); os.makedirs(big)
        open(os.path.join(big, "big.md"), "w", encoding="utf-8").write("数据行。\n" * 40000)
        r = thesis("--plan", "--task", task, "--materials", big, "--workdir", os.path.join(wd, "bigwd"))
        print("[异常-超长材料] exit=%d out=%s" % (r.returncode, r.stdout.strip().splitlines()[0] if r.stdout.strip() else ""))
        if r.returncode != 0: fails.append("超长材料 plan 失败")

        # 5) 重复运行确定性：同输入两次 --plan 产出逐字节一致
        thesis("--plan", "--task", task, "--materials", twd, "--workdir", os.path.join(wd, "r1"))
        thesis("--plan", "--task", task, "--materials", twd, "--workdir", os.path.join(wd, "r2"))
        p1 = open(os.path.join(wd, "r1", "plan.json"), "rb").read()
        p2 = open(os.path.join(wd, "r2", "plan.json"), "rb").read()
        print("[重复运行] plan 逐字节一致=%s" % (p1 == p2))
        if p1 != p2: fails.append("重复 --plan 输出不一致")
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    if fails:
        print("FAIL:", "; ".join(fails)); return 1
    print("SELFTEST PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
