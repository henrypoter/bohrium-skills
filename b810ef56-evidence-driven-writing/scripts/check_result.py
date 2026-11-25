#!/usr/bin/env python3
"""对照 case.json 的 output_contract 校验 result.json（仅标准库）。

用法: check_result.py <case.json> <result.json>
规则:
  R1 result.json 必须是合法 JSON 对象
  R2 必须含 case.json 中 output_contract 声明的全部字段（dict 取其 key；
     list 取其元素，元素为 dict 时取 name/field/key）
  R3 必须额外含 case_id, status, sources, uncertainty, change_records,
     artifact_version, input_manifest, verification
     （change_records 允许为空列表，其余字段不得为空；无内容须显式说明原因）
  R4 case_id 须与 case.json 一致；status ∈ {complete, partial, failed}
  R5-R7 输入 SHA-256/bytes（可读文件重算）、双核验状态与规则版本
退出码: 0=通过, 1=未通过, 2=用法错误。
"""
import hashlib
import json
import os
import re
import sys

BASE_FIELDS = ["case_id", "status", "sources", "uncertainty", "change_records",
               "artifact_version", "input_manifest", "verification"]
ALLOW_EMPTY = {"change_records"}
STATUS_OK = {"complete", "partial", "failed"}


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def contract_fields(case):
    oc = case.get("output_contract", {})
    if isinstance(oc, dict):
        return list(oc.keys())
    out = []
    for it in oc if isinstance(oc, list) else []:
        if isinstance(it, str):
            out.append(it)
        elif isinstance(it, dict):
            for k in ("name", "field", "key"):
                if k in it:
                    out.append(it[k])
                    break
    return out


def resolve_input(path, result_path, case_path):
    candidates = [path] if os.path.isabs(path) else [
        os.path.join(os.getcwd(), path),
        os.path.join(os.path.dirname(os.path.abspath(result_path)), path),
        os.path.join(os.path.dirname(os.path.abspath(case_path)), path),
    ]
    return next((p for p in candidates if os.path.isfile(p)), None)


def check_provenance(res, result_path, case_path):
    """R5-R7：版本、输入摘要和双核验状态可被独立复核。"""
    problems = []
    manifest = res.get("input_manifest")
    if not isinstance(manifest, dict) or manifest.get("algorithm") != "sha256":
        problems.append("R5 input_manifest.algorithm 须为 sha256")
        files = []
    else:
        files = manifest.get("files", [])
    if not isinstance(files, list) or not files:
        problems.append("R5 input_manifest.files 为空")
        files = []
    for i, item in enumerate(files):
        if not isinstance(item, dict):
            problems.append("R5 input_manifest.files[%d] 非对象" % i)
            continue
        path, digest = item.get("path"), item.get("sha256")
        if not path or not re.fullmatch(r"[0-9a-f]{64}", str(digest or "")):
            problems.append("R5 input_manifest.files[%d] 缺 path/64位sha256" % i)
            continue
        if not isinstance(item.get("bytes"), int) or item.get("bytes") < 0:
            problems.append("R5 input_manifest.files[%d] bytes 非法" % i)
        real = resolve_input(path, result_path, case_path)
        if real:
            h = hashlib.sha256()
            with open(real, "rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(block)
            if h.hexdigest() != digest:
                problems.append("R5 输入摘要与现文件不符: " + str(path))
    verification = res.get("verification")
    if not isinstance(verification, dict):
        problems.append("R6 verification 须为对象")
        verification = {}
    for command in ("evidence_lib", "strength_audit"):
        item = verification.get(command)
        if not isinstance(item, dict) or item.get("status") not in {"pass", "failed", "skipped"}:
            problems.append("R6 verification.%s 缺合法 status" % command)
        elif res.get("status") == "complete" and item.get("status") != "pass":
            problems.append("R6 complete 时 %s 必须 pass" % command)
        elif item.get("status") != "pass" and not str(item.get("note") or "").strip():
            problems.append("R6 %s 非 pass 须写 note" % command)
    if verification.get("rule_version") != "evidence-audit-1.0.0":
        problems.append("R7 verification.rule_version 须为 evidence-audit-1.0.0")
    return problems


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    case, res = load(argv[1]), load(argv[2])
    problems = []
    if not isinstance(res, dict):
        print("R1 FAIL: result.json 不是 JSON 对象")
        return 1
    need = contract_fields(case) + BASE_FIELDS
    for f in need:
        if f not in res:
            problems.append(f"R2/R3 缺字段: '{f}'")
        elif res[f] in (None, "", []) and f not in ALLOW_EMPTY:
            problems.append(f"字段 '{f}' 为空（若无内容须显式说明原因）")
    cid = case.get("case_id") or case.get("id")
    if cid and res.get("case_id") != cid:
        problems.append(f"R4 case_id 不一致: case={cid} result={res.get('case_id')}")
    if res.get("status") not in STATUS_OK:
        problems.append(f"R4 status 非法: {res.get('status')}")
    problems.extend(check_provenance(res, argv[2], argv[1]))
    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print(f"PASS: {len(need)} 个必需字段齐备且非空, case_id/status 合法")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
