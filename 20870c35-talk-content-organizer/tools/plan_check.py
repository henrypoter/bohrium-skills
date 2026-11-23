#!/usr/bin/env python3
"""plan_check.py v2 — page_plan 校验 + result 骨架(纯标准库).
check page_plan.json qa_report.json [paper.txt] | init-result case.json result.json
v2: quote源回链/弧顺序/讲稿去重/要点≤6. 退出码0=pass 1=fail."""
import json, re, sys, datetime
ROLES = {"title","background","method","results","discussion","conclusion","thanks","backup"}
NEED_EV = {"method","results","discussion"}
LOC = re.compile(r"(§|p\.?\s*\d|页|Fig\.?|Figure|图\s*\d|Table|表\s*\d|Eq|式\s*\()")
CJK, ENG = re.compile(r"[一-鿿]"), re.compile(r"[A-Za-z]+")
ARC = ["title","background","method","results","discussion","conclusion","thanks"]
STRIP = re.compile(r"[\W_]+")
def density(notes, t, lang):
  if not notes.strip() or t <= 0:
    return ("fail" if t > 0 else "pass"), 0.0
  n = len((CJK if lang == "zh" else ENG).findall(notes))
  lo, hi = (2.0, 6.0) if lang == "zh" else (1.2, 4.0)
  return ("pass" if lo <= n / t <= hi else "warn"), round(n / t, 2)
def norm(s):
  return STRIP.sub("", str(s).lower())
def check(plan_path, report_path, source_path=None):
  plan = json.load(open(plan_path, encoding="utf-8"))
  src = norm(open(source_path, encoding="utf-8", errors="ignore").read()) if source_path else None
  items = []
  meta, slides = plan.get("meta", {}), plan.get("slides", [])
  lang, aud = meta.get("language", "zh"), str(meta.get("audience", ""))
  for k in ("case_id","title","audience","duration_min","slide_count"):
    if k not in meta: items.append(("fail","meta","缺字段 "+k))
  for k in ("problem","method","results","limitations"):
    if not str(plan.get("spine",{}).get(k,"")).strip():
      items.append(("warn","spine","缺 %s"%k))
  main = [s for s in slides if s.get("role") != "backup"]
  total = 0
  for s in slides:
    w, role = "slide %s" % s.get("n","?"), s.get("role","")
    if role not in ROLES: items.append(("fail", w, "非法 role %r"%role))
    claim = str(s.get("claim","")).strip()
    if role in NEED_EV | {"background"} and not claim:
      items.append(("fail", w, "缺 claim"))
    elif claim and len(claim) > 48:
      items.append(("warn", w, "主张%d字>40"%len(claim)))
    if len(s.get("bullets", [])) > 6:
      items.append(("warn", w, "要点%d条>6"%len(s.get("bullets",[]))))
    if role in NEED_EV:
      if not s.get("evidence"): items.append(("fail", w, "缺证据定位"))
      for e in s.get("evidence", []):
        loc = str(e.get("locator",""))
        if not LOC.search(loc): items.append(("fail", w, "定位不可回链:%r"%e))
        q = norm(e.get("quote",""))
        if not q: items.append(("fail", w, "缺 quote"))
        elif src is not None and q not in src:
          items.append(("fail", w, "quote不在源材料:%s(%s)"%(e.get("ref",""),loc)))
    if not str(s.get("visual","")).strip():
      items.append(("warn", w, "缺 visual"))
    notes, t = str(s.get("notes","")), s.get("time_s",0)
    if role == "backup":
      if t: items.append(("warn", w, "备用页time_s应为0"))
    else:
      total += t
      if role in {"title","thanks"} and not notes.strip():
        st, rate = "pass", 0.0
      else:
        st, rate = density(notes, t, lang)
      if st != "pass": items.append((st, w, "密度%s/s≠%ss"%(rate,t)))
      if notes.strip() and notes.strip() == claim: items.append(("fail", w, "讲稿照抄主张"))
      elif notes.strip() and notes.strip() == " ".join(s.get("bullets",[])):
        items.append(("warn", w, "讲稿照抄要点"))
  target = float(meta.get("duration_min",0))*60
  if target:
    dev = abs(total-target)/target
    items.append((("pass" if dev<=0.10 else ("warn" if dev<=0.20 else "fail")),"time",
      "正片%ds vs %ds(偏差%.0f%%)"%(total,target,dev*100)))
  if meta.get("slide_count") and len(main) != meta["slide_count"]:
    items.append(("warn","meta","slide_count=%s≠正片%d"%(meta["slide_count"],len(main))))
  if not any(s.get("role")=="backup" for s in slides) and not plan.get("qa_backup"):
    items.append(("warn","qa","无问答备用页"))
  idx = [ARC.index(s["role"]) for s in main if s.get("role") in ARC]
  if any(b < a for a,b in zip(idx, idx[1:])):
    items.append(("warn","arc","弧顺序乱序"))
  if aud in {"defense","review"} and "results" not in [s.get("role") for s in main]:
    items.append(("fail","arc","%s 缺结果页"%aud))
  fails = sum(1 for lv,_,_ in items if lv=="fail")
  rep = {"result":"fail" if fails else "pass","fails":fails,
     "warns":sum(1 for lv,_,_ in items if lv=="warn"),
     "slides_main":len(main),"slides_backup":len(slides)-len(main),
     "time_total_s":total,"time_target_s":target,"source_checked":bool(src),
     "items":[{"level":lv,"where":w,"msg":m} for lv,w,m in items]}
  json.dump(rep, open(report_path,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
  print("%s:%d fail,%d warn->%s"%(rep["result"],fails,rep["warns"],report_path))
  return 1 if fails else 0
def init_result(case_path, out_path):
  case = json.load(open(case_path, encoding="utf-8"))
  oc = case.get("output_contract", {})
  fields = list(oc) if isinstance(oc,dict) else (oc if isinstance(oc,list) else [])
  res = {k: None for k in fields}
  res.update({"case_id": case.get("case_id") or case.get("id") or "unknown","status":"in_progress",
    "status_reason":"骨架","sources":[],
    "uncertainties":["字段占位null"],
    "change_log":[{"ts":datetime.datetime.now(datetime.timezone.utc).isoformat(),"action":"init-result"}]})
  json.dump(res, open(out_path,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
  print("骨架->%s(%d字段)"%(out_path,len(fields)))
  return 0
if __name__ == "__main__":
  a = sys.argv[1:]
  if a and a[0]=="check" and len(a) in (3,4):
    sys.exit(check(a[1],a[2], a[3] if len(a)==4 else None))
  if a and a[0]=="init-result" and len(a)==3:
    sys.exit(init_result(a[1],a[2]))
  sys.exit(__doc__ or 2)
