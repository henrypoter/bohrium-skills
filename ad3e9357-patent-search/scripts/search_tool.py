#!/usr/bin/env python3
"""专利与技术文献检索机检工具（纯 Python 标准库）。

命令：
  normalize <records.json>          按号码角色规范化，不互换公开号/申请号/授权号
  family    <records.json>          简单族/扩展族分口径归并；不推定完整或权利要求等同
  status    <legal.json>            排序法律事件；无当前官方核验时保持 unknown
  gain      <comparison.json>       同输入同权限 qrels 对照，真算 P/R/nDCG 与成本差
  audit     <result.json>           哈希、逐字引文、字段绑定、计数、族/状态/授权硬审计

所有命令 stdout 均为一个 JSON 对象；数据或审计错误返回 1，用法错误返回 2。
"""
import datetime as _dt
import hashlib
import json
import math
import os
import re
import sys
import unicodedata

STATUSES = {"pass", "issues", "partial", "failed"}
DECISIONS = {"include", "exclude", "unresolved"}
ACCESS = {"green", "yellow", "red"}


def emit(obj, rc=0):
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))
    return rc


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def records_of(d):
    return d.get("records", []) if isinstance(d, dict) else d


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def norm_number(value, role="publication", country=""):
    """只改排版，不把一种号码角色解释成另一种。"""
    raw = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    compact = re.sub(r"[^A-Z0-9]", "", raw)
    if country and re.match(r"^\d", compact):
        compact = country.upper() + compact
    m = re.fullmatch(r"([A-Z]{2})([0-9]{4,14})([A-Z][0-9]?)?", compact)
    if not m:
        raise ValueError("无法规范化%s号码: %r" % (role, value))
    if role == "application" and m.group(3):
        raise ValueError("申请号不应带文献种类代码: %r" % value)
    return "".join(x or "" for x in m.groups())


def resolve_path(base, path):
    if os.path.isabs(path):
        return path
    p = os.path.normpath(os.path.join(base, path))
    return p if os.path.exists(p) else os.path.normpath(path)


def field_value(obj, path):
    """读取 message.items[0].title 这类 JSON 字段路径。"""
    if path in ("", "text", "raw") and isinstance(obj, str):
        return obj
    cur = obj
    tokens = re.findall(r"([^.\[\]]+)|\[([0-9]+)\]", str(path or ""))
    if not tokens:
        raise ValueError("空字段路径")
    for key, index in tokens:
        if key:
            if not isinstance(cur, dict) or key not in cur:
                raise KeyError(path)
            cur = cur[key]
        else:
            cur = cur[int(index)]
    return cur


def source_path(source, base):
    return resolve_path(base, source.get("path", ""))


def load_source_value(source, field, base):
    path = source_path(source, base)
    if field in ("", "text", "raw") and not path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return f.read()
    with open(path, encoding="utf-8") as f:
        if path.lower().endswith(".json"):
            obj = json.load(f)
        else:
            obj = f.read()
    return field_value(obj, field)


def source_map(d, base, errs):
    out = {}
    for i, s in enumerate(d.get("sources", [])):
        label = "sources[%d]" % i
        sid = s.get("id")
        if not sid or sid in out:
            errs.append(label + " 缺 id 或 id 重复")
            continue
        out[sid] = s
        for k in ("name", "version", "query_date", "path", "sha256"):
            if not s.get(k):
                errs.append("%s 缺 %s" % (label, k))
        if s.get("access") not in ACCESS:
            errs.append(label + " access 必须为 green/yellow/red")
        if s.get("access") == "yellow" and not s.get("allowed_fields"):
            errs.append(label + " 黄色来源必须列 allowed_fields")
        p = source_path(s, base)
        if not s.get("path") or not os.path.isfile(p):
            errs.append(label + " 原始来源文件不可读")
        elif s.get("sha256"):
            try:
                if sha256(p) != s["sha256"]:
                    errs.append(label + " sha256 与原始文件不符")
            except OSError as e:
                errs.append(label + " 哈希失败: " + str(e))
    return out


def allowed(source, field):
    pats = source.get("allowed_fields") or []
    return any(field == p or (p.endswith(".*") and field.startswith(p[:-1])) for p in pats)


def check_quote(node, label, sources, base, errs):
    sid = node.get("source_id")
    if sid not in sources:
        errs.append(label + " source_id 未登记")
        return
    s = sources[sid]
    for k in ("quote", "field", "locator"):
        if not node.get(k):
            errs.append("%s 缺 %s" % (label, k))
    if s.get("access") == "red":
        errs.append(label + " 红色受限来源不得展示引文")
        return
    if s.get("access") == "yellow" and not allowed(s, node.get("field", "")):
        errs.append(label + " 字段不在黄色来源 allowed_fields")
        return
    try:
        value = load_source_value(s, node.get("field", ""), base)
        if not isinstance(value, str):
            raise ValueError("引文字段不是字符串")
        quote = node["quote"]
        span = node.get("span")
        if span is not None:
            if (not isinstance(span, list) or len(span) != 2 or
                    not all(isinstance(x, int) and x >= 0 for x in span)):
                raise ValueError("span 必须为 [start,end]")
            if value[span[0]:span[1]] != quote:
                raise ValueError("span 未逐字指向引文")
        elif value.count(quote) != 1:
            raise ValueError("引文不是字段内唯一逐字子串；重复时须给 span")
    except Exception as e:
        errs.append(label + " 逐字回源失败: " + str(e))


def walk_evidence(x, path, sources, base, errs):
    n = 0
    if isinstance(x, dict):
        if "quote" in x:
            check_quote(x, path, sources, base, errs)
            n += 1
        for k, v in x.items():
            if k != "sources":
                n += walk_evidence(v, path + "." + k, sources, base, errs)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            n += walk_evidence(v, "%s[%d]" % (path, i), sources, base, errs)
    return n


def cmd_normalize(path):
    try:
        recs = records_of(load(path))
        out, errs = [], []
        for i, r in enumerate(recs):
            item = {"id": r.get("id"), "normalized": {}}
            for role, key in (("publication", "publication_number"),
                              ("application", "application_number"),
                              ("grant", "grant_number")):
                if r.get(key):
                    try:
                        item["normalized"][key] = norm_number(r[key], role, r.get("country", ""))
                    except ValueError as e:
                        errs.append("records[%d]: %s" % (i, e))
            priorities = []
            for p in r.get("priority_numbers", []):
                try:
                    priorities.append(norm_number(p, "priority", r.get("country", "")))
                except ValueError as e:
                    errs.append("records[%d]: %s" % (i, e))
            item["normalized"]["priority_numbers"] = sorted(set(priorities))
            item["roles_preserved"] = True
            out.append(item)
        return emit({"ok": not errs, "records": out, "errors": errs}, 1 if errs else 0)
    except Exception as e:
        return emit({"ok": False, "errors": [str(e)]}, 1)


class DSU:
    def __init__(self, ids):
        self.p = {x: x for x in ids}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.p[b] = a


def family_calc(recs):
    ids = [r.get("id") for r in recs]
    if len(ids) != len(set(ids)) or any(not x for x in ids):
        raise ValueError("记录 id 缺失或重复")
    normalized, errors = {}, []
    for r in recs:
        ps = []
        for p in r.get("priority_numbers", []):
            try:
                ps.append(norm_number(p, "priority", r.get("country", "")))
            except ValueError as e:
                errors.append(str(e))
        normalized[r["id"]] = set(ps)
    simple_buckets = {}
    for r in recs:
        rid = r["id"]
        if r.get("simple_family_id"):
            key = "id:" + r["simple_family_id"]
        elif normalized[rid]:
            key = "priorities:" + ",".join(sorted(normalized[rid]))
        else:
            key = "singleton:" + rid
        simple_buckets.setdefault(key, []).append(rid)
    members_to_key = {m: k for k, ms in simple_buckets.items() for m in ms}
    for key, ms in simple_buckets.items():
        if key.startswith("id:"):
            signatures = {tuple(sorted(normalized[m])) for m in ms}
            if len(signatures) > 1:
                errors.append("简单族 %s 内优先权集合不一致" % key)
    dsu = DSU(ids)
    ext_buckets = {}
    for r in recs:
        if r.get("extended_family_id"):
            ext_buckets.setdefault("id:" + r["extended_family_id"], []).append(r["id"])
        for p in normalized[r["id"]]:
            ext_buckets.setdefault("priority:" + p, []).append(r["id"])
    for ms in ext_buckets.values():
        for m in ms[1:]:
            dsu.union(ms[0], m)
    ext = {}
    for rid in ids:
        ext.setdefault(dsu.find(rid), []).append(rid)
    simple = [{"basis": k, "members": sorted(v)} for k, v in simple_buckets.items()]
    extended = [{"members": sorted(v)} for v in ext.values()]
    return {
        "simple": sorted(simple, key=lambda x: x["members"]),
        "extended": sorted(extended, key=lambda x: x["members"]),
        "complete": False,
        "claim_scope_equal": False,
        "scope_note": "仅由所给优先权/族标识与观察链接归并；不是完整同族清单，不推定权利要求范围等同",
        "member_to_simple_key": members_to_key,
        "errors": errors,
    }


def cmd_family(path):
    try:
        result = family_calc(records_of(load(path)))
        result.pop("member_to_simple_key", None)
        result["ok"] = not result["errors"]
        return emit(result, 1 if result["errors"] else 0)
    except Exception as e:
        return emit({"ok": False, "errors": [str(e)]}, 1)


def valid_date(s):
    try:
        _dt.date.fromisoformat(str(s))
        return True
    except ValueError:
        return False


def status_one(case):
    events = case.get("events", [])
    errs = []
    for i, e in enumerate(events):
        if not valid_date(e.get("effective_date", "")) or not e.get("status"):
            errs.append("events[%d] 缺有效 effective_date/status" % i)
    ordered = sorted(events, key=lambda e: (e.get("effective_date", ""), e.get("source_id", "")))
    official = [e for e in ordered if e.get("official") is True]
    latest_date = max((e["effective_date"] for e in official), default=None)
    latest = [e for e in official if e.get("effective_date") == latest_date]
    conflict = len({e["status"] for e in latest}) > 1
    checked = case.get("official_register_checked") is True
    declared = case.get("declared_status")
    if not valid_date(case.get("as_of", "")):
        errs.append("as_of 必须为 YYYY-MM-DD")
    if not checked:
        verification, current = "not_checked", "unknown"
    elif conflict:
        verification, current = "conflict", "unknown"
    elif declared and official:
        verification, current = "official_current", declared
    elif official:
        verification, current = "official_events_only", "unknown"
    else:
        verification, current = "secondary_only", "unknown"
    return {"id": case.get("id"), "as_of": case.get("as_of"), "events": ordered,
            "latest_official_event_date": latest_date, "verification": verification,
            "current_status": current, "event_conflict": conflict, "errors": errs,
            "note": "法律事件不自动等同当前法律状态；当前结论需官方登记核验与明确 declared_status"}


def cmd_status(path):
    try:
        d = load(path)
        cases = d.get("cases", []) if isinstance(d, dict) and "cases" in d else [d]
        out = [status_one(c) for c in cases]
        errs = [e for c in out for e in c["errors"]]
        return emit({"ok": not errs, "cases": out, "errors": errs}, 1 if errs else 0)
    except Exception as e:
        return emit({"ok": False, "errors": [str(e)]}, 1)


def ranking_metrics(ranking, qrels, k):
    if len(ranking) != len(set(ranking)):
        raise ValueError("ranking 含重复 id")
    unknown = set(ranking) - set(qrels)
    if unknown:
        raise ValueError("ranking 含 qrels 外 id: " + ",".join(sorted(unknown)))
    top = ranking[:k]
    hits = sum(1 for r in top if qrels.get(r, 0) > 0)
    total_rel = sum(1 for v in qrels.values() if v > 0)
    dcg = sum((2 ** qrels[r] - 1) / math.log2(i + 2) for i, r in enumerate(top))
    ideal = sorted((float(v) for v in qrels.values()), reverse=True)[:k]
    idcg = sum((2 ** v - 1) / math.log2(i + 2) for i, v in enumerate(ideal))
    return {"precision_at_k": hits / k, "recall_at_k": hits / total_rel if total_rel else None,
            "ndcg_at_k": dcg / idcg if idcg else None, "hits_at_k": hits}


def cmd_gain(path):
    try:
        d = load(path)
        if d.get("same_input") is not True or d.get("same_permissions") is not True:
            raise ValueError("公平对照必须 same_input=true 且 same_permissions=true")
        k = int(d.get("k", 0))
        if k <= 0:
            raise ValueError("k 必须为正整数")
        qrels = {str(a): float(b) for a, b in (d.get("qrels") or {}).items()}
        if not qrels or any(v < 0 for v in qrels.values()):
            raise ValueError("qrels 必须为非空非负相关等级")
        out = {"ok": True, "mode": "local_qrels", "case_id": d.get("case_id"),
               "same_input": True, "same_permissions": True, "k": k, "metrics": {}}
        for arm in ("baseline", "skill"):
            arm_d = d.get(arm) or {}
            m = ranking_metrics(arm_d.get("ranking", []), qrels, k)
            m["cost"] = arm_d.get("cost", {})
            out["metrics"][arm] = m
        out["metrics"]["delta"] = {
            key: out["metrics"]["skill"][key] - out["metrics"]["baseline"][key]
            for key in ("precision_at_k", "recall_at_k", "ndcg_at_k")
            if out["metrics"]["skill"][key] is not None and out["metrics"]["baseline"][key] is not None
        }
        bc, sc = (d["baseline"].get("cost", {}), d["skill"].get("cost", {}))
        out["metrics"]["cost_saved"] = {key: bc[key] - sc[key] for key in bc
                                        if key in sc and isinstance(bc[key], (int, float))
                                        and isinstance(sc[key], (int, float))}
        return emit(out)
    except Exception as e:
        return emit({"ok": False, "errors": [str(e)]}, 1)


def compare_bound(expected, actual, field):
    if field.endswith("number"):
        try:
            return norm_number(expected, "priority") == norm_number(actual, "priority")
        except ValueError:
            return False
    if isinstance(expected, (int, float)) or isinstance(actual, (int, float)):
        return str(expected) == str(actual)
    return expected == actual


def check_bindings(record, label, sources, base, errs):
    bindings = record.get("field_bindings") or {}
    for field, b in bindings.items():
        if field not in record:
            errs.append("%s 绑定了不存在的字段 %s" % (label, field))
            continue
        if not isinstance(b, dict) or b.get("source_id") not in sources or not b.get("field"):
            errs.append("%s.%s 字段绑定无效" % (label, field))
            continue
        s = sources[b["source_id"]]
        if s.get("access") == "red":
            errs.append("%s.%s 不得读取红色来源" % (label, field))
            continue
        try:
            actual = load_source_value(s, b["field"], base)
            if not compare_bound(record[field], actual, field):
                errs.append("%s.%s 与原始字段不符: expected=%r actual=%r" %
                            (label, field, record[field], actual))
        except Exception as e:
            errs.append("%s.%s 回源失败: %s" % (label, field, e))


def audit_gain(g, errs):
    if not isinstance(g, dict) or g.get("mode") not in {"not_measured", "local_qrels", "platform_observed"}:
        errs.append("gain.mode 必须为 not_measured/local_qrels/platform_observed")
        return
    if g["mode"] == "not_measured":
        if not g.get("reason"):
            errs.append("gain 未测量时必须给 reason")
    elif g["mode"] == "local_qrels":
        if g.get("same_input") is not True or g.get("same_permissions") is not True:
            errs.append("gain 本地对照缺同输入/同权限声明")
        if not g.get("metrics") or not g.get("qrels_ref"):
            errs.append("gain 本地对照缺 metrics/qrels_ref")
    elif not g.get("platform_run_id"):
        errs.append("gain 平台观察值缺 platform_run_id；不得自造")


def cmd_audit(path):
    errs = []
    try:
        d = load(path)
        base = os.path.dirname(os.path.abspath(path))
        required = ("case_id", "status", "research_scope", "queries", "records",
                    "technical_literature", "families", "legal_status", "claims", "counts",
                    "coverage", "sources", "uncertainty", "change_log", "gain")
        for k in required:
            if k not in d:
                errs.append("缺顶层字段 " + k)
        if d.get("status") not in STATUSES:
            errs.append("status 非法")
        sources = source_map(d, base, errs)
        qids = set()
        for i, q in enumerate(d.get("queries", [])):
            for k in ("id", "query", "database", "run_date", "source_id", "authorization"):
                if not q.get(k):
                    errs.append("queries[%d] 缺 %s" % (i, k))
            if q.get("id") in qids:
                errs.append("queries[%d] id 重复" % i)
            qids.add(q.get("id"))
            if q.get("source_id") not in sources:
                errs.append("queries[%d] 未绑定原始响应 source_id" % i)
        ids = set()
        for i, r in enumerate(d.get("records", [])):
            label = "records[%d]" % i
            for k in ("id", "publication_number", "decision", "relevance_reason", "evidence", "field_bindings"):
                if k not in r or (k in ("publication_number", "relevance_reason") and not r.get(k)):
                    errs.append(label + " 缺 " + k)
            if r.get("id") in ids:
                errs.append(label + " id 重复")
            ids.add(r.get("id"))
            if r.get("decision") not in DECISIONS:
                errs.append(label + " decision 非法")
            if not r.get("evidence"):
                errs.append(label + " 至少一条相关性逐字证据")
            if "publication_number" not in (r.get("field_bindings") or {}):
                errs.append(label + " publication_number 必须绑定原字段")
            check_bindings(r, label, sources, base, errs)
        for i, r in enumerate(d.get("technical_literature", [])):
            if not r.get("id") or not r.get("title") or not r.get("evidence"):
                errs.append("technical_literature[%d] 缺 id/title/evidence" % i)
        c = d.get("counts") or {}
        try:
            raw, ded = int(c["raw"]), int(c["deduplicated"])
            if raw < ded or ded != len(d.get("records", [])):
                errs.append("计数不闭合：要求 raw>=deduplicated=len(records)")
            total = sum(int(c.get(x, 0)) for x in DECISIONS)
            if total != ded:
                errs.append("include/exclude/unresolved 合计不等于去重后记录数")
        except Exception:
            errs.append("counts 缺 raw/deduplicated 或含非整数")
        fam = d.get("families") or {}
        if fam.get("complete") is not False or fam.get("claim_scope_equal") is not False:
            errs.append("观察链接不得声明完整同族或权利要求范围等同")
        for key in ("simple", "extended"):
            if key not in fam:
                errs.append("families 缺 %s 口径" % key)
        try:
            calculated = family_calc(d.get("records", []))
            errs.extend("族计算: " + e for e in calculated["errors"])
            for key in ("simple", "extended"):
                actual_groups = sorted(sorted(g.get("members", [])) for g in fam.get(key, []))
                expected_groups = sorted(sorted(g["members"]) for g in calculated[key])
                if actual_groups != expected_groups:
                    errs.append("families.%s 与优先权/族标识重算不一致" % key)
        except Exception as e:
            errs.append("族重算失败: " + str(e))
        for i, st in enumerate(d.get("legal_status", [])):
            if st.get("verification") not in {"official_current", "official_stale", "official_events_only",
                                               "secondary_only", "not_checked", "conflict"}:
                errs.append("legal_status[%d] verification 非法" % i)
            if not valid_date(st.get("as_of", "")):
                errs.append("legal_status[%d] 缺有效 as_of" % i)
            if st.get("current_status", "unknown") != "unknown" and st.get("verification") != "official_current":
                errs.append("legal_status[%d] 非当前官方核验不得给确定当前状态" % i)
            if st.get("verification") == "conflict" and st.get("current_status") != "unknown":
                errs.append("legal_status[%d] 冲突时 current_status 必须 unknown" % i)
        for i, cl in enumerate(d.get("claims", [])):
            if not cl.get("evidence") or not cl.get("version") or not cl.get("locator_scope"):
                errs.append("claims[%d] 缺版本/定位范围/逐字证据" % i)
            if cl.get("scope_comparison") in {"equal", "equivalent", "same_scope"}:
                errs.append("claims[%d] 不得仅据文本/同族推定权利要求范围等同" % i)
        if (d.get("coverage") or {}).get("global_novelty") is True:
            errs.append("有限快照不得声明 global_novelty=true")
        audit_gain(d.get("gain"), errs)
        evidence_n = walk_evidence(d, "result", sources, base, errs)
        if d.get("status") == "pass" and int(c.get("unresolved", 0) or 0) > 0:
            errs.append("有 unresolved 时不得 status=pass")
        return emit({"ok": not errs, "case_id": d.get("case_id"), "evidence_quotes_checked": evidence_n,
                     "records": len(d.get("records", [])), "errors": errs}, 1 if errs else 0)
    except Exception as e:
        errs.append("审计异常: " + str(e))
        return emit({"ok": False, "errors": errs}, 1)


CMDS = {"normalize": cmd_normalize, "family": cmd_family, "status": cmd_status,
        "gain": cmd_gain, "audit": cmd_audit}


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in CMDS:
        print(__doc__)
        return 2
    return CMDS[sys.argv[1]](sys.argv[2])


if __name__ == "__main__":
    sys.exit(main())
