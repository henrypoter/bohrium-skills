#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scientific chart calibration, audit and fair-gain helper (standard library only).

Commands:
  inspect   --image FIG [--image ...] --table TABLE [--table ...] [--text TXT ...] --out manifest.json
  calibrate --spec calibration.json --out digitized.json [--manifest manifest.json]
  audit     --result result.json --extraction digitized.json --manifest manifest.json [--case case.json]
  gain      --baseline metrics.json --skill metrics.json --out gain.json

The vision-capable Agent supplies visually verified pixel anchors/points. This tool
performs real linear/log10/category mapping, error-bar and scale-bar arithmetic,
then audits evidence and safe arithmetic. It never invents missing pixels or ticks.
"""
import argparse
import ast
import hashlib
import json
import math
import operator
import os
import struct
import sys


class ChartError(Exception):
    pass


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def norm_text(value):
    return " ".join(str(value or "").split())


def image_info(path):
    """Read dimensions without decoding pixels. Unknown formats remain honest."""
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) < 33 or data[12:16] != b"IHDR":
            raise ChartError("PNG 缺 IHDR/文件被截断")
        width, height = struct.unpack(">II", data[16:24])
        return "PNG", width, height
    if data.startswith((b"GIF87a", b"GIF89a")):
        if len(data) < 10:
            raise ChartError("GIF 被截断")
        return "GIF", *struct.unpack("<HH", data[6:10])
    if data.startswith(b"BM"):
        if len(data) < 26:
            raise ChartError("BMP 被截断")
        return "BMP", *struct.unpack("<ii", data[18:26])
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 3 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            while i < len(data) and data[i] == 0xFF:
                i += 1
            if i >= len(data):
                break
            marker = data[i]
            i += 1
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                continue
            if i + 2 > len(data):
                break
            length = struct.unpack(">H", data[i:i + 2])[0]
            if length < 2 or i + length > len(data):
                raise ChartError("JPEG segment 被截断")
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if length < 7:
                    raise ChartError("JPEG SOF 被截断")
                height, width = struct.unpack(">HH", data[i + 3:i + 7])
                return "JPEG", width, height
            i += length
        raise ChartError("JPEG 未找到 SOF，可能裁剪/损坏")
    return "UNKNOWN", None, None


def inspect_command(args):
    if not args.image:
        raise ChartError("每例必须显式提供 --image；缺像素时不得构造")
    manifest = {"images": [], "tables": [], "texts": []}
    errors = []
    for kind, paths in (("images", args.image), ("tables", args.table), ("texts", args.text)):
        for i, path in enumerate(paths, 1):
            item = {"id": kind[:-1].upper() + str(i), "path": path,
                    "file": os.path.basename(path), "sha256": sha256(path), "bytes": os.path.getsize(path)}
            if kind == "images":
                try:
                    fmt, width, height = image_info(path)
                    item.update(format=fmt, width=width, height=height, readable=fmt != "UNKNOWN")
                    if fmt == "UNKNOWN":
                        item["warning"] = "格式尺寸未识别；Agent 可视觉读取但须声明，不能猜像素尺寸"
                except (ChartError, OSError) as e:
                    item.update(readable=False, error=str(e))
                    errors.append(str(e))
            manifest[kind].append(item)
    write_json(args.out, manifest)
    print(json.dumps({"ok": not errors, "images": len(manifest["images"]), "tables": len(manifest["tables"]),
                      "texts": len(manifest["texts"]), "errors": errors, "out": args.out}, ensure_ascii=False))
    return 1 if errors else 0


def finite_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ChartError(label + " 必须是数值")
    value = float(value)
    if not math.isfinite(value):
        raise ChartError(label + " 必须有限")
    return value


def rounded(value, places):
    # Python round is only for decimal display; uncertainty keeps unrounded raw bounds.
    answer = round(value, places)
    return 0.0 if answer == 0 else answer


def numeric_axis(axis, label):
    scale = axis.get("scale")
    if scale not in ("linear", "log10"):
        raise ChartError(label + " scale 必须为 linear/log10/category")
    if not axis.get("unit"):
        raise ChartError(label + " 单位不明：禁止自动标定，填 gap 而非猜单位")
    anchors = axis.get("pixel_anchors")
    if not isinstance(anchors, list) or len(anchors) != 2:
        raise ChartError(label + " 需要两个实测 pixel_anchors")
    p1, v1 = anchors[0]
    p2, v2 = anchors[1]
    p1, p2 = finite_number(p1, label + ".p1"), finite_number(p2, label + ".p2")
    v1, v2 = finite_number(v1, label + ".v1"), finite_number(v2, label + ".v2")
    if p1 == p2 or v1 == v2:
        raise ChartError(label + " 锚点退化，不能标定")
    if scale == "log10" and (v1 <= 0 or v2 <= 0):
        raise ChartError(label + " 对数轴锚点必须为正")
    places = axis.get("output_decimals")
    if not isinstance(places, int) or isinstance(places, bool) or not 0 <= places <= 12:
        raise ChartError(label + " output_decimals 须为 0..12 整数")
    if not norm_text(axis.get("precision_basis")):
        raise ChartError(label + " 缺 precision_basis，防止虚假精度")
    return {"scale": scale, "p1": p1, "p2": p2, "v1": v1, "v2": v2,
            "unit": axis["unit"], "places": places, "raw": axis}


def map_numeric(pixel, axis):
    pixel = finite_number(pixel, "pixel")
    if axis["scale"] == "linear":
        value = axis["v1"] + (pixel - axis["p1"]) * (axis["v2"] - axis["v1"]) / (axis["p2"] - axis["p1"])
        formula = "v1+(pixel-p1)*(v2-v1)/(p2-p1)"
    else:
        l1, l2 = math.log10(axis["v1"]), math.log10(axis["v2"])
        value = 10 ** (l1 + (pixel - axis["p1"]) * (l2 - l1) / (axis["p2"] - axis["p1"]))
        formula = "10**(log10(v1)+(pixel-p1)*(log10(v2)-log10(v1))/(p2-p1))"
    if not math.isfinite(value):
        raise ChartError("标定结果非有限数")
    return value, formula


def map_axis(pixel, axis, label):
    if axis.get("scale") == "category":
        categories = axis.get("categories")
        if not isinstance(categories, dict) or not categories:
            raise ChartError(label + " category 轴需要 categories:{label:pixel}")
        tolerance = finite_number(axis.get("category_tolerance_pixels", 2), label + ".category_tolerance")
        distances = sorted((abs(float(p) - float(pixel)), str(name)) for name, p in categories.items())
        if not distances or distances[0][0] > tolerance:
            raise ChartError(label + " 像素不落在已声明类别刻度容差内；不得猜类别")
        if len(distances) > 1 and distances[0][0] == distances[1][0]:
            raise ChartError(label + " 同时距两个类别最近，类别不确定")
        return distances[0][1], None, "nearest_declared_category", None
    numeric = numeric_axis(axis, label)
    value, formula = map_numeric(pixel, numeric)
    return rounded(value, numeric["places"]), value, formula, numeric


def uncertainty_interval(pixel, tolerance, axis):
    if axis is None:
        return None
    tolerance = finite_number(tolerance, "tolerance_pixels")
    if tolerance < 0:
        raise ChartError("tolerance_pixels 不得为负")
    values = [map_numeric(pixel - tolerance, axis)[0], map_numeric(pixel + tolerance, axis)[0]]
    return {"low": rounded(min(values), axis["places"]), "high": rounded(max(values), axis["places"]),
            "pixel_tolerance": tolerance}


def error_interval(endpoints, axis, label):
    if endpoints is None:
        return None
    if axis is None or not isinstance(endpoints, list) or len(endpoints) != 2:
        raise ChartError(label + " 需要两个像素端点且对应数值轴")
    vals = [map_numeric(finite_number(p, label), axis)[0] for p in endpoints]
    return {"low": rounded(min(vals), axis["places"]), "high": rounded(max(vals), axis["places"]),
            "pixel_endpoints": endpoints, "unit": axis["unit"]}


def validate_manifest_image(spec, manifest):
    if not manifest:
        return None
    images = manifest.get("images", [])
    matches = [x for x in images if x["id"] == spec.get("image_id")]
    if len(matches) != 1:
        raise ChartError("spec.image_id 未唯一匹配 manifest.images")
    return matches[0]


def calibrate_command(args):
    spec = read_json(args.spec)
    manifest = read_json(args.manifest) if args.manifest else None
    image = validate_manifest_image(spec, manifest)
    panels = spec.get("panels")
    if not isinstance(panels, list) or not panels:
        raise ChartError("spec.panels 必须非空")
    points, measurements, reviews = [], [], []
    seen = set()
    panel_ids = set()
    for panel in panels:
        pid = str(panel.get("panel_id") or "")
        if not pid or pid in panel_ids or not isinstance(panel.get("bbox"), list) or len(panel["bbox"]) != 4:
            raise ChartError("每个 panel 需要唯一 panel_id 和四元 bbox")
        panel_ids.add(pid)
        axes = panel.get("axes") or {}
        if "x" not in axes:
            raise ChartError(pid + " 缺 x 轴")
        for series in panel.get("series", []):
            sid = str(series.get("series_id") or "")
            if not sid or not norm_text(series.get("legend_label")) or not series.get("legend_bbox"):
                raise ChartError(pid + " 系列需要 series_id/legend_label/legend_bbox；图例缺失时应人工标 gap")
            y_axis_name = series.get("y_axis", "y")
            if y_axis_name not in axes:
                raise ChartError(pid + "/" + sid + " 引用了不存在的 " + y_axis_name)
            for point in series.get("points", []):
                point_id = str(point.get("point_id") or "")
                key = (pid, sid, point_id)
                if not point_id or key in seen:
                    raise ChartError("point_id 缺失或复合 ID 重复: %r" % (key,))
                seen.add(key)
                pixel = point.get("pixel")
                if not isinstance(pixel, list) or len(pixel) != 2:
                    raise ChartError(str(key) + " pixel 须为 [x,y]")
                x, x_raw, x_formula, x_num = map_axis(pixel[0], axes["x"], pid + ".x")
                y, y_raw, y_formula, y_num = map_axis(pixel[1], axes[y_axis_name], pid + "." + y_axis_name)
                tolerance = point.get("tolerance_pixels", [0, 0])
                if not isinstance(tolerance, list) or len(tolerance) != 2:
                    raise ChartError(str(key) + " tolerance_pixels 须为 [dx,dy]")
                x_unc = uncertainty_interval(pixel[0], tolerance[0], x_num)
                y_unc = uncertainty_interval(pixel[1], tolerance[1], y_num)
                x_err = error_interval(point.get("x_error_pixels"), x_num, str(key) + ".x_error")
                y_err = error_interval(point.get("y_error_pixels"), y_num, str(key) + ".y_error")
                semantics = point.get("error_semantics")
                status = "digitized"
                if (x_err or y_err) and not semantics:
                    reviews.append({"type": "ERROR_SEMANTICS_UNKNOWN", "signal": str(key),
                                    "action": "保留像素误差线，回图注确认 SD/SE/95CI/range；不得默认 SD", "status": "pending"})
                    status = "review"
                record = {"panel_id": pid, "series_id": sid, "point_id": point_id,
                          "x": x, "y": y, "x_unit": axes["x"].get("unit"), "y_unit": axes[y_axis_name].get("unit"),
                          "x_scale": axes["x"].get("scale"), "y_scale": axes[y_axis_name].get("scale"),
                          "y_axis": y_axis_name, "legend_label": series["legend_label"],
                          "x_raw": x_raw, "y_raw": y_raw, "x_uncertainty": x_unc, "y_uncertainty": y_unc,
                          "x_error": x_err, "y_error": y_err, "error_semantics": semantics,
                          "basis": "pixel_digitized", "status": status,
                          "pixel": pixel, "tolerance_pixels": tolerance,
                          "calibration": {"x_formula": x_formula, "y_formula": y_formula,
                                          "x_anchors": axes["x"].get("pixel_anchors", axes["x"].get("categories")),
                                          "y_anchors": axes[y_axis_name].get("pixel_anchors", axes[y_axis_name].get("categories"))},
                          "evidence": {"image_id": spec.get("image_id"), "panel_id": pid,
                                       "bbox": point.get("bbox") or panel["bbox"], "pixel": pixel}}
                points.append(record)
        for bar in panel.get("scale_bars", []):
            bid = str(bar.get("scale_bar_id") or "")
            pixels = finite_number(bar.get("pixel_length"), bid + ".pixel_length")
            real = finite_number(bar.get("value"), bid + ".value")
            if not bid or pixels <= 0 or real <= 0 or not bar.get("unit"):
                raise ChartError("scale bar 需 id、正 pixel_length/value 和明确 unit")
            for feature in bar.get("features", []):
                fp = finite_number(feature.get("pixel_length"), bid + ".feature.pixel_length")
                if fp < 0:
                    raise ChartError("feature pixel_length 不得为负")
                size = fp * real / pixels
                places = bar.get("output_decimals", 3)
                measurements.append({"measurement_id": feature.get("feature_id"), "scale_bar_id": bid,
                                     "panel_id": pid, "value": rounded(size, places), "unit": bar["unit"],
                                     "raw_value": size, "basis": "scale_bar_inferred",
                                     "formula": "feature_pixels*(bar_value/bar_pixels)",
                                     "inputs": {"feature_pixels": fp, "bar_value": real, "bar_pixels": pixels},
                                     "evidence": {"image_id": spec.get("image_id"), "panel_id": pid,
                                                  "bbox": feature.get("bbox") or bar.get("bbox") or panel["bbox"]}})
    out = {"image_id": spec.get("image_id"), "source_sha256": image.get("sha256") if image else spec.get("source_sha256"),
           "status": "partial" if reviews else "success", "points": points, "measurements": measurements,
           "reviews": reviews,
           "method": "Agent 视觉核实锚点/像素；脚本执行 linear/log10/category 标定与误差/比例尺真计算"}
    write_json(args.out, out)
    print(json.dumps({"ok": True, "status": out["status"], "points": len(points),
                      "measurements": len(measurements), "reviews": len(reviews), "out": args.out}, ensure_ascii=False))
    return 0


# Safe arithmetic: names must resolve to declared inputs; no calls/attributes.
BIN_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.Pow: operator.pow}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_eval(expression, inputs):
    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in inputs:
            return finite_number(inputs[node.id], "calculation input " + node.id)
        if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
            return BIN_OPS[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
            return UNARY_OPS[type(node.op)](visit(node.operand))
        raise ChartError("calculation.expression 含不安全/未声明语法")
    try:
        tree = ast.parse(expression, mode="eval")
        value = visit(tree)
        if not math.isfinite(value):
            raise ChartError("calculation 结果非有限数")
        return value
    except (SyntaxError, ZeroDivisionError, OverflowError) as e:
        raise ChartError("calculation 无法计算: %s" % e)


def pending_gain(input_hash):
    return {"status": "baseline_not_provided",
            "protocol": {"same_input": True, "same_permissions": True, "same_model": True, "same_budget": True,
                         "input_sha256": input_hash,
                         "quality_metric": "value/axis/element accuracy + supported_interpretations",
                         "efficiency_metric": "runtime_seconds and manual_rechecks"},
            "baseline_metrics": None, "skill_metrics": None, "delta": None,
            "note": "无平台同输入基础 Agent 实测时不填提升分；用 gain 子命令计算。"}


def point_key(p):
    return (p.get("panel_id"), p.get("series_id"), p.get("point_id"))


def audit_calculation(interp, points, cells, tag, errors):
    calc = interp.get("calculation")
    if not isinstance(calc, dict):
        errors.append(tag + " inferred 数值缺 calculation")
        return
    inputs, refs = calc.get("inputs"), calc.get("input_refs")
    if not isinstance(inputs, dict) or not isinstance(refs, dict) or set(inputs) != set(refs) or not inputs:
        errors.append(tag + " calculation inputs/input_refs 必须同键且非空")
        return
    for name, ref in refs.items():
        actual = None
        if ref.get("point_id"):
            matches = [p for p in points if p.get("point_id") == ref["point_id"]]
            if len(matches) == 1:
                actual = matches[0].get(ref.get("field", "y"))
        elif ref.get("table_cell_id"):
            matches = [c for c in cells if c.get("cell_id") == ref["table_cell_id"]]
            if len(matches) == 1:
                actual = matches[0].get(ref.get("field", "value"))
        if actual is None or not isinstance(actual, (int, float)) or isinstance(actual, bool):
            errors.append(tag + " input_refs." + name + " 未绑定唯一数值点/表单元格")
        elif not math.isclose(float(actual), float(inputs[name]), rel_tol=1e-12, abs_tol=1e-12):
            errors.append(tag + " inputs." + name + " 与引用值不一致")
    try:
        computed = safe_eval(calc.get("expression", ""), inputs)
        expected = finite_number(calc.get("result"), tag + ".result")
        tolerance = finite_number(calc.get("tolerance", 1e-9), tag + ".tolerance")
        if not math.isclose(computed, expected, rel_tol=tolerance, abs_tol=tolerance):
            errors.append("%s 算式不一致: computed=%r result=%r" % (tag, computed, expected))
        if interp.get("value") is not None and not math.isclose(expected, float(interp["value"]), rel_tol=tolerance, abs_tol=tolerance):
            errors.append(tag + " interpretation.value 与 calculation.result 不一致")
    except (ChartError, TypeError, ValueError) as e:
        errors.append(tag + " " + str(e))


def audit_command(args):
    errors = []
    try:
        result = read_json(args.result)
        extraction = read_json(args.extraction)
        manifest = read_json(args.manifest)
    except Exception as e:
        print(json.dumps({"ok": False, "errors": ["输入不可读: %s" % e]}, ensure_ascii=False))
        return 1
    required = ("case_id", "status", "figures", "tables", "axes", "series", "data_points", "measurements",
                "elements", "coverage", "interpretations", "sources", "uncertainty", "gaps", "change_records", "gain")
    for key in required:
        if key not in result:
            errors.append("result 缺顶层字段 " + key)
    if not result.get("case_id"):
        errors.append("case_id 为空")
    if result.get("status") not in ("success", "partial", "cannot_determine", "failed", "refused"):
        errors.append("顶层 status 非法")
    if args.case:
        case = read_json(args.case)
        if result.get("case_id") != case.get("case_id"):
            errors.append("case_id 与 /input/case.json 不一致")
        contract = case.get("output_contract", {})
        keys = contract if isinstance(contract, list) else contract.get("required", []) if isinstance(contract, dict) else []
        if isinstance(contract, dict) and isinstance(contract.get("properties"), dict):
            keys = list(keys) + list(contract["properties"])
        for key in keys:
            if key not in result:
                errors.append("缺原 output_contract 字段 " + key)
    images = manifest.get("images", [])
    if len(images) != 1:
        errors.append("修订 v2 要求每例恰好 1 张原图片，manifest 实际为 %d" % len(images))
    primary = [f for f in result.get("figures", []) if f.get("role") == "primary"]
    if len(primary) != 1:
        errors.append("figures 必须恰好一个 role=primary")
    elif images:
        expected, actual = images[0], primary[0]
        for key in ("id", "path", "sha256"):
            if actual.get("image_id" if key == "id" else key) != expected.get(key):
                errors.append("primary figure %s 与 manifest 不一致" % key)
    table_cells = []
    table_ids = set()
    for table in result.get("tables", []):
        tid = table.get("table_id")
        if tid in table_ids:
            errors.append("table_id 重复 " + str(tid))
        table_ids.add(tid)
        if table.get("status") not in ("extracted", "unreadable", "empty", "not_reported"):
            errors.append("table %s status 非法" % tid)
        if table.get("status") == "extracted" and not table.get("cells"):
            errors.append("table %s extracted 但 cells 为空" % tid)
        for cell in table.get("cells", []):
            for key in ("cell_id", "row", "column", "raw_value"):
                if key not in cell:
                    errors.append("table %s cell 缺 %s" % (tid, key))
            cell = dict(cell, table_id=tid)
            table_cells.append(cell)
    expected_tables = {t["id"] for t in manifest.get("tables", [])}
    if table_ids != expected_tables:
        errors.append("原表覆盖不完整/多出构造表: expected=%r actual=%r" % (sorted(expected_tables), sorted(table_ids)))
    # Quote checks use actual supplied caption/text files, not self-declared text.
    text_blobs = []
    for item in manifest.get("texts", []):
        try:
            with open(item["path"], encoding="utf-8", errors="strict") as f:
                text_blobs.append((item["id"], norm_text(f.read())))
        except Exception as e:
            errors.append("text %s 读取失败: %s" % (item.get("id"), e))
    # Axis declarations and log safety.
    for i, axis in enumerate(result.get("axes", [])):
        if axis.get("scale") not in ("linear", "log10", "category"):
            errors.append("axes[%d] scale 非法" % i)
        if axis.get("status") == "readable":
            if not axis.get("unit") and axis.get("scale") != "category":
                errors.append("axes[%d] readable 但单位为空" % i)
            if not axis.get("ticks") and axis.get("scale") != "category":
                errors.append("axes[%d] readable 但无刻度证据" % i)
        if axis.get("scale") == "log10":
            for tick in axis.get("ticks", []):
                if finite_number(tick.get("value"), "log tick") <= 0:
                    errors.append("axes[%d] 对数刻度非正" % i)
    extraction_points = extraction.get("points", [])
    result_points = result.get("data_points", [])
    exp_by_key = {point_key(p): p for p in extraction_points}
    got_by_key = {point_key(p): p for p in result_points}
    if len(exp_by_key) != len(extraction_points) or len(got_by_key) != len(result_points):
        errors.append("data point 复合 ID 重复")
    if set(exp_by_key) != set(got_by_key):
        errors.append("result.data_points 与 digitized.points 覆盖不一致")
    for key in set(exp_by_key) & set(got_by_key):
        expected, actual = exp_by_key[key], got_by_key[key]
        for field in ("x", "y", "x_unit", "y_unit", "x_scale", "y_scale", "pixel", "y_axis"):
            if actual.get(field) != expected.get(field):
                errors.append("点 %r 字段 %s 被篡改/错配" % (key, field))
        ev = actual.get("evidence") or {}
        if not ev.get("image_id") or not ev.get("bbox") or not ev.get("pixel"):
            errors.append("点 %r 缺图像/panel/bbox/pixel 读取路径" % (key,))
    if result.get("measurements") != extraction.get("measurements"):
        errors.append("比例尺 measurements 与真计算结果不一致")
    # Coverage checklist makes omitted chart elements explicit.
    coverage_types = ("axes", "ticks", "legend", "series", "data_points", "error_bars", "significance",
                      "scale_bars", "caption", "subpanels", "tables")
    for name in coverage_types:
        cov = (result.get("coverage") or {}).get(name)
        if not isinstance(cov, dict) or cov.get("status") not in ("observed", "not_visible", "not_reported", "uncertain"):
            errors.append("coverage.%s 缺合法状态" % name)
        elif cov.get("status") == "observed" and not cov.get("element_ids"):
            errors.append("coverage.%s observed 但 element_ids 为空" % name)
    for i, element in enumerate(result.get("elements", [])):
        if element.get("type") not in ("legend", "error_bar", "significance", "scale_bar", "caption", "subpanel", "axis_tick", "other"):
            errors.append("elements[%d] type 非法" % i)
        if element.get("status") == "observed" and not (element.get("bbox") or element.get("quote")):
            errors.append("elements[%d] observed 但无 bbox/quote" % i)
    # Interpretations: direct / inferred / unknown, verbatim quotes, real calculations.
    for i, interp in enumerate(result.get("interpretations", [])):
        tag = "interpretations[%d]" % i
        basis = interp.get("basis")
        if basis not in ("direct", "inferred", "unknown"):
            errors.append(tag + " basis 非法")
            continue
        ev = interp.get("evidence") or {}
        refs = ev.get("point_ids", []) + ev.get("table_cell_ids", [])
        quote = norm_text(ev.get("quote"))
        if basis == "unknown":
            if interp.get("value") is not None or not norm_text(interp.get("limits")):
                errors.append(tag + " unknown 必须有值 null 且 limits 说明")
        elif not refs and not quote:
            errors.append(tag + " direct/inferred 无点/表格/逐字图注证据")
        if quote:
            if not ev.get("location") or not any(quote in blob for _, blob in text_blobs):
                errors.append(tag + " quote 未逐字命中所给图注/正文或缺 location")
        if basis == "inferred" and interp.get("value") is not None:
            audit_calculation(interp, result_points, table_cells, tag, errors)
    unresolved = [g for g in result.get("gaps", []) if g.get("status", "pending") == "pending"]
    unresolved += [r for r in extraction.get("reviews", []) if r.get("status") == "pending"]
    for gap in result.get("gaps", []):
        for key in ("type", "signal", "action", "location"):
            if not gap.get(key):
                errors.append("gap 缺 " + key)
    if unresolved and result.get("status") == "success":
        errors.append("有 pending gap/review 却标 success")
    if not unresolved and result.get("status") == "partial":
        errors.append("无 pending gap/review 却标 partial")
    gain = result.get("gain") or {}
    if not gain.get("status") or not gain.get("protocol") or "delta" not in gain:
        errors.append("gain 缺 status/protocol/delta")
    # Every provided image/table/text source hash should remain visible.
    source_hashes = {s.get("sha256") for s in result.get("sources", [])}
    for group in ("images", "tables", "texts"):
        for src in manifest.get(group, []):
            if src.get("sha256") not in source_hashes:
                errors.append("sources 缺 %s 的 SHA256" % src.get("id"))
    print(json.dumps({"ok": not errors, "errors": errors, "points": len(result_points),
                      "tables": len(table_ids), "pending": len(unresolved)}, ensure_ascii=False))
    return 1 if errors else 0


def validate_metrics(doc, label):
    run = doc.get("run", {})
    for key in ("input_sha256", "permissions", "model", "budget_seconds"):
        if key not in run:
            raise ChartError("%s.run 缺 %s" % (label, key))
    integer_pairs = (("correct_values", "gold_values"), ("correct_axes", "gold_axes"),
                     ("correct_elements", "gold_elements"), ("supported_interpretations", "total_interpretations"))
    for good, total in integer_pairs:
        if not isinstance(doc.get(total), int) or doc[total] <= 0:
            raise ChartError("%s.%s 须为正整数" % (label, total))
        if not isinstance(doc.get(good), int) or not 0 <= doc[good] <= doc[total]:
            raise ChartError("%s.%s 超出 0..%s" % (label, good, total))
    for key in ("manual_rechecks", "runtime_seconds"):
        if not isinstance(doc.get(key), (int, float)) or isinstance(doc.get(key), bool) or doc[key] < 0:
            raise ChartError("%s.%s 须为非负数" % (label, key))


def gain_command(args):
    baseline, skill = read_json(args.baseline), read_json(args.skill)
    validate_metrics(baseline, "baseline")
    validate_metrics(skill, "skill")
    for key in ("input_sha256", "permissions", "model", "budget_seconds"):
        if baseline["run"][key] != skill["run"][key]:
            raise ChartError("对照不公平: run.%s 不一致" % key)
    delta = {}
    for good, total in (("values", "gold_values"), ("axes", "gold_axes"),
                        ("elements", "gold_elements"), ("interpretations", "total_interpretations")):
        bkey = "supported_interpretations" if good == "interpretations" else "correct_" + good
        b = baseline[bkey] / baseline[total]
        s = skill[bkey] / skill[total]
        delta[good + "_accuracy"] = s - b
        delta["baseline_" + good + "_accuracy"] = b
        delta["skill_" + good + "_accuracy"] = s
    for key in ("manual_rechecks", "runtime_seconds"):
        delta[key] = skill[key] - baseline[key]
    out = {"status": "complete", "protocol": {"same_input": True, "same_permissions": True,
           "same_model": True, "same_budget": True, "input_sha256": skill["run"]["input_sha256"]},
           "baseline_metrics": baseline, "skill_metrics": skill, "delta": delta}
    write_json(args.out, out)
    print(json.dumps({"ok": True, "delta": delta}, ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inspect")
    p.add_argument("--image", action="append", required=True)
    p.add_argument("--table", action="append", default=[])
    p.add_argument("--text", action="append", default=[])
    p.add_argument("--out", required=True)
    p.set_defaults(func=inspect_command)
    p = sub.add_parser("calibrate")
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--manifest")
    p.set_defaults(func=calibrate_command)
    p = sub.add_parser("audit")
    p.add_argument("--result", required=True)
    p.add_argument("--extraction", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--case")
    p.set_defaults(func=audit_command)
    p = sub.add_parser("gain")
    p.add_argument("--baseline", required=True)
    p.add_argument("--skill", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=gain_command)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (ChartError, OSError, ValueError, TypeError, json.JSONDecodeError) as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
