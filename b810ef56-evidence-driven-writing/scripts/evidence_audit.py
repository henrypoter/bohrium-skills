#!/usr/bin/env python3
"""证据强度、仅摘要与冲突证据独立审计（仅 Python 标准库）。

用法:
  evidence_audit.py audit <evidence_library.json> <claim_matrix.json> [manuscript.md] [-o report.json]
  evidence_audit.py fingerprint <file> [file ...]

等级口径: A=多篇独立证据/高质量一致综述; B=单篇设计良好原始研究;
C=小样本/初步/仅摘要/预印本; D=推测或不足。等级理由和不确定字段必填，
不知道填 null 并在 strength_basis.basis_unknown 列出，禁止编造。
退出码: audit 0=无 error, 1=有 error, 2=用法/IO/JSON 错误。
"""
import hashlib
import json
import os
import re
import sys

LEVELS = {"A", "B", "C", "D"}
RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
AVAILABILITY = {"full_text", "abstract_only"}
POSITIONS = {"support", "oppose", "mixed", "context"}
BASIS_FIELDS = ("design", "sample_size", "replication", "consensus")
CONFLICT_WORDS = ("不一致", "冲突", "相反", "尚无一致", "尚未一致", "mixed",
                  "conflict", "inconsistent", "contradict")
CONFLICT_FIELDS = ("summary", "differences", "uncertainty", "action")


def load(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("顶层必须是 JSON object: " + path)
    return obj


def entries(obj, key):
    value = obj.get(key, [])
    return value if isinstance(value, list) else []


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def claim_window(text, cid):
    """取论断编号所在句/段，避免只凭全文其他位置出现冲突词而通过。"""
    pat = re.compile(r"\[" + re.escape(cid) + r"(?::E\d+)?\]")
    for m in pat.finditer(text):
        left = max(text.rfind("\n", 0, m.start()), text.rfind("。", 0, m.start()),
                   text.rfind(".", 0, m.start())) + 1
        rights = [x for x in (text.find("\n", m.end()), text.find("。", m.end()),
                             text.find(".", m.end())) if x >= 0]
        right = min(rights) + 1 if rights else len(text)
        yield text[left:right]


def audit(lib, mat, manuscript_text=None):
    errors, warnings = [], []
    evs = entries(lib, "evidence")
    claims = entries(mat, "claims")
    by_id = {}
    for i, ev in enumerate(evs):
        if not isinstance(ev, dict):
            errors.append("S0 evidence[%d] 非对象" % i)
            continue
        eid = str(ev.get("id") or "E?")
        by_id[eid] = ev
        availability = ev.get("availability")
        if availability not in AVAILABILITY:
            errors.append("S1 %s: availability 须为 full_text/abstract_only" % eid)
        level = ev.get("evidence_level")
        if level not in LEVELS:
            errors.append("S0 %s: evidence_level 非法" % eid)
        if not nonempty(ev.get("evidence_level_reason")):
            errors.append("S4 %s: 缺 evidence_level_reason（设计/样本/重复/共识如何决定等级）" % eid)
        basis = ev.get("strength_basis")
        if not isinstance(basis, dict):
            errors.append("S5 %s: 缺 strength_basis 对象" % eid)
            basis = {}
        unknown = basis.get("basis_unknown", [])
        if not isinstance(unknown, list):
            errors.append("S5 %s: basis_unknown 须为列表" % eid)
            unknown = []
        for field in BASIS_FIELDS:
            if field not in basis:
                errors.append("S5 %s: strength_basis 缺 %s" % (eid, field))
            elif basis.get(field) is None and field not in unknown:
                errors.append("S5 %s: %s=null 但未列入 basis_unknown" % (eid, field))
            elif basis.get(field) is not None and not nonempty(str(basis.get(field))):
                errors.append("S5 %s: %s 须为非空说明或 null" % (eid, field))
        if availability == "abstract_only":
            if level in ("A", "B"):
                errors.append("S2 %s: 仅摘要证据等级不得高于 C（当前 %s）" % (eid, level))
            loc = str(ev.get("locator") or "")
            caveat = str(ev.get("caveat") or "")
            if not (re.search(r"摘要|abstract", loc, re.I) and re.search(r"摘要|abstract", caveat, re.I)):
                errors.append("S3 %s: 仅摘要须在 locator 与 caveat 同时标明摘要/abstract" % eid)
        if level == "A" and ev.get("type") == "原始研究":
            replication = str(basis.get("replication") or "")
            has_replication = re.search(r"独立|多中心|重复|independent|multi.?cent|replicat", replication, re.I)
            negated = re.search(r"无|未|尚无|尚未|没有|\bno\b|\bnot\b|without", replication, re.I)
            if not has_replication or negated:
                errors.append("S8 %s: 单篇原始研究标 A 须记录独立/多中心重复，否则降 B/C" % eid)
    for cl in claims:
        if not isinstance(cl, dict):
            errors.append("S0 claim 非对象")
            continue
        cid = str(cl.get("id") or "C?")
        verdict = cl.get("verdict")
        binds = [b for b in entries(cl, "bindings") if isinstance(b, dict)]
        annotation = cl.get("strength_annotation")
        if not isinstance(annotation, dict):
            errors.append("S6 %s: 缺 strength_annotation" % cid)
            annotation = {}
        alevel = annotation.get("level")
        if alevel not in LEVELS:
            errors.append("S6 %s: strength_annotation.level 非法" % cid)
        if not nonempty(annotation.get("rationale")):
            errors.append("S6 %s: strength_annotation.rationale 为空" % cid)
        if not nonempty(annotation.get("uncertainty")):
            errors.append("S6 %s: strength_annotation.uncertainty 须显式说明（无剩余不确定也须写原因）" % cid)
        bound_evs = [by_id.get(str(b.get("evidence_id"))) for b in binds]
        bound_evs = [e for e in bound_evs if e]
        if bound_evs and alevel in RANK:
            best = min((RANK.get(e.get("evidence_level"), 3) for e in bound_evs), default=3)
            if RANK[alevel] < best:
                errors.append("S7 %s: 论断强度 %s 高于绑定证据上限 %s" %
                              (cid, alevel, min(bound_evs, key=lambda e: RANK.get(e.get("evidence_level"), 3)).get("evidence_level")))
        if any(e.get("availability") == "abstract_only" for e in bound_evs) and alevel in ("A", "B"):
            errors.append("S7 %s: 绑定含仅摘要证据，论断强度封顶 C；无关证据应解绑" % cid)
        positions = []
        for b in binds:
            position = b.get("position")
            if position not in POSITIONS:
                errors.append("C1 %s/%s: binding.position 须为 support/oppose/mixed/context" %
                              (cid, b.get("evidence_id")))
            else:
                positions.append(position)
        if verdict == "conflicted":
            if not (("support" in positions and ("oppose" in positions or "mixed" in positions)) or
                    positions.count("mixed") >= 2):
                errors.append("C2 %s: conflicted 必须显式包含正向与反向/mixed 证据位置" % cid)
            analysis = cl.get("conflict_analysis")
            if not isinstance(analysis, dict):
                errors.append("C3 %s: 缺 conflict_analysis" % cid)
                analysis = {}
            for field in CONFLICT_FIELDS:
                if not nonempty(analysis.get(field)):
                    errors.append("C3 %s: conflict_analysis.%s 为空" % (cid, field))
            if alevel in ("A", "B"):
                errors.append("S7 %s: 冲突证据未解决时论断强度封顶 C" % cid)
            if manuscript_text is not None:
                windows = list(claim_window(manuscript_text, cid))
                if not windows:
                    errors.append("C5 %s: manuscript 未引用冲突论断编号" % cid)
                elif not any(any(w.lower() in win.lower() for w in CONFLICT_WORDS) for win in windows):
                    errors.append("C5 %s: 冲突论断所在句未并陈不一致/相反/conflicted" % cid)
        elif "oppose" in positions or "mixed" in positions:
            errors.append("C4 %s: 存在 oppose/mixed 证据却未判 conflicted（不得隐藏冲突）" % cid)
    if not evs:
        warnings.append("证据库为空：只能输出 unsupported/partial，不得形成有来源的成稿")
    return {"ok": not errors,
            "summary": {"evidence": len(evs), "claims": len(claims),
                        "errors": len(errors), "warnings": len(warnings)},
            "errors": errors, "warnings": warnings,
            "rule_version": "evidence-audit-1.0.0"}


def cmd_audit(args):
    paths = [a for a in args if a != "-o" and not a.startswith("--")]
    out = None
    if "-o" in args:
        j = args.index("-o")
        if j + 1 >= len(args):
            raise ValueError("-o 缺输出路径")
        out = args[j + 1]
        paths = [a for i, a in enumerate(args) if a != "-o" and i != j + 1]
    if len(paths) not in (2, 3):
        raise ValueError("audit 需要 lib、matrix，可选 manuscript")
    lib, mat = load(paths[0]), load(paths[1])
    text = None
    if len(paths) == 3:
        with open(paths[2], encoding="utf-8", errors="replace") as f:
            text = f.read()
    report = audit(lib, mat, text)
    if out is None:
        out = os.path.join(os.path.dirname(os.path.abspath(paths[1])), "strength_audit.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("[evidence_audit] 报告已写 " + out)
    return 0 if report["ok"] else 1


def cmd_fingerprint(paths):
    if not paths:
        raise ValueError("fingerprint 至少需要一个文件")
    files = []
    for path in paths:
        h = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                h.update(block)
        files.append({"path": path, "sha256": h.hexdigest(), "bytes": size})
    print(json.dumps({"algorithm": "sha256", "files": files}, ensure_ascii=False, indent=2))
    return 0


def main(argv):
    try:
        if len(argv) >= 3 and argv[1] == "audit":
            return cmd_audit(argv[2:])
        if len(argv) >= 3 and argv[1] == "fingerprint":
            return cmd_fingerprint(argv[2:])
        print(__doc__)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": ["IO/JSON: " + str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
