#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pdf_text.py - 纯标准库 PDF 文本层抽取（兜底工具，不依赖任何第三方库）。

用法: python3 pdf_text.py <input.pdf> <output.txt>
输出带 === PAGE n (pdf_obj m) === 页标记的文本。
能力边界（须在 result.json 的 uncertainty 中如实反映）：仅处理 /FlateDecode
或未压缩内容流，不支持对象流与 CID/ToUnicode 字体映射（可能出乱码）；
扫描件无文本层则输出为空。乱码/空输出 = extraction_failed 信号，禁止编造。
页序按页面对象号升序近似。退出码: 0 正常; 2 无可用文本层; 1 其他错误。
"""
import re
import sys
import zlib

OBJ_RE = re.compile(rb"(\d+)\s+\d+\s+obj\b")
PAGE_RE = re.compile(rb"/Type\s*/Page\b")
PAGES_RE = re.compile(rb"/Type\s*/Pages\b")
CONT_ONE_RE = re.compile(rb"/Contents\s+(\d+)\s+\d+\s+R")
CONT_ARR_RE = re.compile(rb"/Contents\s*\[((?:\s*\d+\s+\d+\s+R)+)\]", re.S)
REF_RE = re.compile(rb"(\d+)\s+\d+\s+R")
STREAM_RE = re.compile(rb"stream\r?\n")

_ESC = {110: 10, 114: 13, 116: 9, 98: 8, 102: 12, 40: 40, 41: 41, 92: 92}


def find_objects(data):
    objs = {}
    for m in OBJ_RE.finditer(data):
        end = data.find(b"endobj", m.end())
        if end != -1:
            objs[int(m.group(1))] = data[m.end():end]
    return objs


def get_stream(body):
    sm = STREAM_RE.search(body)
    if not sm:
        return None
    em = body.find(b"endstream", sm.end())
    if em == -1:
        return None
    raw = body[sm.end():em].rstrip(b"\r\n")
    if b"FlateDecode" in body:
        for cand in (raw, raw[:-1], raw[:-2]):
            try:
                return zlib.decompress(cand)
            except Exception:
                pass
        try:
            return zlib.decompressobj().decompress(raw)
        except Exception:
            return None
    return raw


def decode_literal(buf):
    out = bytearray()
    i, n = 0, len(buf)
    while i < n:
        c = buf[i]
        if c == 92 and i + 1 < n:  # backslash
            nx = buf[i + 1]
            if nx in _ESC:
                out.append(_ESC[nx]); i += 2
            elif 48 <= nx <= 55:  # octal
                j = i + 1; digs = []
                while j < n and len(digs) < 3 and 48 <= buf[j] <= 55:
                    digs.append(buf[j]); j += 1
                out.append(int(bytes(digs), 8) & 0xFF); i = j
            elif nx in (10, 13):  # line continuation
                i += 2
            else:
                out.append(nx); i += 2
        else:
            out.append(c); i += 1
    return bytes(out)


def decode_bytes(raw):
    """latin-1；0 字节占比高则试 UTF-16BE。"""
    if raw and raw.count(0) * 2 > len(raw):
        try:
            return raw.decode("utf-16-be", errors="ignore")
        except Exception:
            pass
    return raw.decode("latin-1")


def extract_text(stream):
    out = []
    i, n = 0, len(stream)
    while i < n:
        c = stream[i]
        if c == 37:  # % 注释
            j = stream.find(b"\n", i)
            i = n if j == -1 else j + 1
        elif c == 40:  # 字面字符串
            depth, j, buf = 1, i + 1, bytearray()
            while j < n and depth:
                ch = stream[j]
                if ch == 92:
                    buf.append(ch)
                    if j + 1 < n:
                        buf.append(stream[j + 1]); j += 2
                    else:
                        j += 1
                elif ch == 40:
                    depth += 1; buf.append(ch); j += 1
                elif ch == 41:
                    depth -= 1
                    if depth:
                        buf.append(ch)
                    j += 1
                else:
                    buf.append(ch); j += 1
            out.append(decode_bytes(decode_literal(bytes(buf))))
            i = j
        elif c == 60 and stream[i:i + 2] != b"<<":  # 十六进制串
            j = stream.find(b">", i)
            if j == -1:
                break
            hexs = re.sub(rb"\s+", b"", stream[i + 1:j])
            try:
                out.append(decode_bytes(bytes.fromhex(hexs.decode("ascii"))))
            except Exception:
                pass
            i = j + 1
        elif c == 84 and stream[i:i + 2] in (b"Td", b"TD", b"T*", b"Tm"):  # 换行
            out.append("\n"); i += 2
        elif c == 39:  # ' = 换行+显示
            out.append("\n"); i += 1
        else:
            i += 1
    return "".join(out)


def page_list(objs):
    pages = []
    for num in sorted(objs):
        body = objs[num]
        if b"/Type" not in body or not PAGE_RE.search(body) or PAGES_RE.search(body):
            continue
        contents = []
        m = CONT_ONE_RE.search(body)
        if m:
            contents = [int(m.group(1))]
        else:
            m = CONT_ARR_RE.search(body)
            if m:
                contents = [int(x) for x in REF_RE.findall(m.group(1))]
        pages.append((num, contents))
    return pages


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: pdf_text.py <input.pdf> <output.txt>\n")
        return 1
    try:
        data = open(sys.argv[1], "rb").read()
    except OSError as e:
        sys.stderr.write("cannot read pdf: %s\n" % e)
        return 1
    objs = find_objects(data)
    pages = page_list(objs)
    chunks, total = [], 0
    if pages:
        for idx, (pnum, contents) in enumerate(pages, 1):
            text = "".join(extract_text(s) for c in contents
                           for s in [get_stream(objs.get(c, b""))] if s)
            total += len(text.strip())
            chunks.append("=== PAGE %d (pdf_obj %d) ===\n%s" % (idx, pnum, text.strip()))
    else:  # 无页树可解析：退化为流序拼接，页码未知
        for num in sorted(objs):
            s = get_stream(objs[num])
            if s and (b"Tj" in s or b"TJ" in s):
                t = extract_text(s)
                total += len(t.strip())
                chunks.append("=== STREAM obj %d (page unknown) ===\n%s" % (num, t.strip()))
    if total < 20:
        sys.stderr.write("NO_TEXT_LAYER: 疑似扫描件/CID 字体，标 extraction_failed\n")
        open(sys.argv[2], "w", encoding="utf-8").write("\n\n".join(chunks))
        return 2
    open(sys.argv[2], "w", encoding="utf-8").write("\n\n".join(chunks))
    sys.stderr.write("pages=%d chars=%d -> %s\n" % (len(chunks), total, sys.argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
