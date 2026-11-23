#!/usr/bin/env python3
"""对照 case.json 的 output_contract 校验 result.json（仅标准库）。

用法: check_result.py <case.json> <result.json>
规则:
  R1 result.json 必须是合法 JSON 对象
  R2 必须含 case.json 中 output_contract 声明的全部字段（dict 取其 key；
     list 取其元素，元素为 dict 时取 name/field/key）
  R3 必须额外含 case_id, status, sources, uncertainty, change_records
     （change_records 允许为空列表，其余字段不得为空；无内容须显式说明原因）
  R4 case_id 须与 case.json 一致；status ∈ {complete, partial, failed}
退出码: 0=通过, 1=未通过, 2=用法错误。
"""
import json, sys

BASE_FIELDS = ["case_id", "status", "sources", "uncertainty", "change_records"]
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
    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print(f"PASS: {len(need)} 个必需字段齐备且非空, case_id/status 合法")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
