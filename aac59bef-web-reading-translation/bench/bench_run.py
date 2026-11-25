#!/usr/bin/env python3
"""可复跑标准库 bench：每个命令均有正向零误杀与故障/数据变异必命中。"""
import argparse
import copy
import hashlib
import http.server
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AUTO = os.path.join(ROOT, "scripts", "auto_tool.py")
WEB = os.path.join(ROOT, "scripts", "webread.py")
ARTICLE = os.path.join(HERE, "fixtures", "article.html")
TMP = tempfile.mkdtemp(prefix="webread-bench-")
CHECKS = []


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def dump(name, value):
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    return path


def run(tool, *args):
    process = subprocess.run([sys.executable, tool, *map(str, args)], capture_output=True, text=True, timeout=30)
    try:
        value = json.loads(process.stdout)
    except Exception:
        value = {"raw": process.stdout[:300], "stderr": process.stderr[:300]}
    return process.returncode, value


def run_web(*args):
    return run(WEB, *args)


def run_auto(*args):
    return run(AUTO, *args)


def add(name, condition, detail=""):
    CHECKS.append((name, bool(condition), str(detail)[:500]))


def mutate(value):
    return copy.deepcopy(value)


def errors(value):
    return value.get("errors", []) + value.get("verification", {}).get("errors", [])


def write_bytes(name, data):
    path = os.path.join(TMP, name)
    with open(path, "wb") as handle:
        handle.write(data)
    return path


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/article":
            with open(ARTICLE, "rb") as handle:
                body = handle.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("ETag", '"bench-v1"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/login":
            body = b"authentication required"
            self.send_response(401)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/rate":
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://localhost:%d/article" % self.server.server_port)
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(0.3)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            try:
                self.wfile.write(b"ok")
            except BrokenPipeError:
                pass  # 客户端按预期超时断开。
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


def start_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def make_translation(corpus):
    targets = {
        "Abstract": "摘要",
        "We evaluate a graph neural network in a reproducible benchmark.": "我们在可复现基准中评估图神经网络。",
        "Introduction": "引言",
        "Graph neural network (GNN) representations preserve molecular symmetry.": "图神经网络（GNN）表示保留分子对称性。",
        "Methods": "方法",
        "Table 1: Measurements under controlled conditions.": "表 1：受控条件下的测量结果。",
        "Figure 1: A stable schematic of the workflow.": "图 1：稳定的工作流示意图。",
    }
    paragraphs = []
    for block in corpus["blocks"]:
        source = block["text"]
        if source.startswith("At 25 "):
            target = "在 25 °C 下，使用 0.5 mL，并对样本_{2} 计算 \\(E=mc^{2}\\) [1]。"
        elif source.startswith("| Metric |"):
            target = "| 指标 | 数值 |\n| --- | --- |\n| 质量 | 2.5 kg |\n| 时间 | 30 s |"
        else:
            target = targets.get(source, "【bench 未提供译文】")
        paragraphs.append({"id": block["id"], "target": target})
    return {"schema_version": "2.0.0", "corpus_sha256": corpus["corpus_sha256"],
            "metadata": copy.deepcopy(corpus["metadata"]), "paragraphs": paragraphs,
            "glossary": [{"source": "graph neural network", "source_variants": ["graph neural net"], "target": "图神经网络",
                          "first_target": "图神经网络", "target_variants": ["图神经网络（GNN）", "GNN"],
                          "occurrence_policy": "first_full_then_abbreviation"}],
            "semantic_review": {"status": "not_checked", "reason": "bench 只测机器可证保真，不冒充人工语义审校"}}


def artifact(path, role):
    media = "text/html" if path.endswith(".html") else "application/json"
    return {"path": path, "sha256": digest(path), "media_type": media, "role": role}


def make_result(bilingual, artifact_paths, case_path, task_path):
    source = bilingual["source"]
    steps = [
        {"id": "W1", "step": "抓取并锁定页面版本", "depends_on": [], "input": "article URL", "output": artifact_paths["snapshot"], "state": "done"},
        {"id": "W2", "step": "正文抽取与锚点", "depends_on": ["W1"], "input": artifact_paths["snapshot"], "output": artifact_paths["corpus"], "state": "done"},
        {"id": "W3", "step": "逐段翻译与术语约束", "depends_on": ["W2"], "input": artifact_paths["corpus"], "output": artifact_paths["translation"], "state": "done"},
        {"id": "W4", "step": "保真校验与来源审计", "depends_on": ["W3"], "input": artifact_paths["translation"], "output": artifact_paths["bilingual"], "state": "done"},
    ]
    logs = [{"step": step["id"], "started_at": "2026-01-01T00:0%d:00Z" % i,
             "ended_at": "2026-01-01T00:0%d:30Z" % i, "result": "ok",
             "command": "bench " + step["step"]} for i, step in enumerate(steps)]
    return {"case_id": "bench-local", "status": "pass", "schema_version": "2.0.0",
            "skill_version": "3.0.0", "tool_version": "3.0.0", "run_id": "bench-run-001",
            "generated_at": "2026-01-01T00:05:00Z",
            "input": {"case_path": case_path, "task_path": task_path,
                      "case_sha256": digest(case_path), "task_sha256": digest(task_path)},
            "source": copy.deepcopy(source), "corpus_sha256": bilingual["corpus_sha256"],
            "full_text_sha256": bilingual["full_text_sha256"], "extraction_status": bilingual["extraction_status"],
            "paragraphs": copy.deepcopy(bilingual["paragraphs"]),
            "machine_verification": copy.deepcopy(bilingual["verification"]),
            "workflow": steps, "state": {"completed_steps": [x["id"] for x in steps], "failed_step": None, "resume_point": None},
            "data_passing": [{"from": "W1", "to": "W2", "field_mapping": {"snapshot": "html"}, "permission_scope": "green"},
                             {"from": "W2", "to": "W3", "field_mapping": {"blocks": "translations"}, "permission_scope": "green"},
                             {"from": "W3", "to": "W4", "field_mapping": {"translations": "paragraphs"}, "permission_scope": "green"}],
            "failures": [], "run_log": logs, "gain": {"status": "not_measured", "reason": "bench 不冒充基础 Agent 实测；正式对照需 compare 输入两份真实运行记录", "baseline": None, "skill": None},
            "artifacts": [artifact(artifact_paths["snapshot"], "source_snapshot"), artifact(artifact_paths["corpus"], "source_corpus"),
                          artifact(artifact_paths["translation"], "editable_translation"), artifact(artifact_paths["bilingual"], "aligned_bilingual")],
            "unchecked": [], "sources": [{"url": source["url"], "fetched_at": source["fetched_at"],
                                           "snapshot_sha256": source["snapshot_sha256"], "location": source["root_dom_path"]}],
            "uncertainty": [{"item": "semantic_fidelity", "reason": "机检不代替人工语义审校"}],
            "change_log": [{"time": "2026-01-01T00:05:00Z", "action": "create", "target": "bench result"}]}


def failure(step="W4", key="W4-bench-failure"):
    return {"step": step, "kind": "translation_interrupted", "signal": "bench injected interruption",
            "action": "保留译文，从断点补齐该段", "state": "failed", "retry": 1, "idempotency_key": key}


def run_compare_case(result, result_path):
    source_hash = result["source"]["snapshot_sha256"]
    base = {"case_id": "bench-local", "run_id": "baseline-001", "source_sha256": source_hash,
            "permissions": ["http:read", "filesystem:write"],
            "totals": {"expected_body_blocks": 9, "extracted_body_blocks": 6, "translated_body_blocks": 5,
                       "quote_verified_blocks": 3, "protected_tokens_total": 20, "protected_token_violations": 4,
                       "glossary_checks": 4, "glossary_consistent_checks": 2, "manual_actions": 12,
                       "repeated_fetches": 3, "elapsed_seconds": 120},
            "evidence": {"result_path": result_path, "log_path": result_path}}
    skill = mutate(base)
    skill.update(run_id="skill-001")
    skill["totals"].update(extracted_body_blocks=9, translated_body_blocks=9, quote_verified_blocks=9,
                           protected_token_violations=0, glossary_consistent_checks=4,
                           manual_actions=2, repeated_fetches=0, elapsed_seconds=50)
    return base, skill


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", help="可选：把每项结果写成 JSON 报告")
    args = parser.parse_args()
    server = start_server()
    port = server.server_port
    snapshot = os.path.join(TMP, "article.html")
    meta_path = os.path.join(TMP, "fetch.json")
    corpus_path = os.path.join(TMP, "corpus.json")
    translation_path = os.path.join(TMP, "translation.json")
    bilingual_path = os.path.join(TMP, "bilingual.json")
    url = "http://127.0.0.1:%d/article" % port
    try:
        # fetch：正向、401、跨域、超时。
        rc, data = run_web("fetch", url, "--out", snapshot, "--meta", meta_path, "--timeout", "2")
        add("fetch 正向: 本地真实 HTTP 字节快照零误杀", rc == 0 and data.get("status") == "done" and digest(snapshot) == data.get("sha256"), data)
        add("fetch 正向: ETag/URL/时间版本轨迹齐全", data.get("page_version") is None and bool(load(meta_path).get("headers", {}).get("etag")) and bool(load(meta_path).get("finished_at")), "page_version 由 extract 写入；fetch headers 保留 ETag")
        rc, data = run_web("fetch", "http://127.0.0.1:%d/login" % port, "--out", os.path.join(TMP, "login.html"), "--meta", os.path.join(TMP, "login.json"), "--timeout", "2")
        add("fetch 变异: HTTP401->login_expired 且拒绝正文", rc == 1 and data.get("failure", {}).get("kind") == "login_expired" and not os.path.exists(os.path.join(TMP, "login.html")), data)
        rc, data = run_web("fetch", "http://127.0.0.1:%d/rate" % port, "--out", os.path.join(TMP, "rate.html"), "--meta", os.path.join(TMP, "rate.json"), "--timeout", "2")
        add("fetch 变异: HTTP429->rate_limited 并有界恢复", rc == 1 and data.get("failure", {}).get("kind") == "rate_limited" and "有界" in data.get("failure", {}).get("action", ""), data)
        rc, data = run_web("fetch", "http://127.0.0.1:%d/redirect" % port, "--out", os.path.join(TMP, "redirect.html"), "--meta", os.path.join(TMP, "redirect.json"), "--timeout", "2")
        add("fetch 变异: 跨域重定向停止", rc == 1 and data.get("failure", {}).get("kind") == "cross_domain_redirect", data)
        rc, data = run_web("fetch", "http://127.0.0.1:%d/slow" % port, "--out", os.path.join(TMP, "slow.html"), "--meta", os.path.join(TMP, "slow.json"), "--timeout", "0.01")
        add("fetch 变异: 超时可识别并给恢复动作", rc == 1 and data.get("failure", {}).get("kind") == "timeout" and bool(data.get("failure", {}).get("action")), data)
        browser_snapshot = write_bytes("browser.html", open(snapshot, "rb").read())
        stamped_meta = os.path.join(TMP, "stamped.json"); stamped_corpus = os.path.join(TMP, "stamped-corpus.json")
        rc, data = run_web("stamp", browser_snapshot, "--url", url, "--out", stamped_meta, "--capture-method", "browser_rendered", "--capture-notes", "scrolled; network idle; all pagination expanded")
        rc2, extracted = run_web("extract", browser_snapshot, "--meta", stamped_meta, "--out", stamped_corpus)
        add("stamp 正向: 浏览器快照同构元数据可复跑抽取", rc == 0 and rc2 == 0 and data.get("sha256") == digest(browser_snapshot) and load(stamped_corpus)["source"]["capture_method"] == "browser_rendered", data)
        empty_snapshot = write_bytes("empty.html", b"")
        rc, data = run_web("stamp", empty_snapshot, "--url", url, "--out", os.path.join(TMP, "empty-meta.json"), "--capture-method", "browser_rendered")
        add("stamp 变异: 空快照拒绝伪造版本", rc == 1 and data.get("failure", {}).get("kind") == "unversioned_snapshot", data)

        # extract：真实 HTTP 快照上的正文隔离与来源字段。
        rc, data = run_web("extract", snapshot, "--meta", meta_path, "--out", corpus_path)
        corpus = load(corpus_path)
        joined = "\n".join(x["text"] for x in corpus["blocks"])
        add("extract 正向: 真实 HTTP 页面正文抽取零误杀", rc == 0 and data.get("status") == "pass" and corpus["complete"], data)
        add("extract 正向: 导航/推荐/参考文献不混入正文", "related-articles" not in joined and "cited paper" not in joined and any(x["reason"] == "reference_list_excluded_from_body" for x in corpus["excluded"]), corpus["excluded"])
        add("extract 正向: 章节/图注/表注/表格/公式齐全", corpus["coverage"]["headings"] >= 3 and corpus["coverage"]["figure_captions"] == 1 and corpus["coverage"]["table_captions"] == 1 and corpus["coverage"]["tables"] == 1 and corpus["coverage"]["formulas"] == 1, corpus["coverage"])
        add("extract 正向: quote/dom/anchor/offset/hash 逐项可定位", all(x["quote"] == x["text"] and x["dom_path"] and x["html_anchor"] and x["char_end"] > x["char_start"] and len(x["text_sha256"]) == 64 for x in corpus["blocks"]), corpus["blocks"][:1])
        add("extract 正向: 示例导航中的 sign in 不误判登录失效", not any(x["kind"] == "login_expired" for x in corpus["issues"]), corpus["issues"])
        formula_block = next(x for x in corpus["blocks"] if x["formulas"])
        table_block = next(x for x in corpus["blocks"] if x["kind"] == "table")
        add("extract 正向: 公式 TeX 与表格行列原样保留", formula_block["formulas"][0]["value"] == "E=mc^{2}" and table_block["table"]["n_rows"] == 3 and table_block["table"]["n_columns"] == 2, corpus["coverage"])
        meta_base = load(meta_path)
        fallback_html = """<html><head><title>Fallback Paper</title></head><body><article><h1>Fallback Paper</h1><div class='ltx_authors'><span class='ltx_personname'>Jane Doe<span class='ltx_note_outer'><span class='ltx_note_content'>Author contribution note that must not become part of her name.</span></span></span></div><p>The first substantial paragraph describes a reproducible scientific method in sufficient detail.</p><p>The second substantial paragraph contains a note<sup>1</sup> and continues with enough scientific text.</p><p>The third substantial paragraph reports measurements without changing their technical meaning.</p><div role='doc-footnote'><p>1 This is an independent explanatory footnote retained for aligned translation.</p></div></article></body></html>"""
        fallback_path = write_bytes("fallback.html", fallback_html.encode())
        fallback_meta = mutate(meta_base); fallback_meta["sha256"] = digest(fallback_path)
        fallback_meta_path = dump("fallback-meta.json", fallback_meta); fallback_out = os.path.join(TMP, "fallback-corpus.json")
        rc, info = run_web("extract", fallback_path, "--meta", fallback_meta_path, "--out", fallback_out)
        fallback = load(fallback_out)
        add("extract 正向: 无 citation 元数据时作者回退且脚注不内联重复", rc == 0 and fallback["metadata"]["authors"] == ["Jane Doe"] and fallback["coverage"]["footnotes"] == 2 and not any("independent explanatory footnote" in x["text"] for x in fallback["blocks"] if x["kind"] == "paragraph"), {"metadata": fallback["metadata"], "coverage": fallback["coverage"]})

        # 登录/付费墙/动态失败/摘要页/懒加载/分页/元素缺失。
        raw = open(ARTICLE, encoding="utf-8").read()
        variants = {
            "login": ("<html><head><title>Session expired</title></head><body><form><input type='password'><p>Sign in to view full text</p></form></body></html>", "login_expired", "failed"),
            "paywall": ("<html><body><article><h1>Paper</h1><p>This is abstract only.</p><div>Subscribe to view this article. Subscription required.</div></article></body></html>", "paywall", "failed"),
            "dynamic": ("<html><body><main id='app'></main><script>loadArticle()</script></body></html>", "dynamic_render_failed", "failed"),
            "abstract": (raw.split('<section id="introduction">')[0] + "</section></article></body></html>", "abstract_only", "failed"),
            "missing": ("<html><body><div>not found</div></body></html>", "missing_article_element", "failed"),
        }
        for name, (html_text, kind, status) in variants.items():
            path = write_bytes(name + ".html", html_text.encode("utf-8"))
            meta = mutate(meta_base); meta["sha256"] = digest(path); meta["bytes"] = os.path.getsize(path)
            mp = dump(name + "-meta.json", meta); out = os.path.join(TMP, name + "-corpus.json")
            rc, info = run_web("extract", path, "--meta", mp, "--out", out)
            issues = load(out).get("issues", []) if os.path.exists(out) else []
            add("extract 变异: %s 被标 %s" % (kind, status), rc == 1 and info.get("status") == status and any(x["kind"] == kind for x in issues), info)
        paginated = raw.replace("</article>", '<a rel="next" href="page2.html">Next</a></article>')
        path = write_bytes("pagination.html", paginated.encode()); meta = mutate(meta_base); meta["sha256"] = digest(path)
        mp = dump("pagination-meta.json", meta); out = os.path.join(TMP, "pagination-corpus.json")
        rc, info = run_web("extract", path, "--meta", mp, "--out", out)
        add("extract 变异: 分页未合并不得 complete", rc == 0 and info.get("status") == "issues" and not load(out)["complete"] and any(x["kind"] == "pagination" for x in load(out)["issues"]), info)
        lazy = raw.replace('src="figure1.png"', 'src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==" data-src="figure1.png"')
        path = write_bytes("lazy.html", lazy.encode()); meta = mutate(meta_base); meta["sha256"] = digest(path)
        mp = dump("lazy-meta.json", meta); out = os.path.join(TMP, "lazy-corpus.json")
        rc, info = run_web("extract", path, "--meta", mp, "--out", out)
        add("extract 变异: 懒加载占位资源标缺口", rc == 0 and not load(out)["complete"] and any(x["kind"] == "lazy_load_unresolved" for x in load(out)["issues"]), info)
        path = write_bytes("tampered.html", raw.replace("reproducible", "tampered").encode())
        rc, info = run_web("extract", path, "--meta", meta_path, "--out", os.path.join(TMP, "tampered-corpus.json"))
        add("extract 变异: 快照哈希不符拒绝抽取", rc == 1 and info.get("failure", {}).get("kind") == "extract_error", info)

        # align：正向全绿与逐类保真变异。
        translation = make_translation(corpus)
        dump("translation.json", translation)
        rc, info = run_web("align", corpus_path, translation_path, "--out", bilingual_path)
        bilingual = load(bilingual_path)
        add("align 正向: 全量对齐/术语/公式/表格零误杀", rc == 0 and info.get("ok") and bilingual["verification"]["status"] == "pass", info)
        add("align 正向: 每段输出原始定位且语义能力不夸大", len(bilingual["paragraphs"]) == len(corpus["blocks"]) and bilingual["verification"]["semantic_fidelity"] == "not_checked_by_tool" and all(x["location"]["dom_path"] for x in bilingual["paragraphs"]), bilingual["verification"])
        synonym_corpus = mutate(corpus)
        synonym_corpus["blocks"][1]["text"] = synonym_corpus["blocks"][1]["text"].replace("graph neural network", "graph neural net")
        synonym_corpus["blocks"][1]["quote"] = synonym_corpus["blocks"][1]["text"]
        synonym_corpus["blocks"][1]["text_sha256"] = hashlib.sha256(synonym_corpus["blocks"][1]["text"].encode()).hexdigest()
        synonym_corpus["full_text_sha256"] = hashlib.sha256("\n\n".join(x["text"] for x in synonym_corpus["blocks"]).encode()).hexdigest()
        unsigned = {k: v for k, v in synonym_corpus.items() if k != "corpus_sha256"}
        synonym_corpus["corpus_sha256"] = hashlib.sha256(json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        synonym_translation = make_translation(synonym_corpus)
        synonym_translation["paragraphs"][1]["target"] = "我们在可复现基准中评估图神经网络。"
        scp = dump("synonym-corpus.json", synonym_corpus); stp = dump("synonym-translation.json", synonym_translation)
        rc, info = run_web("align", scp, stp, "--out", os.path.join(TMP, "synonym-bilingual.json"))
        add("align 正向: source_variants 同义词仍统一译法", rc == 0 and info.get("ok"), info)

        def alignment_mutant(name, edit, needle, fatal=False):
            bad = mutate(translation); edit(bad)
            path = dump("mutant-" + name + ".json", bad)
            rc, info = run_web("align", corpus_path, path, "--out", os.path.join(TMP, "mutant-" + name + "-out.json"))
            add("align 变异: " + name, rc == 1 and any(needle in x for x in errors(info)), errors(info))

        alignment_mutant("漏段必命中", lambda x: x["paragraphs"].pop(), "漏译")
        def reorder(x): x["paragraphs"][0], x["paragraphs"][1] = x["paragraphs"][1], x["paragraphs"][0]
        alignment_mutant("段落换位必命中", reorder, "顺序")
        def duplicate(x): x["paragraphs"].append(copy.deepcopy(x["paragraphs"][0]))
        alignment_mutant("重复段落必命中", duplicate, "重复")
        def wrong_version(x): x["corpus_sha256"] = "0" * 64
        alignment_mutant("错版语料必命中", wrong_version, "错版")
        def wrong_formula(x): x["paragraphs"][5]["target"] = x["paragraphs"][5]["target"].replace("mc^{2}", "mc^{3}")
        alignment_mutant("公式破损必命中", wrong_formula, "未逐项保留")
        def wrong_number(x): x["paragraphs"][5]["target"] = x["paragraphs"][5]["target"].replace("0.5 mL", "0.6 mL")
        alignment_mutant("数字改变必命中", wrong_number, "未逐项保留")
        def wrong_unit(x): x["paragraphs"][5]["target"] = x["paragraphs"][5]["target"].replace("0.5 mL", "0.5 L")
        alignment_mutant("单位改变必命中", wrong_unit, "未逐项保留")
        def wrong_table(x):
            index = next(i for i, block in enumerate(corpus["blocks"]) if block["kind"] == "table")
            x["paragraphs"][index]["target"] = "| 指标 | 数值 |\n| --- | --- |\n| 质量 | 2.5 kg |"
        alignment_mutant("表格行列缺失必命中", wrong_table, "表格结构改变")
        def wrong_term(x): x["paragraphs"][1]["target"] = "我们在可复现基准中评估神经网络图模型。"
        alignment_mutant("术语漂移必命中", wrong_term, "术语")
        def wrong_first_form(x): x["paragraphs"][1]["target"] = "我们在可复现基准中评估 GNN。"
        alignment_mutant("首次出现未使用全称必命中", wrong_first_form, "术语")
        def wrong_author(x): x["metadata"]["authors"][0] = "Alice 改写"
        alignment_mutant("作者改写必命中", wrong_author, "元数据不保真")
        def extra_doi(x): x["paragraphs"][1]["target"] += " 10.9999/invented.123"
        alignment_mutant("凭空 DOI 必命中", extra_doi, "凭空增加")
        def empty_target(x): x["paragraphs"][1]["target"] = " "
        alignment_mutant("空译文必命中", empty_target, "target 为空")

        # result schema/audit：逐字段与原 HTML 重算。
        case_path = dump("case.json", {"case_id": "bench-local", "url": url, "illustrative_only": True})
        task_path = os.path.join(TMP, "task.md")
        with open(task_path, "w", encoding="utf-8") as handle: handle.write("# synthetic minimal bench; not an official case\n")
        artifacts = {"snapshot": snapshot, "corpus": corpus_path, "translation": translation_path, "bilingual": bilingual_path}
        result = make_result(bilingual, artifacts, case_path, task_path)
        result_path = dump("result.json", result)
        rc, info = run_auto("trace", result_path)
        add("trace 正向: 完整 DAG/轨迹/权限零误杀", rc == 0 and info.get("ok"), info)
        rc, info = run_auto("resume", result_path)
        add("resume 正向: 全完成不重复执行", rc == 0 and info.get("runnable_now") == [], info)
        rc, info = run_auto("schema", result_path)
        add("schema 正向: 版本/定位/gain/产物零误杀", rc == 0 and info.get("ok"), info)
        early = {"case_id": "bench-local", "status": "failed", "schema_version": "2.0.0", "skill_version": "3.0.0", "tool_version": "3.0.0",
                 "run_id": "bench-early-001", "generated_at": "2026-01-01T00:00:30Z", "input": copy.deepcopy(result["input"]),
                 "source": {"url": url, "fetched_at": "2026-01-01T00:00:30Z", "snapshot_path": None, "snapshot_sha256": None, "page_version": None, "root_dom_path": None},
                 "corpus_sha256": None, "full_text_sha256": None, "extraction_status": "failed", "paragraphs": [],
                 "machine_verification": {"status": "failed", "errors": ["HTTP 401"], "warnings": [], "source_blocks": 0, "aligned_blocks": 0,
                                           "missing_blocks": [], "protected_token_violations": 0, "glossary_checks": 0, "glossary_consistent_checks": 0, "semantic_fidelity": "not_checked_by_tool"},
                 "workflow": [{"id": "W1", "step": "抓取", "depends_on": [], "input": url, "output": "no snapshot", "state": "failed"}],
                 "state": {"completed_steps": [], "failed_step": "W1", "resume_point": "W1"}, "data_passing": [],
                 "failures": [{"step": "W1", "kind": "login_expired", "signal": "HTTP 401", "action": "人工认证后重跑 fetch", "state": "blocked", "retry": 0, "idempotency_key": "W1-auth-001"}],
                 "run_log": [{"step": "W1", "started_at": "2026-01-01T00:00:00Z", "ended_at": "2026-01-01T00:00:30Z", "result": "failed", "command": "fetch"}],
                 "gain": {"status": "not_measured", "reason": "早期失败无对照", "baseline": None, "skill": None}, "artifacts": [], "sources": [],
                 "unchecked": [{"item": "article_body", "reason": "未认证，未读取正文", "status": "not_checked"}], "uncertainty": [], "change_log": []}
        rc, info = run_auto("schema", dump("early-failure.json", early))
        add("schema 正向: 第一步登录失败的诚实 null 不被误杀", rc == 0 and info.get("ok"), info)
        rc, info = run_auto("audit", result_path, bilingual_path, "--snapshot", snapshot, "--meta", meta_path)
        add("audit 正向: 原 HTML 重算+逐段字段+文件哈希零误杀", rc == 0 and info.get("ok") and info.get("snapshot_recomputed"), info)

        bad = mutate(result); bad["workflow"][2]["depends_on"] = ["W9"]
        rc, info = run_auto("trace", dump("bad-dep.json", bad))
        add("trace 变异: 不存在依赖必命中", rc == 1 and any("不存在" in x for x in errors(info)), info)
        bad = mutate(result); bad["workflow"][0]["depends_on"] = ["W4"]
        rc, info = run_auto("trace", dump("bad-cycle.json", bad))
        add("trace 变异: DAG 成环必命中", rc == 1 and any("成环" in x for x in errors(info)), info)
        bad = mutate(result)
        bad["workflow"][3]["state"] = "failed"; bad["state"]["completed_steps"] = ["W1", "W2", "W3"]
        bad["state"]["failed_step"] = "W4"; bad["state"]["resume_point"] = "W4"; bad["failures"] = [failure()]
        bad["status"] = "partial"
        failed_document = bad
        failed_result = dump("failed-result.json", failed_document)
        rc, info = run_auto("resume", failed_result)
        add("resume 变异: 失败点可续且已完成不重跑", rc == 0 and info.get("runnable_now") == ["W4"], info)
        bad = mutate(result)
        bad["workflow"][2]["state"] = "failed"; bad["workflow"][3]["state"] = "pending"
        bad["state"] = {"completed_steps": ["W1", "W2"], "failed_step": "W3", "resume_point": "W3"}
        bad["failures"] = [failure("W3", "W3-bench-failure")]; bad["status"] = "partial"
        rc, info = run_auto("resume", dump("blocked-resume.json", bad))
        add("resume 变异: 下游不被失败上游错误放行", rc == 0 and info.get("runnable_now") == ["W3"] and any(x["id"] == "W4" and x["blocked_deps"] == ["W3"] for x in info.get("waiting", [])), info)
        bad = mutate(failed_document); bad["state"]["resume_point"] = None
        rc, info = run_auto("trace", dump("no-resume.json", bad))
        add("trace 变异: 失败缺续跑点必命中", rc == 1 and any("resume_point" in x for x in errors(info)), info)
        bad = mutate(failed_document); bad["failures"].append(failure())
        rc, info = run_auto("trace", dump("duplicate-idem.json", bad))
        add("trace 变异: 重复幂等事件必命中", rc == 1 and any("idempotency_key" in x for x in errors(info)), info)
        bad = mutate(result); bad["data_passing"][0].pop("permission_scope")
        rc, info = run_auto("trace", dump("no-permission.json", bad))
        add("trace 变异: 跨站权限缺失必命中", rc == 1 and any("permission_scope" in x for x in errors(info)), info)

        bad = mutate(result); bad.pop("schema_version")
        rc, info = run_auto("schema", dump("no-version.json", bad))
        add("schema 变异: 版本字段缺失必命中", rc == 1 and any("schema_version" in x for x in errors(info)), info)
        bad = mutate(result); bad["paragraphs"][0]["quote"] = "invented quote"
        rc, info = run_auto("schema", dump("bad-quote-hash.json", bad))
        add("schema 变异: quote/hash 不符必命中", rc == 1 and any("quote" in x for x in errors(info)), info)
        bad = mutate(result); bad["paragraphs"][0]["quote"] = None
        rc, info = run_auto("schema", dump("null-quote-type.json", bad))
        add("schema 变异: 引文类型错误结构化返回而非崩溃", rc == 1 and info.get("failure_kind") == "field_type_error" and any("类型" in x for x in errors(info)), info)
        bad = mutate(result); bad["gain"] = {"status": "measured", "same_input": False}
        rc, info = run_auto("schema", dump("fake-gain.json", bad))
        add("schema 变异: 非同输入伪增益必命中", rc == 1 and any("gain" in x or "同输入" in x for x in errors(info)), info)
        bad = mutate(result); bad["paragraphs"][1]["target"] = "凭产物接口改写译文"
        bad_path = dump("audit-bad-target.json", bad)
        rc, info = run_auto("audit", bad_path, bilingual_path, "--snapshot", snapshot, "--meta", meta_path)
        add("audit 变异: 交付译文与已校验双语不符必命中", rc == 1 and any("target" in x for x in errors(info)), info)
        changed_snapshot = write_bytes("changed-after-result.html", raw.replace("molecular symmetry", "changed source").encode())
        changed_meta = mutate(meta_base); changed_meta["sha256"] = digest(changed_snapshot)
        changed_meta_path = dump("changed-after-result-meta.json", changed_meta)
        rc, info = run_auto("audit", result_path, bilingual_path, "--snapshot", changed_snapshot, "--meta", changed_meta_path)
        add("audit 变异: 原始页面改变后重算哈希必命中", rc == 1 and any("重算" in x for x in errors(info)), info)
        artifact_bad = mutate(result)
        artifact_bad["artifacts"][0]["sha256"] = "0" * 64
        rc, info = run_auto("audit", dump("bad-artifact-hash.json", artifact_bad), bilingual_path)
        add("audit 变异: 产物文件哈希伪造必命中", rc == 1 and any("sha256" in x for x in errors(info)), info)

        # compare：只接受同输入同权限两份可追溯运行证据。
        baseline, skill_run = run_compare_case(result, result_path)
        bp, sp = dump("baseline-run.json", baseline), dump("skill-run.json", skill_run)
        gain_path = os.path.join(TMP, "gain.json")
        rc, info = run_auto("compare", bp, sp, "--out", gain_path)
        gain = load(gain_path) if os.path.exists(gain_path) else {}
        add("compare 正向: 同输入同权限质量/效率算术零误杀", rc == 0 and gain.get("delta", {}).get("quality", {}).get("translation_coverage") == 4/9 and gain.get("delta", {}).get("efficiency", {}).get("manual_actions_saved") == 10, info)
        add("compare 正向: 证据文件哈希与不冒充官方榜单", bool(gain.get("comparison_hash")) and gain.get("official_platform_comparison") is False and len(gain.get("evidence", [])) == 2, info)
        bad = mutate(skill_run); bad["permissions"] = ["http:read", "filesystem:write", "login:session"]
        rc, info = run_auto("compare", bp, dump("different-permission-run.json", bad), "--out", os.path.join(TMP, "bad-gain.json"))
        add("compare 变异: 权限不同拒绝比较", rc == 1 and any("permissions" in x for x in errors(info)), info)
        bad = mutate(skill_run); bad["source_sha256"] = "f" * 64
        rc, info = run_auto("compare", bp, dump("different-source-run.json", bad), "--out", os.path.join(TMP, "bad-gain2.json"))
        add("compare 变异: 页面版本不同拒绝比较", rc == 1 and any("source_sha256" in x for x in errors(info)), info)
        bad = mutate(skill_run); bad["totals"]["translated_body_blocks"] = 100
        rc, info = run_auto("compare", bp, dump("impossible-count-run.json", bad), "--out", os.path.join(TMP, "bad-gain3.json"))
        add("compare 变异: 不可能计数拒绝比较", rc == 1 and any("不得大于" in x for x in errors(info)), info)
        bad = mutate(skill_run); bad["totals"]["manual_actions"] = True
        rc, info = run_auto("compare", bp, dump("boolean-count-run.json", bad), "--out", os.path.join(TMP, "bad-gain4.json"))
        add("compare 变异: 布尔计数不能伪装整数", rc == 1 and any("布尔" in x for x in errors(info)), info)
    finally:
        server.shutdown()
        server.server_close()
    passed = sum(1 for _, ok, _ in CHECKS if ok)
    for name, ok, detail in CHECKS:
        print(("PASS" if ok else "FAIL"), name, ("| " + detail if not ok else ""))
    print("total %d/%d" % (passed, len(CHECKS)))
    if args.report:
        report = {"bench_version": "3.0.0", "passed": passed, "total": len(CHECKS), "all_green": passed == len(CHECKS),
                  "checks": [{"name": name, "pass": ok, "detail_on_failure": detail if not ok else ""} for name, ok, detail in CHECKS]}
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
