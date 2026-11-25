#!/usr/bin/env python3
"""科研资料管理工具（纯 Python 标准库；所有日期均由调用者/系统如实生成）。

  inventory <dir> [--output inventory.json]
      清点文件、权限、完整 sha256、内容重复组、候选版本链和异常。
  checkmap <dir> --spec spec.json
      按目录正则、manifest_csv 和 required_meta 核验落库规范。
  mapmeta <input.csv> --map map.json --output manifest.csv
      批量字段映射，保留每个字段的列/常量/缺失出处；缺必填字段即失败。
  diff <old> <new> [--old-version V] [--new-version V]
      比较内容哈希；UTF-8 文本给 unified diff，二进制只报告哈希/大小差异。
  verify <dir> --manifest manifest.json|csv
      逐文件复核路径、sha256、权限、来源定位、版本替代关系和未登记文件。
  archive <dir> --manifest manifest.json|csv --output archive.zip [--force]
      verify 全过后原子生成 ZIP，内嵌归档清单并回读校验 CRC；失败不留半截包。
  schema <result.json>
      校验结构化交付、可复跑 run 字段、完整哈希、版本和异常恢复记录。
"""
import csv
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import zipfile

TOOL_VERSION = "2.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VER_TOKENS = re.compile(
    r"(?i)(?:[_\-\s]?(?:v|ver|rev|final|draft|copy)\d*|[_\-\s]?\(\d+\)|[_\-\s]?\d{8})"
)
MANIFEST_REQUIRED = ("path", "sha256", "size", "source", "source_locator", "version",
                     "collected_at", "project", "permissions")


def _emit(data, output=None):
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        parent = os.path.dirname(os.path.abspath(output))
        os.makedirs(parent, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(json.dumps({"ok": data.get("ok", False), "output": output,
                          "report_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()},
                         ensure_ascii=False))
    else:
        print(text, end="")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _safe_rel(value):
    if not isinstance(value, str) or not value or value.startswith(("/", "\\")):
        return False
    normalized = value.replace("\\", "/")
    return normalized == value and all(part not in ("", ".", "..") for part in value.split("/"))


def _mode(value):
    return "%04o" % stat.S_IMODE(value)


def _inventory(root):
    files, by_hash, anomalies = [], {}, []
    empty_directories = []
    if not os.path.isdir(root):
        return {"ok": False, "error": "目录不存在或不是目录", "root": root}
    root = os.path.abspath(root)

    def onerror(exc):
        anomalies.append({"path": getattr(exc, "filename", root), "issue": "directory_unreadable",
                          "detail": str(exc), "recovery": "补充遍历权限后重跑 inventory"})

    for current, dirs, names in os.walk(root, onerror=onerror):
        kept_dirs = []
        for name in sorted(dirs):
            path = os.path.join(current, name)
            if os.path.islink(path):
                anomalies.append({"path": _rel(path, root), "issue": "directory_symlink",
                                  "recovery": "登记目标并改用实体目录，不归档软链"})
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        if not dirs and not names:
            empty_directories.append(_rel(current, root))
        for name in sorted(names):
            path = os.path.join(current, name)
            rel = _rel(path, root)
            if os.path.islink(path):
                anomalies.append({"path": rel, "issue": "file_symlink",
                                  "recovery": "登记目标并改用实体文件，不归档软链"})
                continue
            try:
                info = os.stat(path)
                digest = _sha(path)
            except (OSError, ValueError) as exc:
                anomalies.append({"path": rel, "issue": "file_unreadable", "detail": str(exc),
                                  "recovery": "保留原件；授权或重新采集后重算哈希"})
                continue
            row = {"path": rel, "size": info.st_size, "ext": os.path.splitext(name)[1].lower(),
                   "sha256": digest, "empty": info.st_size == 0, "permissions": _mode(info.st_mode),
                   "mtime_ns": info.st_mtime_ns, "source": os.path.join(root, rel)}
            files.append(row)
            by_hash.setdefault(digest, []).append(row)

    duplicates = [{"sha256": digest, "files": sorted(row["path"] for row in rows),
                   "size": rows[0]["size"]}
                  for digest, rows in sorted(by_hash.items()) if len(rows) > 1]
    chains = {}
    for row in files:
        stem = os.path.splitext(os.path.basename(row["path"]))[0]
        base = re.sub(r"\s+", " ", VER_TOKENS.sub("", stem)).strip().lower()
        chains.setdefault(base, []).append(row)
    versions = []
    for base, rows in sorted(chains.items()):
        distinct = {row["sha256"]: row for row in rows}
        if len(distinct) < 2:
            continue  # 同 base 同内容只是重复，不能误报为版本。
        ordered = sorted(distinct.values(), key=lambda r: (r["mtime_ns"], r["path"]))
        versions.append({"base": base, "status": "candidate_requires_confirmation",
                         "current_candidate": ordered[-1]["path"],
                         "files": [{"path": r["path"], "sha256": r["sha256"],
                                    "mtime_ns": r["mtime_ns"]} for r in ordered],
                         "basis": ["normalized_base", "distinct_sha256", "mtime_ns"],
                         "caution": "候选 current 仅按时间排序；须结合任务规则/版本说明确认"})
    result = {"ok": not anomalies, "tool_version": TOOL_VERSION, "root": root,
              "n_files": len(files), "total_bytes": sum(row["size"] for row in files),
              "by_ext": {ext: sum(1 for row in files if row["ext"] == ext)
                         for ext in sorted({row["ext"] for row in files})},
              "files": sorted(files, key=lambda row: row["path"]),
              "duplicate_groups": duplicates, "version_chains": versions,
              "empty_files": [row["path"] for row in files if row["empty"]],
              "empty_directories": empty_directories, "anomalies": anomalies}
    canonical = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["inventory_sha256"] = hashlib.sha256(canonical).hexdigest()
    return result


def cmd_inventory(root, output=None):
    result = _inventory(root)
    _emit(result, output)
    return 0 if result.get("ok") else 1


def cmd_checkmap(root, spec_path):
    try:
        with open(spec_path, encoding="utf-8") as fh:
            spec = json.load(fh)
        patterns = [re.compile(pattern) for pattern in spec.get("path_patterns", [])]
    except (OSError, ValueError, re.error) as exc:
        _emit({"ok": False, "error": "spec 无法读取或解析", "detail": str(exc)})
        return 2
    required = spec.get("required_meta", [])
    manifest = {}
    mf = spec.get("manifest_csv")
    if mf:
        if not os.path.isabs(mf):
            mf = os.path.join(os.path.dirname(os.path.abspath(spec_path)), mf)
        if os.path.isfile(mf):
            with open(mf, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    manifest[row.get("path", "")] = row
        elif required:
            _emit({"ok": False, "error": "manifest_csv 不存在", "manifest_csv": mf})
            return 1
    path_violations, missing_meta, missing = [], [], []
    for current, _, names in os.walk(root):
        for name in names:
            rel = _rel(os.path.join(current, name), root)
            if patterns and not any(pattern.fullmatch(rel) for pattern in patterns):
                path_violations.append(rel)
            row = manifest.get(rel)
            if required:
                if row is None:
                    missing.append(rel)
                else:
                    for key in required:
                        if not str(row.get(key, "")).strip():
                            missing_meta.append({"path": rel, "missing_meta": key})
    result = {"ok": not path_violations and not missing_meta and not missing,
              "path_violations": sorted(path_violations), "missing_meta": missing_meta,
              "no_manifest_row": sorted(missing), "checked_patterns": len(patterns),
              "required_meta": required}
    _emit(result)
    return 0 if result["ok"] else 1


def cmd_mapmeta(input_csv, map_path, output):
    try:
        with open(map_path, encoding="utf-8") as fh:
            config = json.load(fh)
        with open(input_csv, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            original_fields = reader.fieldnames or []
    except (OSError, ValueError, csv.Error) as exc:
        _emit({"ok": False, "error": "输入 CSV 或映射 JSON 无法读取", "detail": str(exc)})
        return 2
    column_map = config.get("column_map", {})
    constants = config.get("constants", {})
    required = config.get("required", list(MANIFEST_REQUIRED))
    allow_unknown = set(config.get("allow_unknown", []))
    fields = list(config.get("output_fields", MANIFEST_REQUIRED))
    for extra in ("mapping_version", "field_provenance"):
        if extra not in fields:
            fields.append(extra)
    output_rows, anomalies = [], []
    seen = {}
    for line_no, source_row in enumerate(rows, 2):
        target, provenance = {}, {}
        for field in fields:
            if field in ("mapping_version", "field_provenance"):
                continue
            if field in column_map:
                source_column = column_map[field]
                value = source_row.get(source_column, "") if source_column in original_fields else ""
                provenance[field] = {"kind": "column", "column": source_column,
                                     "input": os.path.basename(input_csv), "line": line_no}
            elif field in constants:
                value = constants[field]
                provenance[field] = {"kind": "constant", "mapping": os.path.basename(map_path),
                                     "mapping_version": str(config.get("mapping_version", ""))}
            else:
                value = source_row.get(field, "")
                provenance[field] = {"kind": "column", "column": field,
                                     "input": os.path.basename(input_csv), "line": line_no}
            value = "" if value is None else str(value).strip()
            if field in required and not value:
                if field in allow_unknown:
                    value = "unknown"
                    provenance[field] = {"kind": "unresolved", "input": os.path.basename(input_csv),
                                         "line": line_no, "reason": "源字段为空且映射允许 unknown"}
                    anomalies.append({"line": line_no, "path": target.get("path", ""),
                                      "issue": "metadata_unknown", "field": field,
                                      "recovery": "向资料提供方补录；不得推测填充"})
                else:
                    anomalies.append({"line": line_no, "path": target.get("path", ""),
                                      "issue": "required_metadata_missing", "field": field,
                                      "recovery": "补齐源列/常量映射后重跑 mapmeta"})
            target[field] = value
        target["mapping_version"] = str(config.get("mapping_version", ""))
        target["field_provenance"] = json.dumps(provenance, ensure_ascii=False, sort_keys=True)
        path = target.get("path", "")
        if path:
            if path in seen:
                anomalies.append({"line": line_no, "path": path, "issue": "duplicate_manifest_path",
                                  "first_line": seen[path], "recovery": "解决重名冲突，不覆盖前行"})
            else:
                seen[path] = line_no
        output_rows.append(target)
    try:
        parent = os.path.dirname(os.path.abspath(output))
        os.makedirs(parent, exist_ok=True)
        with open(output, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(output_rows)
    except OSError as exc:
        _emit({"ok": False, "error": "manifest 写入失败", "detail": str(exc), "anomalies": anomalies})
        return 2
    fatal = [a for a in anomalies if a["issue"] != "metadata_unknown"]
    result = {"ok": not fatal, "row_count": len(output_rows), "output": output,
              "mapping_version": str(config.get("mapping_version", "")),
              "anomaly_count": len(anomalies), "anomalies": anomalies,
              "status": "issues" if anomalies and not fatal else ("failed" if fatal else "pass")}
    _emit(result)
    return 0 if result["ok"] else 1


def cmd_diff(old, new, old_version=None, new_version=None):
    try:
        old_info, new_info = os.stat(old), os.stat(new)
        old_sha, new_sha = _sha(old), _sha(new)
    except OSError as exc:
        _emit({"ok": False, "error": "版本文件不可读", "detail": str(exc)})
        return 2
    result = {"ok": True, "identical": old_sha == new_sha,
              "old": {"path": old, "sha256": old_sha, "size": old_info.st_size,
                      "mtime_ns": old_info.st_mtime_ns, "version": old_version},
              "new": {"path": new, "sha256": new_sha, "size": new_info.st_size,
                      "mtime_ns": new_info.st_mtime_ns, "version": new_version},
              "relation": "duplicate" if old_sha == new_sha else "content_differs"}
    if not result["identical"]:
        try:
            with open(old, encoding="utf-8") as fh:
                old_lines = fh.readlines()
            with open(new, encoding="utf-8") as fh:
                new_lines = fh.readlines()
            changes = list(difflib.unified_diff(old_lines, new_lines, fromfile=old, tofile=new))
            result.update({"kind": "text", "diff_lines": changes,
                           "added_lines": sum(1 for line in changes if line.startswith("+") and not line.startswith("+++")),
                           "deleted_lines": sum(1 for line in changes if line.startswith("-") and not line.startswith("---"))})
        except UnicodeDecodeError:
            result.update({"kind": "binary_or_non_utf8", "diff_lines": [],
                           "note": "内容哈希不同；二进制差异需原格式工具复核，不伪造逐行差异"})
    else:
        result.update({"kind": "identical_content", "diff_lines": [], "added_lines": 0, "deleted_lines": 0})
    _emit(result)
    return 0


def _load_manifest(path):
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("manifest") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("manifest 必须是数组或含 manifest 数组的对象")
    return rows


def _verify(root, manifest_path):
    errors, hash_mismatches, permission_mismatches, source_errors, version_errors = [], [], [], [], []
    try:
        rows = _load_manifest(manifest_path)
    except (OSError, ValueError, csv.Error) as exc:
        return {"ok": False, "errors": [{"issue": "manifest_unreadable", "detail": str(exc)}]}
    root = os.path.abspath(root)
    expected = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append({"issue": "manifest_row_not_object", "row": index})
            continue
        path = row.get("path", "")
        if not _safe_rel(path):
            errors.append({"issue": "unsafe_or_empty_path", "row": index, "path": path})
            continue
        if path in expected:
            errors.append({"issue": "duplicate_manifest_path", "path": path})
            continue
        expected[path] = row
        for field in ("sha256", "source", "source_locator", "version", "permissions"):
            if not str(row.get(field, "")).strip():
                errors.append({"issue": "missing_manifest_field", "path": path, "field": field})
        digest = str(row.get("sha256", "")).lower()
        if not SHA256_RE.fullmatch(digest):
            errors.append({"issue": "invalid_sha256", "path": path})
        absolute = os.path.abspath(os.path.join(root, *path.split("/")))
        if os.path.commonpath([root, absolute]) != root:
            errors.append({"issue": "path_escapes_root", "path": path})
            continue
        if not os.path.isfile(absolute) or os.path.islink(absolute):
            errors.append({"issue": "manifest_file_missing_or_symlink", "path": path,
                           "recovery": "从 source_locator 恢复后重跑 verify"})
            continue
        try:
            actual = _sha(absolute)
            actual_mode = _mode(os.stat(absolute).st_mode)
        except OSError as exc:
            errors.append({"issue": "file_unreadable", "path": path, "detail": str(exc),
                           "recovery": "授权后重跑；不计为通过"})
            continue
        if SHA256_RE.fullmatch(digest) and actual != digest:
            hash_mismatches.append({"path": path, "expected_sha256": digest, "actual_sha256": actual,
                                    "status": "corrupt", "recovery": "保留原件，从 source_locator 重新采集"})
        expected_mode = str(row.get("permissions", "")).strip()
        if re.fullmatch(r"(?:0o)?[0-7]{3,4}", expected_mode):
            normalized = expected_mode[2:] if expected_mode.startswith("0o") else expected_mode
            normalized = normalized.zfill(4)
            if actual_mode != normalized:
                permission_mismatches.append({"path": path, "expected": normalized, "actual": actual_mode,
                                              "recovery": "按交接约定 chmod 后复跑，或记录获批的权限差异"})
        elif expected_mode:
            errors.append({"issue": "invalid_permissions", "path": path, "value": expected_mode})
        if row.get("size") not in (None, ""):
            try:
                expected_size = int(row["size"])
                if expected_size != os.path.getsize(absolute):
                    errors.append({"issue": "size_mismatch", "path": path, "expected": expected_size,
                                   "actual": os.path.getsize(absolute)})
            except (ValueError, OSError):
                errors.append({"issue": "invalid_size", "path": path, "value": row.get("size")})
    actual_files = set()
    for current, dirs, names in os.walk(root):
        dirs[:] = [name for name in dirs if not os.path.islink(os.path.join(current, name))]
        for name in names:
            path = os.path.join(current, name)
            if not os.path.islink(path):
                actual_files.add(_rel(path, root))
    unlisted = sorted(actual_files - set(expected))
    for path in unlisted:
        errors.append({"issue": "unlisted_file", "path": path, "recovery": "补 manifest 行后重跑 verify"})
    for row in rows:
        if not isinstance(row, dict):
            continue
        path, old = row.get("path"), row.get("supersedes")
        if old:
            if old not in expected:
                version_errors.append({"path": path, "issue": "supersedes_not_in_manifest", "supersedes": old})
            elif old == path:
                version_errors.append({"path": path, "issue": "version_self_cycle"})
            elif row.get("sha256") == expected[old].get("sha256"):
                version_errors.append({"path": path, "issue": "supersedes_identical_content", "supersedes": old,
                                       "recovery": "改记 duplicate_of，不得把相同内容伪装成新版本"})
    errors.extend(hash_mismatches)
    errors.extend(permission_mismatches)
    errors.extend(source_errors)
    errors.extend(version_errors)
    return {"ok": not errors, "root": root, "manifest": os.path.abspath(manifest_path),
            "manifest_sha256": _sha(manifest_path), "checked_files": len(expected),
            "unlisted_files": unlisted, "hash_mismatches": hash_mismatches,
            "permission_mismatches": permission_mismatches, "source_errors": source_errors,
            "version_errors": version_errors, "errors": errors,
            "status": "pass" if not errors else "issues"}


def cmd_verify(root, manifest_path):
    result = _verify(root, manifest_path)
    _emit(result)
    return 0 if result.get("ok") else 1


def cmd_archive(root, manifest_path, output, force=False):
    result = _verify(root, manifest_path)
    if not result.get("ok"):
        _emit({"ok": False, "error": "verify 未通过，拒绝生成归档包", "verification": result})
        return 1
    root, output = os.path.abspath(root), os.path.abspath(output)
    if os.path.commonpath([root, output]) == root:
        _emit({"ok": False, "error": "归档包必须输出到资料根目录之外，避免自包含"})
        return 2
    if os.path.exists(output) and not force:
        _emit({"ok": False, "error": "输出已存在；确认后使用 --force，禁止静默覆盖", "output": output})
        return 1
    rows = _load_manifest(manifest_path)
    archive_manifest = {"archive_format": "zip", "tool_version": TOOL_VERSION,
                        "created_at": _utc_now(), "source_manifest_sha256": _sha(manifest_path),
                        "root_name": os.path.basename(root), "file_count": len(rows), "files": rows}
    temp_path = None
    try:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".archive-", suffix=".zip", dir=os.path.dirname(output))
        os.close(fd)
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for row in sorted(rows, key=lambda item: item["path"]):
                path = row["path"]
                zf.write(os.path.join(root, *path.split("/")), arcname="library/" + path)
            payload = json.dumps(archive_manifest, ensure_ascii=False, indent=2, sort_keys=True)
            zf.writestr("archive_manifest.json", payload.encode("utf-8"))
        with zipfile.ZipFile(temp_path, "r") as zf:
            bad = zf.testzip()
            if bad:
                raise OSError("ZIP CRC 校验失败: " + bad)
            names = zf.namelist()
        os.replace(temp_path, output)
        temp_path = None
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
        _emit({"ok": False, "error": "归档失败，临时包已清理", "detail": str(exc)})
        return 2
    _emit({"ok": True, "archive": output, "archive_sha256": _sha(output),
           "file_count": len(rows), "zip_entries": len(names), "crc_verified": True,
           "manifest_sha256": archive_manifest["source_manifest_sha256"]})
    return 0


def cmd_schema(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        _emit({"ok": False, "errors": ["result.json 无法读取或解析: %s" % exc]})
        return 2
    if not isinstance(data, dict):
        _emit({"ok": False, "errors": ["顶层必须是对象"]})
        return 1
    errors = []
    for key in ("case_id", "status", "directory_tree", "manifest", "dedup", "versions",
                "operations", "recovery", "run", "gain", "unchecked", "sources", "uncertainty", "change_log"):
        if key not in data:
            errors.append("缺顶层字段 %s" % key)
    if data.get("status") not in {"pass", "issues", "partial", "failed"}:
        errors.append("status 非法")
    manifest = data.get("manifest", [])
    if not isinstance(manifest, list):
        errors.append("manifest 必须是数组")
        manifest = []
    paths = set()
    for index, row in enumerate(manifest):
        if not isinstance(row, dict):
            errors.append("manifest[%d] 必须是对象" % index)
            continue
        for key in MANIFEST_REQUIRED:
            if key not in row or row[key] in (None, ""):
                errors.append("manifest[%d] 缺或空 %s" % (index, key))
        if not SHA256_RE.fullmatch(str(row.get("sha256", "")).lower()):
            errors.append("manifest[%d] sha256 必须为 64 位小写十六进制" % index)
        if not _safe_rel(row.get("path")):
            errors.append("manifest[%d] path 必须是安全的根内相对路径" % index)
        elif row["path"] in paths:
            errors.append("manifest[%d] path 重复" % index)
        else:
            paths.add(row["path"])
    operations = data.get("operations", [])
    if not isinstance(operations, list):
        errors.append("operations 必须是数组")
        operations = []
    for index, row in enumerate(operations):
        if not isinstance(row, dict):
            errors.append("operations[%d] 必须是对象" % index)
            continue
        for key in ("action", "src", "dst", "result", "operator", "timestamp"):
            if key not in row:
                errors.append("operations[%d] 缺 %s" % (index, key))
    recovery = data.get("recovery", [])
    if not isinstance(recovery, list):
        errors.append("recovery 必须是数组")
        recovery = []
    for index, row in enumerate(recovery):
        if not isinstance(row, dict):
            errors.append("recovery[%d] 必须是对象" % index)
            continue
        for key in ("type", "path", "status", "action", "recovery"):
            if key not in row:
                errors.append("recovery[%d] 缺 %s" % (index, key))
        if row.get("status") not in {"resolved", "open", "blocked"}:
            errors.append("recovery[%d] status 非法" % index)
        if data.get("status") == "pass" and row.get("status") != "resolved":
            errors.append("status=pass 但 recovery[%d] 未解决" % index)
    run = data.get("run")
    if not isinstance(run, dict):
        errors.append("run 必须是对象")
    else:
        for key in ("tool_version", "commands", "input_root", "input_inventory_sha256", "started_at", "completed_at"):
            if key not in run or run[key] in (None, "", []):
                errors.append("run 缺或空 %s" % key)
        if not SHA256_RE.fullmatch(str(run.get("input_inventory_sha256", "")).lower()):
            errors.append("run.input_inventory_sha256 必须是完整 sha256")
    versions = data.get("versions", {})
    if not isinstance(versions, dict):
        errors.append("versions 必须是对象")
    else:
        for base, chain in versions.items():
            if not isinstance(chain, dict):
                errors.append("versions[%s] 必须是对象" % base)
                continue
            for key in ("current", "history", "basis"):
                if key not in chain:
                    errors.append("versions[%s] 缺 %s" % (base, key))
            history = chain.get("history")
            if not isinstance(history, list):
                errors.append("versions[%s].history 必须是数组" % base)
            elif chain.get("current") in history:
                errors.append("versions[%s] current 不能同时在 history" % base)
    dedup = data.get("dedup", {})
    if not isinstance(dedup, dict) or not isinstance(dedup.get("groups"), list):
        errors.append("dedup.groups 必须是数组")
    else:
        for index, group in enumerate(dedup["groups"]):
            if not isinstance(group, dict) or not SHA256_RE.fullmatch(str(group.get("sha256", "")).lower()):
                errors.append("dedup.groups[%d] 缺完整 sha256" % index)
            if not isinstance(group, dict) or not isinstance(group.get("files"), list) or len(group["files"]) < 2:
                errors.append("dedup.groups[%d].files 至少两个路径" % index)
            elif group.get("keep") not in group["files"]:
                errors.append("dedup.groups[%d].keep 必须属于 files" % index)
    if errors:
        _emit({"ok": False, "errors": errors})
        return 1
    _emit({"ok": True, "manifest": len(manifest), "operations": len(operations),
           "recovery": len(recovery), "tool_version": run["tool_version"]})
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    command, args = argv[0], argv[1:]
    try:
        if command == "inventory" and len(args) >= 1:
            output = args[args.index("--output") + 1] if "--output" in args else None
            return cmd_inventory(args[0], output)
        if command == "checkmap" and len(args) >= 3 and "--spec" in args:
            return cmd_checkmap(args[0], args[args.index("--spec") + 1])
        if command == "mapmeta" and "--map" in args and "--output" in args and args:
            return cmd_mapmeta(args[0], args[args.index("--map") + 1], args[args.index("--output") + 1])
        if command == "diff" and len(args) >= 2:
            return cmd_diff(args[0], args[1],
                            args[args.index("--old-version") + 1] if "--old-version" in args else None,
                            args[args.index("--new-version") + 1] if "--new-version" in args else None)
        if command == "verify" and len(args) >= 3 and "--manifest" in args:
            return cmd_verify(args[0], args[args.index("--manifest") + 1])
        if command == "archive" and len(args) >= 5 and "--manifest" in args and "--output" in args:
            return cmd_archive(args[0], args[args.index("--manifest") + 1],
                               args[args.index("--output") + 1], "--force" in args)
        if command == "schema" and len(args) == 1:
            return cmd_schema(args[0])
    except (IndexError, OSError, ValueError) as exc:
        _emit({"ok": False, "error": "参数或运行错误", "detail": str(exc)})
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
