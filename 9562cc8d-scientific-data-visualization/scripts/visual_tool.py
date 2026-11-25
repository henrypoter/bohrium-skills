#!/usr/bin/env python3
"""科研数据可视化（仅 Python 标准库）：推荐、真渲染、逐元素审计、结果契约。

recommend FIGURE_SPEC.json       按字段类型/目的给出推荐与不推荐理由
render FIGURE_SPEC.json          从 CSV 生成 SVG、300dpi PNG、绘图数据、图注、manifest
schema RESULT.json              版本、证据、图件、覆盖与增益契约检查
audit RESULT.json               重算绘图数据并核对图注、编码、颜色、尺寸、DPI、哈希

图型：bar/scatter/line/box/hist；退出码 0 通过、1 校验/执行失败、2 调用错误。
"""
import argparse
import csv
import hashlib
import html
import json
import math
import os
import re
import statistics
import struct
import sys
import tempfile
import zlib
from datetime import datetime, timezone


def parse_datetime(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def parse_timestamp(value):
    return parse_datetime(value).timestamp()

VERSION = "2.0.0"
DEFAULT_MISSING = {"", "na", "n/a", "nan", "null", "none", "."}
PALETTE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#000000"]
SHAPES = ["circle", "square", "diamond", "triangle", "cross", "circle", "square", "diamond"]
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def emit(obj, rc=0):
    print(json.dumps(obj, ensure_ascii=False, allow_nan=False, sort_keys=True))
    return rc


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_json(path):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层必须为对象")
    return obj


def number(value):
    text = str(value).strip()
    if not re.match(r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$", text):
        raise ValueError("非数值: %r" % text)
    result = float(text)
    if not math.isfinite(result):
        raise ValueError("非有限数值")
    return result


def read_csv(path):
    last = None
    for enc in ("utf-8-sig", "gb18030"):
        try:
            with open(path, encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                fields = reader.fieldnames
                if not fields or len(fields) != len(set(fields)) or any(not x for x in fields):
                    raise ValueError("空表头/重复列名")
                rows = list(reader)
            if not rows:
                raise ValueError("空表")
            if any(None in r for r in rows):
                raise ValueError("存在超出表头宽度的行")
            return rows, fields, enc
        except UnicodeDecodeError as exc:
            last = exc
    raise ValueError("CSV 解码失败: %s" % last)


def reject_undeclared_sentinel(value, missing):
    text = str(value).strip()
    if text in {"-999", "-9999", "9999"} and text.casefold() not in missing:
        raise ValueError("疑似缺失哨兵 %s 未在 missing_values 声明；不得当作真实值绘图" % text)


def is_number_column(rows, col):
    present = [r[col] for r in rows if str(r[col]).strip() != ""]
    if not present:
        return False
    try:
        for value in present:
            number(value)
        return True
    except ValueError:
        return False


def is_datetime_column(rows, col):
    present = [r[col] for r in rows if str(r[col]).strip() != ""]
    if not present:
        return False
    try:
        for value in present:
            datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def cmd_recommend(spec_path):
    spec = load_json(spec_path)
    rows, fields, _ = read_csv(spec["data"])
    x = (spec.get("x") or {}).get("column")
    y = (spec.get("y") or {}).get("column")
    for col in (x, y):
        if col and col not in fields:
            raise ValueError("字段不存在: %s" % col)
    purpose = spec.get("purpose")
    xnum, ynum = is_number_column(rows, x) if x else False, is_number_column(rows, y) if y else False
    xdate = is_datetime_column(rows, x) if x else False
    group = (spec.get("group") or {}).get("column")
    categories = len({r[group] for r in rows}) if group in fields else 0
    reason, chart = "", None
    if purpose == "correlation" and xnum and ynum:
        chart, reason = "scatter", "两个连续变量用位置编码；分类仅用颜色+形状分系列，不用面积/角度。"
    elif purpose == "trend" and (xdate or xnum) and ynum:
        chart, reason = "line", "有序时间/连续 x 用线段表达顺序；不得改画无序并列柱。"
    elif purpose == "comparison" and x and not xnum and ynum:
        chart, reason = "bar", "无序类别比较用长度且数值基线为 0；不使用饼图角度。"
    elif purpose == "distribution" and ynum:
        grouped = bool(group) or bool(x and x != y)
        chart, reason = ("box", "分组样本用五数概括呈现分布并保留样本量。") if grouped else ("hist", "单连续变量用等宽 bin 显示分布，bin 数写入 manifest。")
    elif purpose == "composition" and x and ynum:
        chart, reason = "stacked_bar", "构成可用堆叠长度而非饼图角度；本 render 尚未实现 stacked_bar，仅给选型建议。"
    if not chart:
        return emit({"ok": False, "error": "字段类型与 purpose 不匹配",
                     "observed": {"x_numeric": xnum, "x_datetime": xdate, "y_numeric": ynum}}, 1)
    warnings = ["类别数 %d>8：先分面或按明确规则归并，不硬塞单图" % categories] if categories > 8 else []
    rejected = {"pie": "角度/面积不利于精确比较", "dual_axis": "双轴易制造虚假相关；优先分面/标准化",
                "truncated_bar": "柱状图截断非零基线会夸大差异"}
    result = {"ok": True, "tool_version": VERSION, "recommended": chart, "reason": reason,
              "rejected": rejected, "warnings": warnings,
              "render_supported": chart in {"bar", "scatter", "line", "box", "hist"}}
    return emit(result)


def clean_rows(spec, rows, fields):
    where = spec.get("where", {})
    if not isinstance(where, dict) or any(k not in fields for k in where):
        raise ValueError("where 缺列或不是对象")
    indexed = [dict(row, __source_row=i) for i, row in enumerate(rows, 2)]
    selected = [r for r in indexed if all(str(r[k]) == str(v) for k, v in where.items())]
    dedup = spec.get("drop_duplicates", False)
    if dedup:
        keys = fields if dedup is True else dedup
        if not isinstance(keys, list) or not keys or any(k not in fields for k in keys):
            raise ValueError("drop_duplicates 须为 true 或有效列名数组")
        seen, unique = set(), []
        for row in selected:
            key = tuple(row[k] for k in keys)
            if key not in seen:
                seen.add(key); unique.append(row)
        selected = unique
    return selected


def parse_num_fields(row, fields, missing):
    vals = {}
    for field in fields:
        raw = str(row[field]).strip()
        if raw.casefold() in missing:
            return None
        vals[field] = number(raw)
    return vals


def quantile(values, p):
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    low = int(k); high = min(low + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (k - low)


def build_plot_data(spec, rows, fields):
    chart = spec.get("chart")
    if chart not in {"bar", "scatter", "line", "box", "hist"}:
        raise ValueError("render 不支持 chart: %s" % chart)
    xcol = (spec.get("x") or {}).get("column")
    ycol = (spec.get("y") or {}).get("column")
    gcol = (spec.get("group") or {}).get("column")
    for col in (ycol, xcol, gcol):
        if col and col not in fields:
            raise ValueError("缺列: %s" % col)
    if chart != "box" and not xcol:
        raise ValueError("该图型需要 x.column")
    if not ycol:
        raise ValueError("需要 y.column")
    selected = clean_rows(spec, rows, fields)
    missing = {str(v).strip().casefold() for v in spec.get("missing_values", sorted(DEFAULT_MISSING))}
    output, excluded = [], []
    if chart == "scatter" or chart == "line":
        for row in selected:
            source_row = row["__source_row"]
            try:
                reject_undeclared_sentinel(row[ycol], missing)
                if chart == "scatter":
                    reject_undeclared_sentinel(row[xcol], missing)
                parsed_y = parse_num_fields(row, [ycol], missing)
                if parsed_y is None:
                    raise ValueError("y 缺失")
                y = parsed_y[ycol]
                if chart == "scatter":
                    parsed_x = parse_num_fields(row, [xcol], missing)
                    if parsed_x is None:
                        raise ValueError("x 缺失")
                    xval = parsed_x[xcol]
                    xraw = row[xcol]
                else:
                    xraw = str(row[xcol]).strip()
                    if xraw.casefold() in missing:
                        raise ValueError("x 缺失")
                    xval = number(xraw) if spec.get("x", {}).get("type") == "continuous" else parse_timestamp(xraw)
                group = str(row[gcol]) if gcol else "all"
                output.append({"source_row": source_row, "x_raw": xraw, "x_value": xval,
                               "y": y, "group": group})
            except ValueError:
                raw_required = [row[xcol], row[ycol]] + ([row[gcol]] if gcol else [])
                if any(str(v).strip().casefold() in missing for v in raw_required):
                    excluded.append(source_row)
                else:
                    raise ValueError("第 %d 行存在未声明脏数值/日期" % source_row)
        if chart == "line":
            output.sort(key=lambda r: (r["group"], r["x_value"], r["source_row"]))
    elif chart == "hist":
        vals = []
        for row in selected:
            source_row = row["__source_row"]
            raw = row[ycol]
            if str(raw).strip().casefold() in missing:
                excluded.append(source_row); continue
            reject_undeclared_sentinel(raw, missing)
            try:
                vals.append((number(raw), source_row))
            except ValueError as exc:
                raise ValueError("第 %d 行 y 为脏数值" % source_row) from exc
        if not vals:
            raise ValueError("没有可绘制的数值")
        numeric = [v for v, _ in vals]
        bins = int(spec.get("bins", max(1, math.ceil(math.sqrt(len(numeric))))))
        if not 1 <= bins <= 100:
            raise ValueError("bins 须在 1..100")
        low, high = min(numeric), max(numeric)
        if low == high:
            low, high = low - 0.5, high + 0.5
        width = (high - low) / bins
        for i in range(bins):
            left = low + i * width; right = high if i == bins - 1 else low + (i + 1) * width
            members = [(v, r) for v, r in vals if (left <= v < right) or (i == bins - 1 and v == high)]
            output.append({"bin": i + 1, "bin_start": left, "bin_end": right,
                           "count": len(members), "source_rows": ";".join(str(r) for _, r in members)})
    else:
        # bar/box：x 为类别；box 未给 x 时用 All。
        buckets = {}
        for row in selected:
            source_row = row["__source_row"]
            raw = row[ycol]
            required_categories = ([row[xcol]] if xcol else []) + ([row[gcol]] if gcol else [])
            if any(str(v).strip().casefold() in missing for v in required_categories):
                excluded.append(source_row); continue
            if str(raw).strip().casefold() in missing:
                excluded.append(source_row); continue
            reject_undeclared_sentinel(raw, missing)
            try:
                y = number(raw)
            except ValueError as exc:
                raise ValueError("第 %d 行 y 为脏数值" % source_row) from exc
            x = str(row[xcol]) if xcol else "All"
            group = str(row[gcol]) if gcol else "all"
            buckets.setdefault((x, group), []).append((y, source_row))
        for (x, group), vals in sorted(buckets.items()):
            numbers = [v for v, _ in vals]
            base = {"x": x, "group": group, "n": len(vals),
                    "source_rows": ";".join(str(r) for _, r in vals)}
            if chart == "bar":
                mean = math.fsum(numbers) / len(numbers)
                sd = statistics.stdev(numbers) if len(numbers) > 1 else None
                base.update(mean=mean, sd=sd, sem=sd / math.sqrt(len(numbers)) if sd is not None else None)
            else:
                q1, med, q3 = quantile(numbers, .25), quantile(numbers, .5), quantile(numbers, .75)
                iqr = q3 - q1
                inliers = [v for v in numbers if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]
                outliers = [v for v in numbers if v < q1 - 1.5 * iqr or v > q3 + 1.5 * iqr]
                base.update(q1=q1, median=med, q3=q3, whisker_low=min(inliers),
                            whisker_high=max(inliers), outliers=";".join(str(v) for v in outliers))
            output.append(base)
    if not output:
        raise ValueError("清洗后没有可绘制数据")
    groups = sorted({str(r.get("group", "all")) for r in output})
    if len(groups) > 8:
        raise ValueError("类别数 %d>8：须明确分面或归并规则后重试" % len(groups))
    if chart == "bar" and any(r["n"] < 2 for r in output) and spec.get("error"):
        raise ValueError("误差线样本量不足：每组 n 至少为 2")
    return output, {"input_rows": len(rows), "selected_rows": len(selected),
                    "excluded_missing_rows": len(excluded), "excluded_source_rows": excluded,
                    "plotted_records": len(output), "groups": groups}


def almost(a, b, tol=1e-9):
    return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)


def nice_ticks(low, high, count=5, include_zero=False):
    if include_zero:
        low = min(0, low)
    if low == high:
        low -= 0.5; high += 0.5
    raw = (high - low) / count
    power = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = min((1, 2, 5, 10), key=lambda m: abs(m * power - raw)) * power
    start = math.floor(low / step) * step
    end = math.ceil(high / step) * step
    ticks = []
    for i in range(int(round((end - start) / step)) + 1):
        value = start + i * step
        if low - 1e-12 <= value <= high + 1e-12:
            ticks.append(value)
    return ticks, [start, end]


def fmt(value):
    if abs(value) >= 1e5 or (abs(value) < 1e-3 and value != 0):
        return "%.2g" % value
    return ("%.6f" % value).rstrip("0").rstrip(".") or "0"


def ascii_text(value):
    replacements = {"μ": "u", "µ": "u", "α": "alpha", "β": "beta", "±": "+/-", "×": "x", "²": "2", "³": "3"}
    text = str(value)
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text


# 5x7 位图字模；PNG 是无外部字体依赖的真实栅格预览，不伪造字体嵌入。
FONT = {
"0":[14,17,19,21,25,17,14],"1":[4,12,4,4,4,4,14],"2":[14,17,1,2,4,8,31],"3":[30,1,1,14,1,1,30],
"4":[2,6,10,18,31,2,2],"5":[31,16,16,30,1,1,30],"6":[14,16,16,30,17,17,14],"7":[31,1,2,4,8,8,8],
"8":[14,17,17,14,17,17,14],"9":[14,17,17,15,1,1,14],
"A":[14,17,17,31,17,17,17],"B":[30,17,17,30,17,17,30],"C":[14,17,16,16,16,17,14],
"D":[30,17,17,17,17,17,30],"E":[31,16,16,30,16,16,31],"F":[31,16,16,30,16,16,16],
"G":[14,17,16,23,17,17,15],"H":[17,17,17,31,17,17,17],"I":[14,4,4,4,4,4,14],
"J":[7,2,2,2,18,18,12],"K":[17,18,20,24,20,18,17],"L":[16,16,16,16,16,16,31],
"M":[17,27,21,21,17,17,17],"N":[17,25,21,19,17,17,17],"O":[14,17,17,17,17,17,14],
"P":[30,17,17,30,16,16,16],"Q":[14,17,17,17,21,18,13],"R":[30,17,17,30,20,18,17],
"S":[15,16,16,14,1,1,30],"T":[31,4,4,4,4,4,4],"U":[17,17,17,17,17,17,14],
"V":[17,17,17,17,17,10,4],"W":[17,17,17,21,21,21,10],"X":[17,17,10,4,10,17,17],
"Y":[17,17,10,4,4,4,4],"Z":[31,1,2,4,8,16,31],
"-":[0,0,0,31,0,0,0],"+":[0,4,4,31,4,4,0],".":[0,0,0,0,0,12,12],",":[0,0,0,0,4,4,8],
":":[0,12,12,0,12,12,0],";":[0,12,12,0,4,4,8],"/":[1,2,2,4,8,8,16],"\\":[16,8,8,4,2,2,1],
"(":[2,4,8,8,8,4,2],")":[8,4,2,2,2,4,8],"[":[14,8,8,8,8,8,14],"]":[14,2,2,2,2,2,14],
"_":[0,0,0,0,0,0,31],"=":[0,0,31,0,31,0,0],"<":[2,4,8,16,8,4,2],">":[8,4,2,1,2,4,8],
"%":[17,17,2,4,8,17,17],"*":[0,21,14,31,14,21,0],"?":[14,17,1,2,4,0,4],"!":[4,4,4,4,4,0,4],
" ":[0,0,0,0,0,0,0],"'":[4,4,8,0,0,0,0],"\"":[10,10,0,0,0,0,0]
}


def raster_text(raster, x, y, text, scale, color):
    unsupported = []
    x0 = int(x)
    for char in ascii_text(text).upper():
        if ord(char) > 127:
            unsupported.append(char); char = "?"
        glyph = FONT.get(char, FONT["?"])
        for yy, bits in enumerate(glyph):
            for xx in range(5):
                if bits & (1 << (4 - xx)):
                    raster.rect(x0 + xx * scale, int(y) + yy * scale,
                                x0 + (xx + 1) * scale - 1, int(y) + (yy + 1) * scale - 1, color)
        x0 += 6 * scale
    return unsupported


class Raster:
    def __init__(self, width, height, background="#FFFFFF"):
        self.width, self.height = width, height
        rgb = tuple(int(background[i:i+2], 16) for i in (1, 3, 5))
        self.data = bytearray(rgb * (width * height))

    def pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 3
            self.data[i:i+3] = bytes(color)

    def rect(self, x1, y1, x2, y2, color):
        if isinstance(color, str): color = rgb(color)
        x1, x2 = sorted((max(0, int(x1)), min(self.width - 1, int(x2))))
        y1, y2 = sorted((max(0, int(y1)), min(self.height - 1, int(y2))))
        row = bytes(color) * max(0, x2 - x1 + 1)
        for y in range(y1, y2 + 1):
            i = (y * self.width + x1) * 3
            self.data[i:i+len(row)] = row

    def line(self, x1, y1, x2, y2, color, width=1):
        steps = max(1, int(max(abs(x2 - x1), abs(y2 - y1))))
        radius = max(0, width // 2)
        for i in range(steps + 1):
            x = round(x1 + (x2 - x1) * i / steps); y = round(y1 + (y2 - y1) * i / steps)
            self.rect(x - radius, y - radius, x + radius, y + radius, color)

    def circle(self, cx, cy, radius, color, fill=True):
        color = rgb(color) if isinstance(color, str) else color
        for y in range(math.floor(cy - radius), math.ceil(cy + radius) + 1):
            for x in range(math.floor(cx - radius), math.ceil(cx + radius) + 1):
                dist = (x - cx) ** 2 + (y - cy) ** 2
                if (dist <= radius ** 2) if fill else (radius ** 2 * .65 <= dist <= radius ** 2 * 1.25):
                    self.pixel(x, y, color)


def rgb(color):
    return tuple(int(color[i:i+2], 16) for i in (1, 3, 5))


def png_chunk(kind, payload):
    return struct.pack("!I", len(payload)) + kind + payload + struct.pack("!I", zlib.crc32(kind + payload) & 0xffffffff)


def write_png(path, raster, dpi):
    raw = b"".join(b"\x00" + bytes(raster.data[y * raster.width * 3:(y + 1) * raster.width * 3])
                   for y in range(raster.height))
    ppm = round(dpi / 0.0254)
    payload = (b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack("!2I5B", raster.width, raster.height, 8, 2, 0, 0, 0))
               + png_chunk(b"pHYs", struct.pack("!IIB", ppm, ppm, 1)) + png_chunk(b"IDAT", zlib.compress(raw, 9))
               + png_chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(payload)


def axis_label(axis):
    label = str(axis.get("label") or axis.get("column") or "")
    unit = str(axis.get("unit") or "")
    return label + ((" [" + unit + "]") if unit else "")


def validate_spec(spec):
    if spec.get("spec_version") != VERSION or not spec.get("case_id") or not spec.get("id"):
        raise ValueError("spec_version/case_id/id 缺失或版本错误")
    if not re.match(r"^[A-Za-z0-9_-]+$", spec["id"]):
        raise ValueError("id 只允许字母数字_-")
    if not spec.get("data") or not HEX64.match(str(spec.get("source_sha256", ""))):
        raise ValueError("data/source_sha256 缺失")
    for axis in ("x", "y"):
        a = spec.get(axis, {})
        if axis == "y" and (not a.get("label") or "unit" not in a):
            raise ValueError("y 轴必须有 label 和 unit(无单位用空串)")
        if axis == "x" and spec.get("chart") != "box" and (not a.get("label") or "unit" not in a):
            raise ValueError("x 轴必须有 label 和 unit(无单位用空串)")
    requirements = spec.get("requirements", {})
    if requirements.get("scale_bar") or requirements.get("colorbar"):
        raise ValueError("比例尺/连续色标须用任务提供的空间或连续编码数据；当前单表渲染器不伪造")
    if spec.get("error") and (spec["error"] not in {"sd", "sem"} or spec.get("chart") != "bar"):
        raise ValueError("自动误差线仅 bar 支持 sd/sem；CI 须提供实际统计计算并人工审计")
    if spec.get("log_x"):
        raise ValueError("log_x 需先显式 log10 派生列并保留公式，当前版本不静默变换")
    if spec.get("chart") == "box" and spec.get("group"):
        raise ValueError("box 的类别放在 x.column；当前版本不对额外 group 做分面")
    if spec.get("chart") in {"bar", "hist"} and (spec.get("log_y") or spec.get("log_x")):
        raise ValueError("柱/直方图禁止对数轴与截断基线")
    for sig in spec.get("significance", []):
        if spec.get("chart") != "bar" or not all(k in sig for k in ("x", "label", "p", "method", "evidence")):
            raise ValueError("显著性仅限 bar，且需要 x/label/p/method/evidence")
        p = number(sig["p"])
        if not 0 <= p <= 1:
            raise ValueError("显著性 p 不在 [0,1]")


def render_scene(spec, data, width, height, dpi):
    xaxis, yaxis = spec.get("x", {}), spec.get("y", {})
    chart = spec["chart"]
    font_px = max(18, math.ceil(float(spec.get("min_font_pt", 7)) * dpi / 72))
    n_groups = len({str(r.get("group", "all")) for r in data})
    legend_rows = math.ceil(n_groups / 4) if spec.get("group") else 0
    top_ratio = .27 + .06 * max(0, legend_rows - 1) if legend_rows else .16
    left, right, top, bottom = math.ceil(width * .17), math.ceil(width * .04), math.ceil(height * min(.45, top_ratio)), math.ceil(height * .20)
    pw, ph = width - left - right, height - top - bottom
    scenes = []
    yvals = []
    for row in data:
        if chart == "box":
            yvals.extend(float(row[key]) for key in ("q1", "median", "q3", "whisker_low", "whisker_high"))
            yvals.extend(float(v) for v in row["outliers"].split(";") if v)
        elif chart == "hist":
            yvals.append(float(row["count"]))
        else:
            key = "mean" if chart == "bar" else "y"
            yvals.append(float(row[key]))
        if chart == "bar" and spec.get("error"):
            err = row.get(spec["error"])
            if err is not None: yvals.extend([row["mean"] - err, row["mean"] + err])
    ylow, yhigh = min(yvals), max(yvals)
    if chart in {"bar", "hist"}:
        ylow, yhigh = min(0, ylow), max(0, yhigh)
    if spec.get("log_y"):
        if ylow <= 0: raise ValueError("log_y 要求全部值为正")
        transform = math.log10
        ylow, yhigh = transform(ylow), transform(yhigh)
    else:
        transform = lambda v: v
    yticks, ydomain = nice_ticks(ylow, yhigh, include_zero=chart in {"bar", "hist"})
    yp = lambda v: top + ph - (transform(v) - ydomain[0]) / (ydomain[1] - ydomain[0]) * ph
    xmode = "continuous" if chart in {"scatter", "line"} else "category"
    if chart == "line" and spec.get("x", {}).get("type") != "continuous": xmode = "datetime"
    if chart == "hist": xmode = "bins"
    if xmode in {"continuous", "datetime"}:
        xvals = [float(r["x_value"]) for r in data]
        xticks, xdomain = nice_ticks(min(xvals), max(xvals))
        xp = lambda v: left + (float(v) - xdomain[0]) / (xdomain[1] - xdomain[0]) * pw
    elif chart == "hist":
        low = min(r["bin_start"] for r in data); high = max(r["bin_end"] for r in data)
        xticks, xdomain = nice_ticks(low, high)
        xp = lambda v: left + (v - xdomain[0]) / (xdomain[1] - xdomain[0]) * pw
    else:
        if chart == "box" and not spec.get("x"):
            categories = ["All"]
        else:
            categories = list(dict.fromkeys(r["x"] for r in data))
        xdomain = [0, max(1, len(categories))]
        xticks = categories[:]
        xp = lambda v: left + (categories.index(str(v)) + .5) / len(categories) * pw
    groups = sorted({str(r.get("group", "all")) for r in data})
    colors = {g: PALETTE[i % len(PALETTE)] for i, g in enumerate(groups)}
    shapes = {g: SHAPES[i % len(SHAPES)] for i, g in enumerate(groups)}
    # 细网格与坐标轴
    for tick in yticks:
        y = yp(tick)
        scenes.append({"kind": "line", "x1": left, "y1": y, "x2": left + pw, "y2": y, "stroke": "#DDDDDD", "width": 2})
        scenes.append({"kind": "text", "x": 8, "y": y - font_px * .45, "text": "10^%s" % fmt(tick) if spec.get("log_y") else fmt(tick), "size": font_px})
    scenes.extend([{"kind": "line", "x1": left, "y1": top, "x2": left, "y2": top + ph, "stroke": "#000000", "width": 3},
                   {"kind": "line", "x1": left, "y1": top + ph, "x2": left + pw, "y2": top + ph, "stroke": "#000000", "width": 3}])
    if xmode in {"category"}:
        for i, label in enumerate(xticks):
            scenes.append({"kind": "text", "x": xp(label) - font_px * 1.5, "y": top + ph + 12,
                           "text": str(label), "size": font_px})
    else:
        for tick in xticks:
            x = xp(tick)
            label = datetime.fromtimestamp(tick, timezone.utc).date().isoformat() if xmode == "datetime" else fmt(tick)
            scenes.append({"kind": "text", "x": x - font_px * 1.7, "y": top + ph + 12, "text": label, "size": font_px})
    scenes.append({"kind": "text", "x": left, "y": height - font_px * 1.25,
                   "text": axis_label(xaxis) + (" [log10]" if spec.get("log_x") else ""), "size": font_px})
    scenes.append({"kind": "text", "x": 8, "y": 5, "text": axis_label(yaxis) + (" [log10]" if spec.get("log_y") else ""), "size": font_px})
    title = spec.get("title", "")
    if title: scenes.append({"kind": "text", "x": left, "y": font_px * 2.1, "text": title, "size": font_px})
    # 图例：颜色 + 形状/线型双编码；无色盲读者仅依赖颜色。
    if groups != ["all"] or spec.get("group"):
        for i, group in enumerate(groups):
            gx = left + (i % 4) * max(150, pw // 4); gy = top - font_px * (1.5 + (i // 4))
            scenes.append({"kind": "marker", "x": gx, "y": gy, "color": colors[group], "shape": shapes[group], "size": 9})
            scenes.append({"kind": "text", "x": gx + 18, "y": gy - font_px * .5, "text": group, "size": font_px})
    # 数据元素
    if chart in {"scatter", "line"}:
        for group in groups:
            rows = [r for r in data if r["group"] == group]
            if chart == "line":
                points = [(xp(r["x_value"]), yp(r["y"])) for r in rows]
                scenes.append({"kind": "polyline", "points": points, "stroke": colors[group], "width": 3})
            for r in rows:
                scenes.append({"kind": "marker", "x": xp(r["x_value"]), "y": yp(r["y"]),
                               "color": colors[group], "shape": shapes[group], "size": 7})
    elif chart == "bar":
        categories = list(dict.fromkeys(r["x"] for r in data)); slot = pw / len(categories)
        active_groups = groups if spec.get("group") else ["all"]
        bw = slot * .72 / len(active_groups)
        for r in data:
            gindex = active_groups.index(r["group"]); center = xp(r["x"])
            x = center - slot * .36 + gindex * bw
            scenes.append({"kind": "rect", "x1": x, "y1": yp(0), "x2": x + bw * .92, "y2": yp(r["mean"]),
                           "fill": colors[r["group"]]})
            err = r.get(spec.get("error")) if spec.get("error") else None
            if err is not None:
                ex = x + bw * .46
                scenes.append({"kind": "line", "x1": ex, "y1": yp(r["mean"] - err), "x2": ex, "y2": yp(r["mean"] + err), "stroke": "#000000", "width": 3})
                scenes.append({"kind": "line", "x1": ex - 5, "y1": yp(r["mean"] - err), "x2": ex + 5, "y2": yp(r["mean"] - err), "stroke": "#000000", "width": 3})
                scenes.append({"kind": "line", "x1": ex - 5, "y1": yp(r["mean"] + err), "x2": ex + 5, "y2": yp(r["mean"] + err), "stroke": "#000000", "width": 3})
    elif chart == "hist":
        for r in data:
            scenes.append({"kind": "rect", "x1": xp(r["bin_start"]) + 1, "y1": yp(0),
                           "x2": xp(r["bin_end"]) - 1, "y2": yp(r["count"]), "fill": colors["all"]})
    elif chart == "box":
        categories = list(dict.fromkeys(r["x"] for r in data)); bw = pw / len(categories) * .35
        for r in data:
            x = xp(r["x"])
            scenes.append({"kind": "line", "x1": x, "y1": yp(r["whisker_low"]), "x2": x, "y2": yp(r["whisker_high"]), "stroke": "#000000", "width": 3})
            scenes.append({"kind": "rect", "x1": x - bw / 2, "y1": yp(r["q3"]), "x2": x + bw / 2, "y2": yp(r["q1"]), "fill": colors[r["group"]]})
            scenes.append({"kind": "line", "x1": x - bw / 2, "y1": yp(r["median"]), "x2": x + bw / 2, "y2": yp(r["median"]), "stroke": "#000000", "width": 4})
            for outlier in [float(v) for v in r["outliers"].split(";") if v]:
                scenes.append({"kind": "marker", "x": x, "y": yp(outlier), "color": colors[r["group"]], "shape": "cross", "size": 6})
    # 显著性括号必须附真实检验证据，不计算或编造 p。
    for sig in spec.get("significance", []):
        x = xp(sig["x"]); y = top + 15 + len(scenes) % 3 * 25
        scenes.append({"kind": "text", "x": x, "y": y, "text": sig["label"], "size": font_px})
    panel = spec.get("requirements", {}).get("panel")
    if panel: scenes.append({"kind": "text", "x": 8, "y": top - font_px, "text": str(panel), "size": font_px, "bold": True})
    axes = {"x": {"type": xmode, "domain": xdomain, "ticks": xticks, "label": axis_label(xaxis), "unit": xaxis.get("unit", "")},
            "y": {"type": "log10" if spec.get("log_y") else "linear", "domain": ydomain, "ticks": yticks, "label": axis_label(yaxis), "unit": yaxis.get("unit", "")}}
    return scenes, axes, colors, shapes, font_px


def write_svg(path, scenes, width, height, width_mm, height_mm, title, caption):
    def text(item):
        attrs = "font-weight='bold'" if item.get("bold") else ""
        return "<text x='%.3f' y='%.3f' font-size='%.3f' font-family='DejaVu Sans,Arial,sans-serif' %s>%s</text>" % (
            item["x"], item["y"] + item["size"] * .75, item["size"], attrs, html.escape(str(item["text"])))
    body = []
    for item in scenes:
        kind = item["kind"]
        if kind == "text": body.append(text(item))
        elif kind == "line": body.append("<line x1='%.3f' y1='%.3f' x2='%.3f' y2='%.3f' stroke='%s' stroke-width='%s'/>" % (item["x1"], item["y1"], item["x2"], item["y2"], item["stroke"], item.get("width", 1)))
        elif kind == "rect": body.append("<rect x='%.3f' y='%.3f' width='%.3f' height='%.3f' fill='%s'/>" % (min(item["x1"], item["x2"]), min(item["y1"], item["y2"]), abs(item["x2"] - item["x1"]), abs(item["y2"] - item["y1"]), item["fill"]))
        elif kind == "polyline": body.append("<polyline points='%s' fill='none' stroke='%s' stroke-width='%s'/>" % (" ".join("%.3f,%.3f" % p for p in item["points"]), item["stroke"], item["width"]))
        elif kind == "marker":
            x, y, s, color = item["x"], item["y"], item["size"], item["color"]; shape = item["shape"]
            if shape == "square": body.append("<rect x='%.3f' y='%.3f' width='%s' height='%s' fill='%s'/>" % (x-s, y-s, 2*s, 2*s, color))
            elif shape in {"diamond", "triangle"}:
                points = [(x, y-s), (x+s, y), (x, y+s), (x-s, y)] if shape == "diamond" else [(x, y-s), (x+s, y+s), (x-s, y+s)]
                body.append("<polygon points='%s' fill='%s'/>" % (" ".join("%.3f,%.3f" % p for p in points), color))
            elif shape == "cross": body.append("<path d='M %s %s L %s %s M %s %s L %s %s' stroke='%s' stroke-width='3'/>" % (x-s,y-s,x+s,y+s,x-s,y+s,x+s,y-s,color))
            else: body.append("<circle cx='%.3f' cy='%.3f' r='%s' fill='%s'/>" % (x, y, s, color))
    content = """<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns='http://www.w3.org/2000/svg' width='%smm' height='%smm' viewBox='0 0 %s %s' role='img' aria-labelledby='title desc'>
<title id='title'>%s</title><desc id='desc'>%s</desc>
<rect width='100%%' height='100%%' fill='white'/>%s</svg>
""" % (width_mm, height_mm, width, height, html.escape(title), html.escape(caption), "\n".join(body))
    with open(path, "w", encoding="utf-8") as f: f.write(content)


def draw_raster(scenes, width, height, png_label_map):
    raster = Raster(width, height); unsupported = []
    for item in scenes:
        kind = item["kind"]
        if kind == "line": raster.line(item["x1"], item["y1"], item["x2"], item["y2"], rgb(item["stroke"]), int(item.get("width", 1)))
        elif kind == "rect": raster.rect(item["x1"], item["y1"], item["x2"], item["y2"], item["fill"])
        elif kind == "polyline":
            for a, b in zip(item["points"], item["points"][1:]): raster.line(a[0], a[1], b[0], b[1], rgb(item["stroke"]), int(item["width"]))
        elif kind == "marker":
            x, y, s, color = item["x"], item["y"], item["size"], item["color"]
            if item["shape"] == "square": raster.rect(x-s, y-s, x+s, y+s, color)
            elif item["shape"] in {"cross", "diamond", "triangle"}:
                if item["shape"] == "diamond": points = [(x,y-s),(x+s,y),(x,y+s),(x-s,y),(x,y-s)]
                elif item["shape"] == "triangle": points = [(x,y-s),(x+s,y+s),(x-s,y+s),(x,y-s)]
                else: points = [(x-s,y-s),(x+s,y+s)]
                for a,b in zip(points,points[1:]): raster.line(a[0],a[1],b[0],b[1],rgb(color),3)
                if item["shape"] == "cross": raster.line(x-s,y+s,x+s,y-s,rgb(color),3)
            else: raster.circle(x,y,s,color)
        elif kind == "text":
            original = str(item["text"]); text = png_label_map.get(original, original)
            scale = max(1, math.ceil(item["size"] / 7))
            unsupported.extend(raster_text(raster, item["x"], item["y"], text, scale, (0,0,0)))
    return raster, sorted(set(unsupported))


def csv_value(value):
    if value is None: return ""
    if isinstance(value, float): return format(value, ".17g")
    return str(value)


def write_plot_csv(path, data):
    fields = list(data[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in data: writer.writerow({k: csv_value(row.get(k)) for k in fields})


def make_caption(spec, data_info, data):
    chart_names = {"bar":"柱状图", "scatter":"散点图", "line":"折线图", "box":"箱线图", "hist":"直方图"}
    y = axis_label(spec.get("y", {})); x = axis_label(spec.get("x", {})) or "全部样本"
    n_text = "；各组 n=" + ", ".join("%s/%s:%s" % (r["x"], r["group"], r["n"]) for r in data) if spec["chart"] in {"bar", "box"} else "；绘图记录 n=%d" % len(data)
    error = ("；误差线=" + {"sd":"样本标准差(SD)", "sem":"均值标准误(SEM)"}[spec["error"]]) if spec.get("error") else ""
    missing = "；排除缺失行=%d，源行=%s" % (data_info["excluded_missing_rows"], data_info["excluded_source_rows"] or "无")
    method = "；箱线须为 Q1/median/Q3，须线为 1.5×IQR 内极值" if spec["chart"] == "box" else ""
    sig = "".join("；%s: p=%s (%s, evidence=%s)" % (s["label"], s["p"], s["method"], s["evidence"]) for s in spec.get("significance", []))
    return "%s：x=%s，y=%s%s%s%s%s%s。" % (chart_names[spec["chart"]], x, y, n_text, error, missing, method, sig)


def png_label_map(spec):
    mapping = {}
    for key in ("title",):
        if spec.get(key + "_png") and spec.get(key): mapping[spec[key]] = spec[key + "_png"]
    for key in ("x", "y"):
        axis = spec.get(key, {})
        if axis.get("label_png"):
            mapping[axis_label(axis)] = ascii_text(axis["label_png"]) + ((" [" + str(axis.get("unit", "")) + "]") if axis.get("unit") else "")
    if spec.get("x", {}).get("tick_labels_png"):
        mapping.update({str(k): str(v) for k,v in spec["x"]["tick_labels_png"].items()})
    return mapping


def cmd_render(spec_path):
    spec = load_json(spec_path)
    validate_spec(spec)
    rows, fields, encoding = read_csv(spec["data"])
    if sha256(spec["data"]) != spec["source_sha256"]:
        raise ValueError("源 CSV SHA256 不匹配；不得用过期图件")
    data, info = build_plot_data(spec, rows, fields)
    export = spec.get("export", {})
    width_mm, height_mm, dpi = float(export.get("width_mm", 85)), float(export.get("height_mm", 60)), int(export.get("dpi", 300))
    if dpi < 300 or not 40 <= width_mm <= 300 or not 40 <= height_mm <= 300:
        raise ValueError("发表级导出要求 dpi>=300、宽高 40..300mm")
    width, height = round(width_mm / 25.4 * dpi), round(height_mm / 25.4 * dpi)
    if width * height > 40000000:
        raise ValueError("画布超过 4000 万像素，降低尺寸以控制内存")
    if float(spec.get("min_font_pt", 7)) < 7:
        raise ValueError("最终尺寸最小字号不得低于 7pt")
    scenes, axes, colors, shapes, font_px = render_scene(spec, data, width, height, dpi)
    output_dir = spec.get("output_dir") or os.path.dirname(os.path.abspath(spec_path))
    os.makedirs(output_dir, exist_ok=True)
    stem = spec["id"]
    svg_path = os.path.join(output_dir, stem + ".svg")
    png_path = os.path.join(output_dir, stem + ".png")
    data_path = os.path.join(output_dir, stem + "-figure-data.csv")
    caption_path = os.path.join(output_dir, stem + "-caption.txt")
    manifest_path = os.path.join(output_dir, stem + "-manifest.json")
    caption = make_caption(spec, info, data)
    label_map = png_label_map(spec)
    write_plot_csv(data_path, data)
    write_svg(svg_path, scenes, width, height, width_mm, height_mm, spec.get("title", stem), caption)
    raster, unsupported = draw_raster(scenes, width, height, label_map)
    write_png(png_path, raster, dpi)
    with open(caption_path, "w", encoding="utf-8") as f: f.write(caption + "\n")
    warnings = []
    all_text = " ".join(str(s.get("text", "")) for s in scenes)
    if any(ord(c) > 127 for c in ascii_text(all_text)) and not label_map and unsupported:
        warnings.append("PNG 有未映射非 ASCII 文本，已用?显示；SVG 完整，投稿前须配置 *_png 或人工检查")
    # 产物视觉元素在 audit 中由源数据确定性重绘比对。
    audit_state = {"colorbar":"not_checked(无连续色标)", "scale_bar":"not_checked(非空间图像)",
                   "svg_font_embedding":"not_checked(SVG 保留可编辑文本，字体未嵌入)", "png_font":"内置5x7矢量字模栅格化，无系统字体依赖"}
    manifest = {"manifest_version": VERSION, "tool_version": VERSION, "case_id": spec["case_id"], "id": stem,
                "chart": spec["chart"], "purpose": spec.get("purpose"), "source": os.path.abspath(spec["data"]),
                "source_sha256": spec["source_sha256"], "encoding": encoding, "spec": spec,
                "figure_data": data_path, "svg": svg_path, "png": png_path, "caption_path": caption_path,
                "caption": caption, "data_quality": info, "axes": axes, "colors": colors, "shapes": shapes,
                "error_definition": spec.get("error"), "significance": spec.get("significance", []),
                "export": {"width_mm": width_mm, "height_mm": height_mm, "dpi": dpi,
                           "width_px": width, "height_px": height, "min_font_pt": spec.get("min_font_pt", 7)},
                "font_px": font_px, "warnings": warnings, "visual_coverage": audit_state,
                "png_label_map": label_map}
    manifest["figure_data_sha256"] = sha256(data_path); manifest["svg_sha256"] = sha256(svg_path)
    manifest["png_sha256"] = sha256(png_path); manifest["caption_sha256"] = sha256(caption_path)
    with open(manifest_path, "w", encoding="utf-8") as f: json.dump(manifest, f, ensure_ascii=False, indent=2, allow_nan=False)
    return emit({"ok": not warnings, "status": "pass" if not warnings else "issues",
                 "manifest": manifest_path, "svg": svg_path, "png": png_path,
                 "figure_data": data_path, "caption": caption, "warnings": warnings}, 0 if not warnings else 1)


def read_png_metadata(path):
    with open(path, "rb") as f: raw = f.read()
    if raw[:8] != b"\x89PNG\r\n\x1a\n": raise ValueError("不是 PNG")
    offset, metadata = 8, {}
    while offset + 12 <= len(raw):
        size = struct.unpack("!I", raw[offset:offset+4])[0]; kind = raw[offset+4:offset+8]
        payload = raw[offset+8:offset+8+size]
        if kind == b"IHDR": metadata["width_px"], metadata["height_px"] = struct.unpack("!II", payload[:8])
        if kind == b"pHYs":
            xppm, yppm, unit = struct.unpack("!IIB", payload)
            if unit == 1: metadata["dpi"] = xppm * .0254
        offset += size + 12
    return metadata


def deuteranopia(color):
    # 近似的线性变换用于编码失败筛查，不声称临床级模拟。
    r,g,b = [v/255 for v in rgb(color)]
    return tuple(max(0,min(255,255*x)) for x in (.625*r+.375*g, .7*r+.3*g, .3*r+.7*b))


def color_conflicts(colors):
    conflicts = []
    items = list(colors.items())
    for i,(ga,ca) in enumerate(items):
        for gb,cb in items[i+1:]:
            normal = math.dist(rgb(ca),rgb(cb)); cvd = math.dist(deuteranopia(ca),deuteranopia(cb))
            la = sum(v*w for v,w in zip(rgb(ca),(.2126,.7152,.0722))); lb = sum(v*w for v,w in zip(rgb(cb),(.2126,.7152,.0722)))
            if normal < 40 or (cvd < 25 and abs(la-lb) < 20): conflicts.append({"groups":[ga,gb],"normal_distance":round(normal,2),"cvd_distance":round(cvd,2),"gray_luminance_delta":round(abs(la-lb),2)})
    return conflicts


def result_schema_errors(result):
    errors = []
    required = ("schema_version","skill_version","case_id","status","questions","figures","lineage","gain","coverage","unchecked","sources","uncertainty","change_log")
    for key in required:
        if key not in result: errors.append("缺顶层字段 %s" % key)
    if result.get("schema_version") != VERSION or result.get("skill_version") != VERSION: errors.append("版本必须为 %s" % VERSION)
    if not result.get("case_id"): errors.append("case_id 为空")
    if result.get("status") not in {"pass","issues","partial","failed"}: errors.append("status 非法")
    for i,q in enumerate(result.get("questions", [])):
        if not q.get("id") or q.get("answer") in (None,""): errors.append("questions[%d] 缺 id/answer" % i)
        ev = q.get("evidence")
        if not isinstance(ev,list) or not ev: errors.append("questions[%d] 缺 evidence" % i); continue
        for j,e in enumerate(ev):
            if not isinstance(e,dict) or not e.get("artifact") or not e.get("location"): errors.append("questions[%d].evidence[%d] 缺 artifact/location" % (i,j))
            elif not e.get("quote") and not HEX64.match(str(e.get("sha256",""))): errors.append("questions[%d].evidence[%d] 缺 quote/sha256" % (i,j))
    lineage = result.get("lineage",{})
    for key in ("snapshot","tables","source_sha256","commands","plot_spec","code"):
        if key not in lineage: errors.append("lineage 缺 %s" % key)
    if not HEX64.match(str(lineage.get("source_sha256",""))): errors.append("lineage.source_sha256 非法")
    for i,s in enumerate(result.get("sources", [])):
        if not isinstance(s,dict) or not s.get("path") or not HEX64.match(str(s.get("sha256",""))): errors.append("sources[%d] 缺 path/sha256" % i)
    for key in ("cleaning","statistics","chart_selection","encoding","annotation","readability","export"):
        state = result.get("coverage",{}).get(key,{})
        if state.get("status") not in {"pass","issues","not_checked"}: errors.append("coverage.%s 状态非法" % key)
        if state.get("status") == "not_checked" and not state.get("reason"): errors.append("coverage.%s not_checked 缺 reason" % key)
    for i,fig in enumerate(result.get("figures", [])):
        for key in ("id","manifest","manifest_sha256","svg","png","figure_data","caption","source_sha256"):
            if not fig.get(key): errors.append("figures[%d] 缺 %s" % (i,key))
        if not HEX64.match(str(fig.get("manifest_sha256",""))): errors.append("figures[%d].manifest_sha256 非法" % i)
    gain = result.get("gain",{})
    if not gain.get("protocol_version") or gain.get("same_input") is not True or gain.get("same_permissions") is not True: errors.append("gain 对照协议不完整")
    for arm in ("baseline","skill"):
        a = gain.get(arm,{})
        if a.get("status") not in {"measured","not_checked"}: errors.append("gain.%s.status 非法" % arm)
        if not isinstance(a.get("quality"),dict) or not isinstance(a.get("efficiency"),dict): errors.append("gain.%s 缺 quality/efficiency" % arm)
        if a.get("status") == "measured" and not a.get("evidence"): errors.append("gain.%s measured 缺 evidence" % arm)
    if result.get("status") == "pass" and (result.get("unchecked") or result.get("uncertainty")): errors.append("pass 时 unchecked/uncertainty 须为空")
    return errors


def cmd_schema(path):
    result = load_json(path); errors = result_schema_errors(result)
    return emit({"ok":not errors,"errors":errors,"tool_version":VERSION},0 if not errors else 1)


def audit_manifest(manifest_path, declared_hash=None):
    errors, checks = [], 0
    manifest = load_json(manifest_path)
    if manifest.get("manifest_version") != VERSION: errors.append("manifest 版本不一致")
    if declared_hash and sha256(manifest_path) != declared_hash: errors.append("result 中 manifest SHA256 不一致")
    source = manifest["source"]
    if sha256(source) != manifest["source_sha256"]: errors.append("源数据 SHA256 不一致")
    rows, fields, _ = read_csv(source)
    expected, info = build_plot_data(manifest["spec"], rows, fields)
    export = manifest["export"]
    spec = manifest["spec"]
    scenes, expected_axes, expected_colors, expected_shapes, font_px = render_scene(
        spec, expected, export["width_px"], export["height_px"], export["dpi"])
    if expected_axes != manifest["axes"]: errors.append("轴类型/范围/刻度与重绘不一致")
    if expected_colors != manifest["colors"] or expected_shapes != manifest["shapes"]: errors.append("颜色/形状映射与重绘不一致")
    with tempfile.TemporaryDirectory(prefix="visual-audit-") as tmp:
        expected_svg = os.path.join(tmp, "expected.svg")
        expected_png = os.path.join(tmp, "expected.png")
        write_svg(expected_svg, scenes, export["width_px"], export["height_px"],
                  export["width_mm"], export["height_mm"], spec.get("title", manifest["id"]), manifest["caption"])
        raster, _ = draw_raster(scenes, export["width_px"], export["height_px"], manifest["png_label_map"])
        write_png(expected_png, raster, export["dpi"])
        if sha256(expected_svg) != manifest["svg_sha256"]: errors.append("SVG 视觉元素与源数据/规格重绘不一致")
        if sha256(expected_png) != manifest["png_sha256"]: errors.append("PNG 视觉元素与源数据/规格重绘不一致")
    data_path = manifest["figure_data"]
    if sha256(data_path) != manifest["figure_data_sha256"]: errors.append("figure-data 文件哈希不一致")
    with open(data_path, encoding="utf-8", newline="") as f:
        actual = list(csv.DictReader(f))
    if len(actual) != len(expected): errors.append({"error":"绘图数据行数不一致","actual":len(actual),"expected":len(expected)})
    for i, (a,e) in enumerate(zip(actual, expected)):
        checks += 1
        if set(a) != {k for k in e}: errors.append({"row":i,"error":"绘图数据字段不一致"}); continue
        for key,want in e.items():
            got = a[key]
            if isinstance(want,(int,float)) and not isinstance(want,bool):
                try: matches = almost(number(got),want)
                except ValueError: matches = False
            else: matches = got == csv_value(want)
            if not matches: errors.append({"row":i,"field":key,"error":"图源数据不一致","actual":got,"expected":csv_value(want)})
    for key,hashkey in (("svg","svg_sha256"),("png","png_sha256"),("caption_path","caption_sha256")):
        if not os.path.isfile(manifest[key]) or sha256(manifest[key]) != manifest[hashkey]: errors.append("%s 缺失或哈希不一致" % key)
    with open(manifest["caption_path"],encoding="utf-8") as f: caption = f.read().strip()
    if caption != manifest["caption"]: errors.append("图注文件与 manifest 不一致")
    if "n=" not in caption or ("误差线=" in caption) != bool(manifest.get("error_definition")): errors.append("图注缺 n 或误差线定义")
    if info != manifest["data_quality"]: errors.append("缺失排除/绘图行数记录与重算不一致")
    # 轴、刻度、单位、映射
    axes = manifest["axes"]
    for axis in ("x","y"):
        label = axis_label(manifest["spec"].get(axis,{}))
        if axes[axis]["label"] != label: errors.append("%s 轴标目/单位与 spec 不一致" % axis)
    numeric_ticks = [float(t) for t in axes["y"]["ticks"]]
    if any(t < axes["y"]["domain"][0]-1e-8 or t > axes["y"]["domain"][1]+1e-8 for t in numeric_ticks): errors.append("y 刻度超出声明范围")
    if manifest["chart"] in {"bar","hist"} and axes["y"]["domain"][0] > 0: errors.append("柱/直方图基线非零")
    for group,color in manifest["colors"].items():
        if not re.match(r"^#[0-9A-F]{6}$",color): errors.append("颜色非法")
        if group not in manifest["shapes"]: errors.append("组缺第二重形状编码")
    conflicts = color_conflicts(manifest["colors"])
    # 每一组均有形状编码，颜色近似只作为可读性 issues，不把色觉检查隐藏。
    if conflicts: errors.append({"error":"颜色在灰度/色觉模拟下可能不可分","conflicts":conflicts})
    png = read_png_metadata(manifest["png"]); export = manifest["export"]
    if png.get("dpi",0) < 299.99 or export["dpi"] < 300: errors.append("PNG 实际 DPI<300")
    if png.get("width_px") != export["width_px"] or png.get("height_px") != export["height_px"]: errors.append("PNG 像素尺寸与 manifest 不一致")
    if export["width_mm"] != 85 and export["width_mm"] > 180: errors.append("画布不符合单/双栏宽度")
    if export["min_font_pt"] < 7: errors.append("字号低于 7pt")
    with open(manifest["svg"],encoding="utf-8") as f: svg = f.read()
    if "<title" not in svg or "<desc" not in svg or "viewBox" not in svg: errors.append("SVG 缺标题/描述/viewBox")
    if manifest.get("warnings"): errors.append("render 尚有字体/导出告警")
    return errors, checks, {"source_sha256":manifest["source_sha256"],"png":png,"color_conflicts":conflicts,
                            "visual_coverage":manifest.get("visual_coverage",{})}


def cmd_audit(result_path):
    result = load_json(result_path); errors = result_schema_errors(result)
    checked, reports = 0, []
    for fig in result.get("figures", []):
        try:
            e,n,report = audit_manifest(fig["manifest"],fig["manifest_sha256"])
            checked += n
            if fig["source_sha256"] != report["source_sha256"]: e.append("result 图源哈希与 manifest 不一致")
            if fig["caption"] != load_json(fig["manifest"])["caption"]: e.append("result 图注与 manifest 不一致")
            for key,mkey in (("svg","svg"),("png","png"),("figure_data","figure_data")):
                if os.path.realpath(fig[key]) != os.path.realpath(load_json(fig["manifest"])[mkey]): e.append("result %s 路径与 manifest 不一致" % key)
            reports.append(dict(report,id=fig["id"],errors=e)); errors.extend(dict(x,figure=fig["id"]) if isinstance(x,dict) else {"figure":fig["id"],"error":x} for x in e)
        except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc: errors.append({"figure":fig.get("id"),"error":str(exc)})
    if result.get("lineage",{}).get("source_sha256") and result.get("figures"):
        if result["lineage"]["source_sha256"] != result["figures"][0]["source_sha256"]: errors.append("lineage 与 figure 源哈希不一致")
    return emit({"ok":not errors,"checked_plot_records":checked,"figures":reports,"errors":errors},0 if not errors else 1)


def parser():
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True)
    for name in ("recommend","render"):
        x=sub.add_parser(name); x.add_argument("spec")
    for name in ("schema","audit"):
        x=sub.add_parser(name); x.add_argument("result")
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    if args.command == "recommend": return cmd_recommend(args.spec)
    if args.command == "render": return cmd_render(args.spec)
    if args.command == "schema": return cmd_schema(args.result)
    return cmd_audit(args.result)


if __name__ == "__main__":
    try: sys.exit(main())
    except (OSError,ValueError,KeyError,csv.Error,json.JSONDecodeError) as exc:
        sys.exit(emit({"ok":False,"error":str(exc),"error_type":type(exc).__name__},1))
