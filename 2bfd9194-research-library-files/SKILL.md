---
name: research-library-files
description: 科研资料库与文件管理：真实落库、内容哈希去重、版本差异、批量元数据映射、权限来源核验和可验证 ZIP 归档
---

# 科研资料库与文件管理

把一批文件**真正落库并留下复核链**：目录树、逐文件元数据、完整 SHA-256、重复/版本关系、操作与恢复日志齐全。只给整理建议、只改名而没有清单，均不算完成。

适用：本地或已挂载资料批次的清点、归位、去重、版本梳理和交接归档。不适用：网盘同步配置、文献引文格式转换、权限系统运维；没有原始文件或授权时只能交付 `partial/blocked` 记录。

## 判对硬约束（三道闸）

1. **目录与清单一致**：实际目录每行都有 manifest，反之亦然；必填字段、路径规范、来源定位、权限均通过 `checkmap + verify`。
2. **重复与版本按内容判断**：SHA-256 相同才是内容重复；同 base 但哈希不同才列为**候选版本**。同内容不得伪装成 `supersedes`；文本版本必须有 `diff` 证据，二进制只能报告哈希/大小差异。
3. **他人能复跑**：保留 `inventory_sha256`、实际命令、完整哈希、操作时间、异常恢复动作；交付前 `schema` 必须通过。`status=pass` 时不得仍有 `open/blocked` 异常。

任一闸未过：继续修复或将状态降为 `issues/partial/failed`，不得写“全部完成”。

## 输入、输出与环境

- 输入：`/input/case.json`、`/input/task.md` 和题目实际给出的文件；先读任务中的目录规则、版本说明和 `output_contract`。
- 工作区：`/app/work`；最终产物：`/app/output/result.json`、`inventory.json`、manifest、`verification.json`（保留 `verify` 输出）、操作日志；要求归档时再加 ZIP。
- 工具：`scripts/file_tool.py`，仅 Python 标准库，工具版本 `2.0.0`。平台安装后可设 `SKILL_HOME=/skills/weekly-skill`；本地演示时设为提交目录。
- 保留原题目要求的全部字段；下述字段是补充而非替代。平台记录的模型/预算/原生 trace 不自行编造。

```bash
export SKILL_HOME="${SKILL_HOME:-/skills/weekly-skill}"
mkdir -p /app/work /app/output
TOOL="$SKILL_HOME/scripts/file_tool.py"
```

## 可复跑工作流

### 0. 先定规范，不先搬文件

从任务材料确定目录层级、允许类型、命名规则、必填字段和保留策略，写入项目 spec；模板见 `templates/directory_spec.md`。未给规则时采用模板并标为“建议规范”，不得冒充题目原规则。

搬移前先规划 `src -> dst`，检查目标重名、剩余空间和回滚路径。优先复制并验证后再按任务要求处置源件；**不静默覆盖、不直接删除唯一原件**。

### 1. 清点、权限和完整指纹

```bash
python3 "$TOOL" inventory /app/work/batch --output /app/output/inventory.json
```

输出逐文件 `path/size/ext/sha256/permissions/mtime_ns/source`、`duplicate_groups`、`version_chains`、`empty_files/empty_directories/anomalies` 和本报告 `inventory_sha256`。非零退出表示目录或软链等异常，先登记处置再往下走。

- 重复组使用完整 64 位哈希，不能只看文件名或短哈希。
- `current_candidate` 只是按修改时间给出的候选；须结合版本说明、任务规则和 `diff` 确认 `current/history/supersedes`，不能因文件名含 `final` 就自动认定最新。
- 空文件可能是有效占位，也可能采集失败；查来源后明确保留或重采，不得静默删除。

### 2. 批量字段映射并保留出处

伴随表格的列名不固定时，先写版本化 `map.json`，再执行：

```bash
python3 "$TOOL" mapmeta /app/work/input.csv \
  --map /app/work/map.json --output /app/output/manifest.csv
```

`map.json` 示例（列名必须按真实输入调整）：

```json
{
  "mapping_version": "map-1.0",
  "column_map": {"path": "原路径", "sha256": "哈希", "source": "来源", "version": "版本"},
  "constants": {"project": "P1"},
  "required": ["path", "sha256", "size", "source", "source_locator", "version", "collected_at", "project", "permissions"],
  "allow_unknown": []
}
```

输出的 `mapping_version` 和 `field_provenance` 记录每字段来自哪一列、哪一行或哪个常量。必填缺失默认失败；只有映射明确列入 `allow_unknown` 才填 `unknown`，同时输出 `metadata_unknown`，不得由文件名臆造作者、年份、仪器或项目号。

### 3. 去重与版本差异

```bash
python3 "$TOOL" diff /app/work/report_v1.txt /app/work/report_v2.txt \
  --old-version v1 --new-version v2 > /app/output/report-v1-v2.diff.json
```

- `relation=duplicate`：内容完全相同，选保留件并把其他路径记 `duplicate_of`，按要求归档而非无痕删除。
- `relation=content_differs`：结合修改时间与任务说明建立方向，manifest 新版写 `supersedes`，旧版不能删除；`versions[base]` 记录 `current/history/basis`。
- UTF-8 文本保留 unified diff 与增删行数；非 UTF-8/二进制没有逐行证据时明确写限制。
- 哈希不足以判断两个同 base 文件一定有版本关系；只输出候选，语义关系不确定时加入 `uncertainty`。

### 4. 归位后双核验

manifest（JSON 数组、含 `manifest` 数组的 JSON，或 CSV）每行至少含：

`path / sha256 / size / source / source_locator / version / collected_at / project / permissions`。

其中 `source` 是来源主体/批次，`source_locator` 是可回到原路径、仪器官网批次或交接记录的定位；`permissions` 为四位八进制如 `0644`。无版本文件可用 `unversioned`，未知必须有原因，不能编版本号。

```bash
python3 "$TOOL" checkmap /app/work/library --spec /app/work/spec.json
python3 "$TOOL" verify /app/work/library --manifest /app/output/manifest.csv \
  > /app/output/verification.json
```

`verify` 机检：不安全/重复路径、缺失字段、完整 SHA-256、文件大小、权限、来源定位、未登记文件、`supersedes` 目标及“相同内容伪版本”。任何错误均非零退出；修复后**从原输入重新计算并重跑**，而不是手改报告为通过。

### 5. 操作、异常与恢复日志

每个动作记录 `action/src/dst/result/operator/timestamp`；去重、改名、移动和归档可定位到 manifest。`recovery[]` 每项固定写 `type/path/status/action/recovery`，状态只能 `resolved/open/blocked`。

| 异常 | 立即处置 | 恢复与交付状态 |
|-|-|-|
| 上传/复制中断 | 分列源端、已落库、未落库；按完整 SHA-256 找续点 | 从来源续传，重跑 verify；未齐时 `partial` |
| 权限不足/文件不可读 | 记 `blocked`、路径、所需权限和错误；不跳过 | 获批授权或交接方补件后重跑；无权限不伪造权限值 |
| 重名冲突 | 先比哈希，不覆盖；同内容记重复，不同内容保留两路径 | 确认版本关系，写 `supersedes/duplicate_of` 和 change_log |
| 文件损坏、大小或哈希不符 | `verify.hash_mismatches` 标 `corrupt`，保留原件，不入正常归档 | 从 `source_locator` 重采；未恢复为 `open/blocked`，禁止顶替 |
| 元数据缺失/冲突 | 指出字段、输入行和已有出处；不猜测 | 可证实再补；否则 `unknown + uncertainty`，状态非 pass |
| 存储空间不足 | 停止搬移/打包，比较剩余空间与待写量 | 清理**可再生临时文件**或扩容后原子重跑；不留下宣称完整的半截包 |
| 空目录、空文件、软链 | inventory 明列，区分有效占位和漏采 | 按任务规则清理/补件；软链换实体文件并重新哈希 |
| 归档输出重名 | 默认拒绝覆盖 | 明确 `--force` 才替换，保留 change_log；先确保 verify 通过 |

### 6. 可验证归档包（任务要求时）

```bash
python3 "$TOOL" archive /app/work/library --manifest /app/output/manifest.csv \
  --output /app/output/handoff.zip > /app/output/archive.json
```

仅 verify 全过才生成；输出必须在资料根之外。ZIP 内为 `library/<原相对路径>` 与 `archive_manifest.json`，回读 `testzip()` 校验 CRC，临时文件原子替换为最终包。结果保存 ZIP 完整 `archive_sha256`、文件数和源 manifest 哈希。verify 失败、空间不足或 CRC 失败时无“成功包”。

### 7. result.json 与最终闸

必须保留原 `output_contract` 字段，并补齐：

```json
{
  "case_id": "example-only",
  "status": "pass",
  "directory_tree": {"data": ["a.txt"]},
  "manifest": [{
    "path": "data/a.txt", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "size": 6, "source": "示例批次", "source_locator": "upload/example/a.txt",
    "version": "v1", "collected_at": "2026-01-02", "project": "P1", "permissions": "0644"
  }],
  "dedup": {"groups": [], "freed_bytes": 0},
  "versions": {},
  "operations": [{"action": "copy", "src": "upload/example/a.txt", "dst": "data/a.txt",
                   "result": "ok", "operator": "agent", "timestamp": "2026-01-02T03:04:05Z"}],
  "recovery": [],
  "run": {"tool_version": "2.0.0", "commands": ["inventory /app/work/batch"],
           "input_root": "/app/work/batch", "input_inventory_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
           "started_at": "2026-01-02T03:00:00Z", "completed_at": "2026-01-02T03:05:00Z"},
  "archive": {"path": "handoff.zip", "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
               "manifest_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "file_count": 1},
  "gain": {"baseline_fill_rate": null, "skill_fill_rate": null, "manual_edits_saved": null},
  "unchecked": [], "sources": ["upload/example"], "uncertainty": [], "change_log": []
}
```

以上仅为**接口示例**，哈希须替换成真实计算值；不做归档时 `archive` 可省略或置 `null` 并说明。没有同输入基础 Agent 实测时 gain 保持 `null`，不得编造提升率。

```bash
python3 "$TOOL" schema /app/output/result.json
python3 "$SKILL_HOME/bench/bench_run.py"   # 开发自测，不替代正式案例
```

最终交付目录树与 manifest、verify、版本 diff、操作/恢复记录相互一致。即使 JSON 校验失败，也保留已生成的真实产物，同时在 result 说明失败。

## 最小调用示例

```bash
python3 scripts/file_tool.py inventory ./batch
python3 scripts/file_tool.py mapmeta ./input.csv --map ./map.json --output ./manifest.csv
python3 scripts/file_tool.py verify ./library --manifest ./manifest.csv
python3 scripts/file_tool.py archive ./library --manifest ./manifest.csv --output ./handoff.zip
python3 scripts/file_tool.py schema ./result.json
```

示意输出：`verify` 为 `{"ok": true, "checked_files": 1, "errors": []}`；仅是说明，不是正式案例结果。

## 边界与底线

本工具验证字节完整性、文本差异和交接结构，不证明科学结论正确，也不自动理解 PDF/图片内容；此类语义元数据须人工或原格式工具提供证据。不访问私人账户，不伪造外部软件状态。**不静默跳过、不按文件名去重、不用相同内容冒充版本、不在校验失败时标 pass。**
