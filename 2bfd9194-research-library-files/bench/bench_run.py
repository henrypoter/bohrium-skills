#!/usr/bin/env python3
"""合成变异 bench：正常批次零误杀；每种关键损坏/缺字段变异必须命中。"""
import csv
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.abspath(os.path.join(HERE, "..", "scripts", "file_tool.py"))
TMP = tempfile.mkdtemp(prefix="file-tool-bench-")
checks = []


def put(path, text="", binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if binary:
        with open(path, "wb") as fh:
            fh.write(text)
    else:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return path


def dump(path, data):
    return put(path, json.dumps(data, ensure_ascii=False, indent=2))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def run(*args):
    proc = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    try:
        return proc.returncode, json.loads(proc.stdout)
    except Exception:
        return proc.returncode, {"raw": proc.stdout[:500], "stderr": proc.stderr[:500]}


def add(name, condition, detail=""):
    checks.append((name, bool(condition), detail))


# inventory：同内容不误报版本，不同内容才形成候选版本链。
BATCH = os.path.join(TMP, "batch")
put(os.path.join(BATCH, "report_v1.pdf"), "AAA")
put(os.path.join(BATCH, "report_v2.pdf"), "BBBB")
put(os.path.join(BATCH, "report_final.pdf"), "CCCCC")
put(os.path.join(BATCH, "a.txt"), "same-content")
put(os.path.join(BATCH, "a_copy.txt"), "same-content")
put(os.path.join(BATCH, "empty.txt"))
put(os.path.join(BATCH, "data", "raw.csv"), "x,y\n1,2\n")
rc, inv = run("inventory", BATCH)
add("inventory正向:文件数/权限/完整哈希", rc == 0 and inv.get("n_files") == 7
    and all(len(row["sha256"]) == 64 and row.get("permissions") for row in inv.get("files", [])),
    str(inv)[:300])
add("inventory正向:内容重复组", len(inv.get("duplicate_groups", [])) == 1
    and inv["duplicate_groups"][0]["files"] == ["a.txt", "a_copy.txt"]
    and len(inv["duplicate_groups"][0]["sha256"]) == 64, str(inv.get("duplicate_groups"))[:200])
add("inventory正向:内容不同才报版本", len(inv.get("version_chains", [])) == 1
    and inv["version_chains"][0]["base"] == "report"
    and len(inv["version_chains"][0]["files"]) == 3, str(inv.get("version_chains"))[:250])
add("inventory正向:空文件与复跑指纹", inv.get("empty_files") == ["empty.txt"]
    and len(inv.get("inventory_sha256", "")) == 64, str(inv.get("inventory_sha256")))
link_path = os.path.join(BATCH, "alias.txt")
os.symlink(os.path.join(BATCH, "a.txt"), link_path)
rc, linked = run("inventory", BATCH)
add("inventory变异:软链异常必命中且非零退出", rc == 1 and any(a["issue"] == "file_symlink"
    for a in linked.get("anomalies", [])), str(linked)[:250])
os.unlink(link_path)

SPEC = dump(os.path.join(TMP, "spec.json"),
            {"path_patterns": ["data/.+", "[^/]+"], "required_meta": []})
rc, check = run("checkmap", BATCH, "--spec", SPEC)
add("checkmap正向:规范内零误报", rc == 0 and check.get("ok"), str(check)[:250])
put(os.path.join(BATCH, "misc", "x.bin"), "z")
rc, check = run("checkmap", BATCH, "--spec", SPEC)
add("checkmap变异:路径违规必命中", rc == 1 and "misc/x.bin" in check.get("path_violations", []),
    str(check)[:200])

# mapmeta：列映射、常量、逐字段出处、缺字段/显式 unknown。
source_csv = os.path.join(TMP, "input.csv")
with open(source_csv, "w", encoding="utf-8", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=["原路径", "哈希", "字节", "来源", "定位", "版本", "日期", "权限"])
    writer.writeheader()
    writer.writerow({"原路径": "data/raw.csv", "哈希": "a" * 64, "字节": 8, "来源": "仪器A",
                     "定位": "upload/batch-1/data/raw.csv", "版本": "v1", "日期": "2026-01-02", "权限": "0644"})
map_path = dump(os.path.join(TMP, "map.json"), {
    "mapping_version": "map-1.0",
    "column_map": {"path": "原路径", "sha256": "哈希", "size": "字节", "source": "来源",
                   "source_locator": "定位", "version": "版本", "collected_at": "日期", "permissions": "权限"},
    "constants": {"project": "P1"}, "required": ["path", "sha256", "size", "source", "source_locator",
                                                "version", "collected_at", "project", "permissions"]})
manifest_csv = os.path.join(TMP, "mapped.csv")
rc, mapped = run("mapmeta", source_csv, "--map", map_path, "--output", manifest_csv)
with open(manifest_csv, encoding="utf-8-sig", newline="") as fh:
    mapped_rows = list(csv.DictReader(fh))
provenance = json.loads(mapped_rows[0]["field_provenance"])
add("mapmeta正向:批量映射与字段出处", rc == 0 and mapped.get("ok") and mapped_rows[0]["project"] == "P1"
    and provenance["path"]["column"] == "原路径" and provenance["project"]["kind"] == "constant"
    and mapped_rows[0]["mapping_version"] == "map-1.0", str(mapped)[:250])
with open(source_csv, "a", encoding="utf-8", newline="") as fh:
    fh.write("data/missing.csv,b*64,1,,upload/missing,v1,2026-01-02,0644\n".replace("b*64", "b" * 64))
rc, missing = run("mapmeta", source_csv, "--map", map_path, "--output", manifest_csv)
add("mapmeta变异:必填来源缺失必命中", rc == 1 and any(a["issue"] == "required_metadata_missing"
    and a["field"] == "source" for a in missing.get("anomalies", [])), str(missing)[:250])
unknown_map = dump(os.path.join(TMP, "map-unknown.json"), {**json.load(open(map_path, encoding="utf-8")),
                                                            "allow_unknown": ["source"]})
rc, unknown = run("mapmeta", source_csv, "--map", unknown_map, "--output", manifest_csv)
add("mapmeta异常:unknown诚实降级不误杀", rc == 0 and unknown.get("status") == "issues"
    and any(a["issue"] == "metadata_unknown" for a in unknown.get("anomalies", [])), str(unknown)[:250])

# diff：相同内容零差异，文本变化给坐标，二进制不伪造逐行差异。
old = put(os.path.join(TMP, "old.txt"), "alpha\nbeta\n")
new = put(os.path.join(TMP, "new.txt"), "alpha\ngamma\ndelta\n")
same = put(os.path.join(TMP, "same.txt"), "alpha\nbeta\n")
rc, diff = run("diff", old, same, "--old-version", "v1", "--new-version", "v1-copy")
add("diff正向:同内容不误报版本差异", rc == 0 and diff.get("identical") and diff.get("relation") == "duplicate"
    and diff.get("diff_lines") == [], str(diff)[:200])
rc, diff = run("diff", old, new, "--old-version", "v1", "--new-version", "v2")
add("diff变异:文本变化必命中", rc == 0 and not diff.get("identical") and diff.get("added_lines") == 2
    and diff.get("deleted_lines") == 1 and any("-beta" in line for line in diff.get("diff_lines", [])),
    str(diff)[:300])
binary_old = put(os.path.join(TMP, "old.bin"), b"\x00\xff\x01", binary=True)
binary_new = put(os.path.join(TMP, "new.bin"), b"\x00\xff\x02", binary=True)
rc, diff = run("diff", binary_old, binary_new)
add("diff变异:二进制变化必命中不伪造文本", rc == 0 and diff.get("kind") == "binary_or_non_utf8"
    and not diff.get("identical"), str(diff)[:200])

# verify + archive：路径、权限、来源、未登记、版本关系与损坏恢复。
LIB = os.path.join(TMP, "library")
lib_files = {"data/a.txt": "alpha\n", "docs/v1.txt": "old\n", "docs/v2.txt": "new\n"}
manifest = []
for rel, content in lib_files.items():
    path = put(os.path.join(LIB, *rel.split("/")), content)
    manifest.append({"path": rel, "sha256": sha(path), "size": os.path.getsize(path),
                     "source": "synthetic-bench", "source_locator": "memory://bench/" + rel,
                     "version": "v1" if rel != "docs/v2.txt" else "v2",
                     "collected_at": "2026-01-02", "project": "P1",
                     "permissions": "%04o" % stat.S_IMODE(os.stat(path).st_mode)})
manifest[2]["supersedes"] = "docs/v1.txt"
manifest_json = dump(os.path.join(TMP, "manifest.json"), {"manifest": manifest})
rc, verified = run("verify", LIB, "--manifest", manifest_json)
add("verify正向:哈希/权限/来源/版本零误杀", rc == 0 and verified.get("ok")
    and verified.get("checked_files") == 3, str(verified)[:400])
put(os.path.join(LIB, "data", "a.txt"), "CORRUPTED\n")
rc, corrupted = run("verify", LIB, "--manifest", manifest_json)
add("verify变异:文件损坏哈希不符必命中", rc == 1 and corrupted.get("hash_mismatches")
    and corrupted["hash_mismatches"][0]["status"] == "corrupt"
    and corrupted["hash_mismatches"][0]["actual_sha256"] == sha(os.path.join(LIB, "data", "a.txt")),
    str(corrupted)[:400])
put(os.path.join(LIB, "data", "a.txt"), lib_files["data/a.txt"])
os.chmod(os.path.join(LIB, "data", "a.txt"), 0o600)
rc, permission = run("verify", LIB, "--manifest", manifest_json)
add("verify变异:权限不符必命中", rc == 1 and permission.get("permission_mismatches"), str(permission)[:300])
os.chmod(os.path.join(LIB, "data", "a.txt"), int(manifest[0]["permissions"], 8))
put(os.path.join(LIB, "data", "unlisted.txt"), "new")
rc, unlisted = run("verify", LIB, "--manifest", manifest_json)
add("verify变异:未登记文件必命中", rc == 1 and unlisted.get("unlisted_files") == ["data/unlisted.txt"],
    str(unlisted)[:250])
os.unlink(os.path.join(LIB, "data", "unlisted.txt"))
bad_version = json.loads(json.dumps(manifest))
bad_version[0]["supersedes"] = "docs/v1.txt"
bad_version[0]["sha256"] = bad_version[1]["sha256"]
bad_version_path = dump(os.path.join(TMP, "bad-version.json"), bad_version)
rc, version_bad = run("verify", LIB, "--manifest", bad_version_path)
add("verify变异:把相同内容写成替代版本必命中", rc == 1 and any(e["issue"] == "supersedes_identical_content"
    for e in version_bad.get("version_errors", [])), str(version_bad)[:350])

archive_path = os.path.join(TMP, "handoff.zip")
rc, archived = run("archive", LIB, "--manifest", manifest_json, "--output", archive_path)
with zipfile.ZipFile(archive_path) as zf:
    archive_names = zf.namelist()
    archive_crc = zf.testzip()
add("archive正向:清单入包/CRC/包哈希", rc == 0 and archived.get("ok") and archived.get("crc_verified")
    and archive_crc is None and len(archived.get("archive_sha256", "")) == 64
    and "archive_manifest.json" in archive_names and "library/data/a.txt" in archive_names,
    str(archived)[:300])
rc, overwrite = run("archive", LIB, "--manifest", manifest_json, "--output", archive_path)
add("archive变异:重名归档不静默覆盖", rc == 1 and not overwrite.get("ok")
    and "--force" in overwrite.get("error", ""), str(overwrite)[:200])
put(os.path.join(LIB, "docs", "v2.txt"), "CORRUPTED AFTER VERIFY\n")
partial_archive = os.path.join(TMP, "must-not-exist.zip")
rc, refused = run("archive", LIB, "--manifest", manifest_json, "--output", partial_archive)
add("archive变异:损坏文件拒绝归档且无半截包", rc == 1 and not os.path.exists(partial_archive)
    and "verify" in refused.get("error", ""), str(refused)[:250])
put(os.path.join(LIB, "docs", "v2.txt"), lib_files["docs/v2.txt"])

# schema：可核验版本字段、完整 sha、运行复跑记录、恢复闭环。
BASE = {
    "case_id": "c1", "status": "pass", "directory_tree": {"data": ["a.txt"]},
    "manifest": [dict(manifest[0])],
    "dedup": {"groups": [{"sha256": "c" * 64, "files": ["a.txt", "a_copy.txt"], "keep": "a.txt"}],
              "freed_bytes": 4},
    "versions": {"docs": {"current": "docs/v2.txt", "history": ["docs/v1.txt"],
                           "basis": ["distinct_sha256", "mtime_ns"]}},
    "operations": [{"action": "move", "src": "upload/a.txt", "dst": "data/a.txt", "result": "ok",
                    "operator": "agent", "timestamp": "2026-01-02T03:04:05Z"}],
    "recovery": [{"type": "hash_mismatch", "path": "data/a.txt", "status": "resolved",
                  "action": "保留原件并重新采集", "recovery": "重跑 verify 通过"}],
    "run": {"tool_version": "2.0.0", "commands": ["inventory batch/", "verify library/ --manifest manifest.json"],
            "input_root": "batch/", "input_inventory_sha256": "d" * 64,
            "started_at": "2026-01-02T03:00:00Z", "completed_at": "2026-01-02T03:05:00Z"},
    "gain": {"baseline_fill_rate": 0.6, "skill_fill_rate": 0.98},
    "unchecked": [], "sources": ["upload/batch-1"], "uncertainty": [], "change_log": ["v1 -> v2"]}
base_path = dump(os.path.join(TMP, "result.json"), BASE)
rc, schema = run("schema", base_path)
add("schema正向:可核验交付零误杀", rc == 0 and schema.get("ok"), str(schema)[:400])

for name, mutate, expected in [
    ("manifest缺完整sha256", lambda x: x["manifest"][0].update(sha256="abc"), "sha256"),
    ("缺权限字段", lambda x: x["manifest"][0].pop("permissions"), "permissions"),
    ("缺来源定位", lambda x: x["manifest"][0].pop("source_locator"), "source_locator"),
    ("操作缺时间", lambda x: x["operations"][0].pop("timestamp"), "timestamp"),
    ("缺run复跑记录", lambda x: x.pop("run"), "run"),
    ("pass但异常未恢复", lambda x: x["recovery"][0].update(status="open"), "recovery"),
    ("current误入history", lambda x: x["versions"]["docs"]["history"].append("docs/v2.txt"), "current"),
]:
    bad = json.loads(json.dumps(BASE))
    mutate(bad)
    path = dump(os.path.join(TMP, "bad-" + str(len(checks)) + ".json"), bad)
    rc, result = run("schema", path)
    add("schema变异:" + name + "必命中", rc == 1 and any(expected in error for error in result.get("errors", [])),
        str(result)[:250])

ok = sum(1 for _, condition, _ in checks if condition)
for name, condition, detail in checks:
    print(("PASS" if condition else "FAIL"), name, ("| " + detail if not condition else ""))
print("total %d/%d" % (ok, len(checks)))
sys.exit(0 if ok == len(checks) else 1)
