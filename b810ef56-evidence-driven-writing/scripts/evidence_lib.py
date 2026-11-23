#!/usr/bin/env python3
"""证据库 + 论断-证据绑定矩阵核验（仅标准库）。

用法: evidence_lib.py skeleton <out_dir>
      evidence_lib.py check <lib.json> <matrix.json> [src_txt_dir] [manuscript.md]
规则: E1 字段/年份/DOI；E2 绑定存在且含 scope+note；E3 supported≥1 & unsupported 无 full；
E4 conflicted≥2；E5 quote 原文锚定；E6 level/verdict 合法；E7 full 数值须见于 quote；
E8 full 内容词覆盖软检；E9 强度词-等级对齐（取绑定证据的最强等级）；E10 supported 须 full；
E11 partial 口径；E12 证据/论断编号唯一；M1 正文↔matrix（支持 [C#] 与 [C#:E#] 引用式）。
退出码: 0=无 error, 1=有 error, 2=用法错误。报告写 stdout 与 <matrix目录>/verification_report.json。
"""
import json, os, re, sys

EV_FIELDS = ["id", "authors", "year", "title", "venue", "type",
             "locator", "quote", "supports", "evidence_level"]
CL_FIELDS = ["id", "text", "bindings", "verdict"]
LEVELS = {"A", "B", "C", "D"}
VERDICTS = {"supported", "partially_supported", "unsupported", "conflicted"}
SCOPES = {"full", "partial"}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
YEAR_RE = re.compile(r"^(19|20)\d{2}$")
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
LATIN_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,}")
CLAIM_ID_RE = re.compile(r"\[C(\d+)(?::E\d+)?\]")
NEG = {"未", "无", "不", "尚", "法", "非", "没"}
HARD_CLAIM = ["证明", "证实", "首次", "共识", "领域共识", "导致", "确立",
              "广泛接受", "普遍认为", "公认", "已成为"]
SOFT_CLAIM = ["显著", "明确", "优于", "远超", "稳健地", "稳定地"]
STOPWORDS = {"the", "a", "an", "and", "or", "of", "to", "in", "for", "on",
             "with", "that", "this", "these", "those", "is", "are", "was",
             "were", "be", "been", "by", "as", "at", "from", "its", "their",
             "we", "they", "it", "has", "have", "had", "which", "who",
             "but", "not", "no", "also", "can", "may", "could", "should"}


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip().lower()


def claim_numbers(s):
    """论断中的数值 token（4 位年份归元数据，不做锚定）。"""
    out = []
    for m in NUM_RE.finditer(s or ""):
        core = m.group(0).rstrip("%")
        if re.fullmatch(r"(19|20)\d{2}", core):
            continue
        out.append(core)
    return out


def content_terms(s):
    """内容词集合：英文小写 token + 中文 2-gram，供覆盖度软检查。"""
    s = (s or "").lower()
    terms = set()
    for w in LATIN_RE.findall(s):
        if w not in STOPWORDS:
            terms.add(w)
    for run in CJK_RE.findall(s):
        if len(run) == 1:
            terms.add(run)
        else:
            for i in range(len(run) - 1):
                terms.add(run[i:i + 2])
    return terms


def hit_words(text, words):
    """返回命中的强度词（跳过否定前缀，如 无法证明/无显著/尚未证实）。"""
    hits = []
    for w in words:
        i = text.find(w)
        while i != -1:
            if i == 0 or text[i - 1] not in NEG:
                hits.append(w)
                break
            i = text.find(w, i + 1)
    return hits


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build_corpus(d):
    if not d or not os.path.isdir(d):
        return None
    parts = []
    for fn in sorted(os.listdir(d)):
        if fn.lower().endswith((".txt", ".md")):
            with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as f:
                parts.append(f.read())
    return norm(" ".join(parts)) if parts else None


def cmd_check(lib_path, mat_path, src_dir=None, manuscript=None):
    errors, warnings, notes = [], [], []
    lib, mat = load(lib_path), load(mat_path)
    evs = lib.get("evidence", lib if isinstance(lib, list) else [])
    claims = mat.get("claims", mat if isinstance(mat, list) else [])
    corpus = build_corpus(src_dir)
    if corpus is None:
        notes.append("未提供材料纯文本目录：quote 锚定检查跳过（E5=unchecked）")

    ids = {}
    for ev in evs:
        eid = ev.get("id", "<无id>")
        if eid in ids:
            errors.append(f"E12 证据 id 重复: {eid}（编号冲突，须唯一）")
        ids[eid] = ev
        for f in EV_FIELDS:
            if f not in ev:
                errors.append(f"E1 证据 {eid}: 缺字段 '{f}'")
        y = str(ev.get("year") or "")
        if y and y != "null" and not YEAR_RE.match(y):
            errors.append(f"E1 证据 {eid}: year '{y}' 非 4 位年份")
        doi = ev.get("doi")
        if doi and not DOI_RE.match(str(doi)):
            errors.append(f"E1 证据 {eid}: doi '{doi}' 格式非法")
        if not doi:
            warnings.append(f"证据 {eid}: 无 doi（若材料缺失请核实）")
        lv = ev.get("evidence_level")
        if lv not in LEVELS:
            errors.append(f"E6 证据 {eid}: evidence_level '{lv}' 非法")
        if corpus is not None:
            q = norm(ev.get("quote", ""))
            if not q:
                errors.append(f"E5 证据 {eid}: quote 为空")
            elif q not in corpus:
                errors.append(f"E5 证据 {eid}: quote 未在原文找到（疑似编造）: {q[:60]}...")

    n_sup = 0
    claim_ids = set()
    for cl in claims:
        cid = cl.get("id", "<无id>")
        if cid in claim_ids:
            errors.append(f"E12 论断 id 重复: {cid}（编号冲突，须唯一）")
        claim_ids.add(cid)
        text = cl.get("text", "")
        for f in CL_FIELDS:
            if f not in cl:
                errors.append(f"E2 {cid}: 缺字段 '{f}'")
        v = cl.get("verdict")
        if v not in VERDICTS:
            errors.append(f"E6 {cid}: verdict '{v}' 非法")
        binds = cl.get("bindings") or []
        nums = claim_numbers(text)
        full_binds, seen = [], set()
        for b in binds:
            if not isinstance(b, dict):
                errors.append(f"E2 {cid}: binding 非对象")
                continue
            eid = b.get("evidence_id")
            if eid not in ids:
                errors.append(f"E2 {cid}: evidence_id '{eid}' 不存在")
                continue
            if eid in seen:
                warnings.append(f"{cid}: 重复绑定 {eid}")
            seen.add(eid)
            scope = b.get("scope")
            if scope not in SCOPES:
                errors.append(f"E2 {cid}: {eid} scope '{scope}' 非法")
            if not (b.get("note") or "").strip():
                errors.append(f"E2 {cid}: {eid} 缺 note（判定理由）")
            if scope == "full":
                full_binds.append((eid, b))
        if v == "supported":
            if not binds:
                errors.append(f"E3 {cid}: supported 无绑定")
            elif not full_binds:
                errors.append(f"E10 {cid}: supported 无 full 绑定")
            else:
                n_sup += 1
        if v == "unsupported" and any(b.get("scope") == "full" for b in binds if isinstance(b, dict)):
            errors.append(f"E3 {cid}: unsupported 却有 full 绑定")
        if v == "conflicted" and len(binds) < 2:
            errors.append(f"E4 {cid}: conflicted 绑定 <2")
        if v == "partially_supported" and full_binds and not any(
                b.get("scope") == "partial" for b in binds if isinstance(b, dict)):
            warnings.append(f"E11 {cid}: 有 full 却判 partial，复核口径")
        for eid, b in full_binds:
            qn = set(claim_numbers(ids[eid].get("quote", "")))
            miss = sorted({n for n in nums if n not in qn})
            if miss:
                errors.append(f"E7 {cid}: full 绑定 {eid} quote 缺数值 {miss[:6]}（核对原文或降 partial）")
            ct = content_terms(text)
            if ct:
                qt = content_terms(ids[eid].get("quote", ""))
                cov = len(ct & qt) / len(ct)
                if cov < 0.5:
                    warnings.append(f"E8 {cid}: {eid} 内容词覆盖 {cov:.2f}<0.5，可能不支撑")
        bound_levs = [ids[b.get("evidence_id")].get("evidence_level")
                      for b in binds if isinstance(b, dict) and b.get("evidence_id") in ids]
        # 论断的强度上限由最强绑定证据决定（A 最强）：A<B<C<D，取 min。
        best_lev = min(bound_levs) if bound_levs else None
        hard = hit_words(text, HARD_CLAIM)
        soft = hit_words(text, SOFT_CLAIM)
        if hard and best_lev != "A":
            errors.append(f"E9 {cid}: 强词 {hard[:3]} 但证据等级 {best_lev or '无'} 非 A")
        if soft and best_lev in (None, "C", "D"):
            warnings.append(f"E9 {cid}: {soft[:3]} 但证据等级 {best_lev or '无'} ≤C，加限定语")
    if manuscript:
        if os.path.isfile(manuscript):
            with open(manuscript, encoding="utf-8", errors="replace") as f:
                ms = f.read()
            cited = {"C" + g for g in CLAIM_ID_RE.findall(ms)}
            for c in sorted(cited - claim_ids):
                errors.append(f"M1 manuscript 编号 {c} 不在 matrix")
            for c in sorted(claim_ids - cited):
                warnings.append(f"M1 论断 {c} 未在 manuscript 引用")
        else:
            warnings.append(f"M1 manuscript 不可读：{manuscript}")

    report = {
        "summary": {"evidence": len(evs), "claims": len(claims),
                    "supported": n_sup, "errors": len(errors),
                    "warnings": len(warnings)},
        "errors": errors, "warnings": warnings, "notes": notes,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(mat_path)), "verification_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"[evidence_lib] 报告已写 {out}")
    return 1 if errors else 0


def cmd_skeleton(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    lib = {"evidence": [{"id": "E1", "authors": None, "year": None, "title": "",
             "venue": None, "doi": None, "type": "原始研究|综述|指南|预印本",
             "locator": "章节/页/段", "quote": "逐字原文摘录",
             "supports": "该文献真正支持的表述", "data": "关键数字",
             "conditions": "适用条件/人群/体系", "limitations": "局限",
             "evidence_level": "A|B|C|D", "caveat": None}]}
    mat = {"claims": [{"id": "C1", "text": "最小可判定论断",
             "verdict": "partially_supported",
             "bindings": [{"evidence_id": "E1", "scope": "partial",
                           "note": "支撑范围说明：证据支持到哪一步"}]}]}
    for name, obj in (("evidence_library.json", lib), ("claim_matrix.json", mat)):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"[evidence_lib] 骨架已写入 {out_dir}")
    return 0


def main(argv):
    if len(argv) >= 3 and argv[1] == "skeleton":
        return cmd_skeleton(argv[2])
    if len(argv) >= 4 and argv[1] == "check":
        return cmd_check(argv[2], argv[3],
                         argv[4] if len(argv) > 4 else None,
                         argv[5] if len(argv) > 5 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
