#!/usr/bin/env python3
"""pptx_build.py — page_plan→可编辑 .pptx(含备注讲稿+证据quote), 纯标准库.
build page_plan.json out.pptx [--template t.pptx]  (--template 继承母版/版式/主题/media)"""
import json, re, sys, zipfile
from xml.sax.saxutils import escape
RP = "http://schemas.openxmlformats.org/package/2006/relationships"
OD = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="%s" '
   'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"' % OD)
W, H = 12192000, 6858000
HDR = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
GRP = ('<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm>'
   '<a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>')
CM = ('<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3"'
   ' accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>')
def rel(i, t, tg):
  return '<Relationship Id="rId%d" Type="%s/%s" Target="%s"/>' % (i, OD, t, tg)
def rels(*rs):
  return HDR + '<Relationships xmlns="%s">%s</Relationships>' % (RP, "".join(rs))
def _fills(tag):
  f = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
  return '<a:%s>%s%s%s</a:%s>' % (tag, f, f, f, tag)
THEME = (HDR + '<a:theme %s name="T"><a:themeElements><a:clrScheme name="T">%s</a:clrScheme>'
    '<a:fontScheme name="T"><a:majorFont><a:latin typeface="Calibri Light"/><a:ea typeface=""/><a:cs typeface=""/></a:majorFont>'
    '<a:minorFont><a:latin typeface="Calibri"/><a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
    '<a:fmtScheme name="T">%s<a:lnStyleLst>%s</a:lnStyleLst><a:effectStyleLst>%s</a:effectStyleLst>%s'
    '</a:fmtScheme></a:themeElements></a:theme>') % (
  NS, "".join('<a:%s><a:srgbClr val="%s"/></a:%s>' % (k, v, k) for k, v in [
    ("dk1", "262626"), ("lt1", "FFFFFF"), ("dk2", "1F3864"), ("lt2", "DEEAF6"), ("accent1", "1F3864"),
    ("accent2", "2E75B6"), ("accent3", "548235"), ("accent4", "BF8F00"), ("accent5", "7030A0"),
    ("accent6", "C00000"), ("hlink", "0563C1"), ("folHlink", "954F72")]),
  _fills("fillStyleLst"),
  "".join('<a:ln w="%d"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' % w for w in (6350, 12700, 19050)),
  '<a:effectStyle><a:effectLst/></a:effectStyle>' * 3, _fills("bgFillStyleLst"))
def sp(sid, name, x, y, cx, cy, paras, fill=None, dash=False, anchor="t"):
  f = '<a:solidFill><a:srgbClr val="%s"/></a:solidFill>' % fill if fill else "<a:noFill/>"
  ln = ('<a:ln w="9525"><a:solidFill><a:srgbClr val="9CA3AF"/></a:solidFill><a:prstDash val="dash"/></a:ln>'
     if dash else '<a:ln><a:noFill/></a:ln>')
  ps = ""
  for runs in paras:
    rr = "".join('<a:r><a:rPr lang="zh-CN" sz="%d"%s><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:rPr>'
          '<a:t>%s</a:t></a:r>' % (sz, ' b="1"' if b else "", c, escape(t)) for t, sz, b, c in runs)
    ps += "<a:p>%s</a:p>" % (rr or '<a:endParaRPr lang="zh-CN"/>')
  return ('<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
      '<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>%s%s'
      '</p:spPr><p:txBody><a:bodyPr wrap="square" anchor="%s" lIns="91440" tIns="45720" rIns="91440" bIns="45720"/>'
      '<a:lstStyle/>%s</p:txBody></p:sp>') % (sid, escape(name), x, y, cx, cy, f, ln, anchor, ps)
def slide_xml(shapes):
  return (HDR + '<p:sld %s><p:cSld><p:spTree>%s%s</p:spTree></p:cSld>'
      '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>') % (NS, GRP, "".join(shapes))
def notes_xml(text):
  body = "".join('<a:p><a:r><a:rPr lang="zh-CN" sz="1200"/><a:t>%s</a:t></a:r></a:p>'
         % escape(l) for l in text.split("\n") if l.strip()) or "<a:p/>"
  return (HDR + '<p:notes %s><p:cSld><p:spTree>%s<p:sp><p:nvSpPr><p:cNvPr id="2" name="N"/>'
      '<p:cNvSpPr txBox="1"/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr><p:spPr><a:xfrm>'
      '<a:off x="685800" y="1143000"/><a:ext cx="5486400" cy="6858000"/></a:xfrm>'
      '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>%s</p:txBody>'
      '</p:sp></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:notes>') % (NS, GRP, body)
def content_shapes(s, total, meta):
  claim = str(s.get("claim", "")).strip()
  if s.get("role") == "title":
    return [sp(2, "t", 914400, 2200000, 10363200, 1600000, [[(str(s.get("title") or meta.get("title", "")), 3600, True, "1F3864")]], anchor="ctr"),
        sp(3, "st", 914400, 4000000, 10363200, 900000, [[(claim, 1600, False, "262626")],
         [("听众%s·%smin" % (meta.get("audience", ""), meta.get("duration_min", "")), 1200, False, "595959")]], anchor="ctr")]
  ev = "；".join("%s(%s)" % (e.get("ref", ""), e.get("locator", "")) for e in s.get("evidence", []))
  bl = [[("• " + b, 1600, False, "262626")] for b in s.get("bullets", [])] or [[("（见视觉方案）", 1400, False, "9CA3AF")]]
  sh = [sp(2, "bar", 0, 0, W, 820000, [[(str(s.get("title", ""))[:40], 2400, True, "FFFFFF")]], fill="1F3864"),
     sp(3, "bl", 274320, 1005840, 6400800, 4300000, bl),
     sp(4, "vis", 6949440, 1005840, 4973320, 4300000,
      [[("视觉：", 1200, True, "595959")], [(str(s.get("visual", "")).strip() or "纯文字", 1300, False, "262626")]],
      fill="F2F2F2", dash=True, anchor="ctr"),
     sp(5, "ev", 274320, 5390000, 11674880, 460000,
      [[("证据：", 1100, True, "595959"), (ev or "—", 1100, False, "595959")]]),
     sp(7, "pg", 11250000, 6620000, 900000, 240000, [[("%s/%s" % (s.get("n", "?"), total), 900, False, "9CA3AF")]])]
  if claim:
    sh.insert(4, sp(6, "cl", 274320, 5943600, 11674880, 640080,
            [[("▶ ", 1400, True, "1F3864"), (claim, 1400, True, "1F3864")]], fill="DEEAF6"))
  return sh
def build(plan_path, out_path, template=None):
  plan = json.load(open(plan_path, encoding="utf-8"))
  meta, slides = plan.get("meta", {}), plan.get("slides", [])
  if not slides:
    sys.exit("slides 为空")
  pkg, lay, mas, thm = {}, "slideLayout1.xml", "slideMaster1.xml", "theme1.xml"
  if template:
    try:
      zin = zipfile.ZipFile(template)
      pick = lambda p: sorted(n for n in zin.namelist() if re.match(p, n) and not n.endswith("/"))
      for n in pick(r"ppt/(slideMasters|slideLayouts|theme|media|notesMasters)/"):
        pkg[n] = zin.read(n)
      lays, masts = pick(r"ppt/slideLayouts/slideLayout\d+\.xml$"), pick(r"ppt/slideMasters/slideMaster\d+\.xml$")
      ths = pick(r"ppt/theme/theme\d+\.xml$")
      if not lays or not masts:
        raise ValueError("模板缺少 slideLayout/slideMaster")
      lay, mas = lays[0].split("/")[-1], masts[0].split("/")[-1]
      if ths:
        thm = ths[0].split("/")[-1]
    except Exception as e:
      print("模板读取失败(%s),回退内置" % e, file=sys.stderr)
      pkg, lay, mas, thm = {}, "slideLayout1.xml", "slideMaster1.xml", "theme1.xml"
  builtin = ("ppt/slideMasters/" + mas) not in pkg
  if builtin:
    pkg["ppt/theme/theme1.xml"] = THEME.encode()
    pkg["ppt/slideMasters/slideMaster1.xml"] = (
      HDR + '<p:sldMaster %s><p:cSld><p:spTree>%s</p:spTree></p:cSld>%s'
      '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst>'
      '<p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>' % (NS, GRP, CM)).encode()
    pkg["ppt/slideMasters/_rels/slideMaster1.xml.rels"] = rels(
      rel(1, "slideLayout", "../slideLayouts/slideLayout1.xml"), rel(2, "theme", "../theme/theme1.xml")).encode()
    pkg["ppt/slideLayouts/slideLayout1.xml"] = (
      HDR + '<p:sldLayout %s type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>%s</p:spTree></p:cSld>'
      '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>' % (NS, GRP)).encode()
    pkg["ppt/slideLayouts/_rels/slideLayout1.xml.rels"] = rels(
      rel(1, "slideMaster", "../slideMasters/slideMaster1.xml")).encode()
  if "ppt/notesMasters/notesMaster1.xml" not in pkg:
    pkg["ppt/notesMasters/notesMaster1.xml"] = (
      HDR + '<p:notesMaster %s><p:cSld><p:spTree>%s</p:spTree></p:cSld>%s</p:notesMaster>' % (NS, GRP, CM)).encode()
    pkg["ppt/notesMasters/_rels/notesMaster1.xml.rels"] = rels(rel(1, "theme", "../theme/" + thm)).encode()
  sids, pres = [], []
  for i, s in enumerate(slides, 1):
    sh = content_shapes(s, len(slides), meta)
    pkg["ppt/slides/slide%d.xml" % i] = slide_xml(sh).encode()
    pkg["ppt/slides/_rels/slide%d.xml.rels" % i] = rels(
      rel(1, "slideLayout", "../slideLayouts/" + lay), rel(2, "notesSlide", "../notesSlides/notesSlide%d.xml" % i)).encode()
    ev = "；".join("%s(%s)·%s" % (e.get("ref", ""), e.get("locator", ""), e.get("quote", ""))
          for e in s.get("evidence", []) if e.get("locator") or e.get("quote"))
    note = str(s.get("notes", ""))
    if ev:
      note = note + "\n[证据: " + ev + "]"
    pkg["ppt/notesSlides/notesSlide%d.xml" % i] = notes_xml(
      "%s\n[用时 %ss · 主张: %s]" % (note, s.get("time_s", 0), s.get("claim", ""))).encode()
    pkg["ppt/notesSlides/_rels/notesSlide%d.xml.rels" % i] = rels(
      rel(1, "notesMaster", "../notesMasters/notesMaster1.xml"), rel(2, "slide", "../slides/slide%d.xml" % i)).encode()
    sids.append('<p:sldId id="%d" r:id="rId%d"/>' % (255 + i, 2 + i))
    pres.append(rel(2 + i, "slide", "slides/slide%d.xml" % i))
  pkg["ppt/presentation.xml"] = (
    HDR + '<p:presentation %s><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
    '<p:notesMasterIdLst><p:notesMasterId r:id="rId2"/></p:notesMasterIdLst><p:sldIdLst>%s</p:sldIdLst>'
    '<p:sldSz cx="%d" cy="%d" type="wide"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
    % (NS, "".join(sids), W, H)).encode()
  pkg["ppt/_rels/presentation.xml.rels"] = rels(
    rel(1, "slideMaster", "slideMasters/" + mas), rel(2, "notesMaster", "notesMasters/notesMaster1.xml"), *pres).encode()
  pkg["_rels/.rels"] = rels(rel(1, "officeDocument", "ppt/presentation.xml")).encode()
  PM = "application/vnd.openxmlformats-officedocument."
  ctm = {"slideMaster": PM + "presentationml.slideMaster+xml", "slideLayout": PM + "presentationml.slideLayout+xml",
     "notesMaster": PM + "presentationml.notesMaster+xml", "theme": PM + "theme+xml",
     "slide": PM + "presentationml.slide+xml", "notesSlide": PM + "presentationml.notesSlide+xml",
     "presentation": PM + "presentationml.presentation.main+xml"}
  ovr = ['<Default Extension="%s" ContentType="%s"/>' % (e, c) for e, c in [
    ("rels", "application/vnd.openxmlformats-package.relationships+xml"), ("xml", "application/xml"),
    ("png", "image/png"), ("jpeg", "image/jpeg"), ("jpg", "image/jpeg"), ("svg", "image/svg+xml")]]
  for n in pkg:
    if not n.endswith(".xml"):
      continue
    base = n.split("/")[-1]
    key = "presentation" if base == "presentation.xml" else re.sub(r"\d+\.xml$", "", base)
    if key in ctm:
      ovr.append('<Override PartName="/%s" ContentType="%s"/>' % (n, ctm[key]))
  pkg["[Content_Types].xml"] = (HDR + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">%s</Types>'
                 % "".join(ovr)).encode()
  with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
    for n, b in sorted(pkg.items()):
      z.writestr(n, b)
  print("ok:%s(%d页, master=%s)" % (out_path, len(slides), "builtin" if builtin else "template"))
  return 0
if __name__ == "__main__":
  a = sys.argv[1:]
  if len(a) >= 3 and a[0] == "build":
    sys.exit(build(a[1], a[2], a[a.index("--template") + 1] if "--template" in a else None))
  sys.exit(__doc__ or 2)
