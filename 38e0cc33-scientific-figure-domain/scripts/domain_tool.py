#!/usr/bin/env python3
"""领域总课题通用校验：result.json 完整性 + 可追溯性。纯标准库。"""
import json, sys
TOP=["case_id","status","result","evidence","artifacts","unchecked","sources","uncertainty","change_log"]
STATUS={"pass","issues","partial","failed"}
def main(path):
    try: d=json.load(open(path,encoding="utf-8"))
    except Exception as e: print(json.dumps({"ok":False,"errors":["json解析失败:%s"%e]},ensure_ascii=False)); return 1
    errs=[]
    for k in TOP:
        if k not in d: errs.append("缺顶层字段 %s"%k)
    if d.get("status") not in STATUS: errs.append("status非法")
    if not d.get("case_id"): errs.append("case_id为空")
    if not d.get("result"): errs.append("result 为空(主结果缺失)")
    if not d.get("sources"): errs.append("sources 为空(缺来源保留)")
    if errs: print(json.dumps({"ok":False,"errors":errs},ensure_ascii=False)); return 1
    print(json.dumps({"ok":True,"artifacts":len(d.get("artifacts",[]))},ensure_ascii=False)); return 0
if __name__=="__main__":
    sys.exit(main(sys.argv[1]) if len(sys.argv)>1 else 2)
