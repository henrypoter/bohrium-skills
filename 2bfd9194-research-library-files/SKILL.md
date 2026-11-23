---
name: research-library-files
description: 科研资料库与文件管理：内容哈希去重、版本链识别、目录规范核验、元数据与操作日志齐全
---

# 科研资料库与文件管理

把一批文件**真正落库**：目录结构、元数据清单、哈希与版本关系、操作日志四件齐备，他人可照单复跑。

不适用：云端网盘的同步配置、文献管理软件的引文格式转换、权限系统本身的运维。

## 调用

- 输入：`/input/case.json`、`/input/task.md`、待归档文件批次
- 输出：`/app/output/result.json` + 目录树 + manifest（CSV/JSON）+ 操作日志
- 工具：`scripts/file_tool.py`（`inventory` / `checkmap` / `schema`）
- 模板：`templates/directory_spec.md`（目录规范 + 命名规则 + 字段字典 + 元数据必填项）

## 工作流

### 0. 先定规范，再动手
按 `templates/directory_spec.md` 写：目录层级、命名规则、必填元数据字段、允许的文件类型。**规范先于搬文件**，否则后面全是返工。

### 1. 清点与指纹
```bash
python3 scripts/file_tool.py inventory batch/
```
输出：每个文件的 `sha256`、大小、扩展名；`duplicate_groups`（内容完全相同）；`version_chains`（同名不同版本，如 `report_v1/v2/final`）；`empty_files`；`anomalies`（软链、读取失败）。
- **去重按内容哈希，不按文件名**。同名不同内容是版本，不同名同内容才是重复。
- 空文件与软链必须显式处置（删除或登记），**不得静默跳过**。

### 2. 版本关系判定
同一 `base` 下多个文件构成版本链：确定哪一个是"当前有效版本"，其余标为历史版本并保留 `supersedes/superseded_by` 关系。判据写进 change_log（按日期/命名/内容差异）。

### 3. 归位与元数据
按规范移动到目标目录，为每个文件写 manifest 行：`path / sha256 / source（原路径或来源）/ version / 采集时间 / 归属项目`。
```bash
python3 scripts/file_tool.py checkmap library/ --spec spec.json
```
核验路径是否合规、必填元数据是否齐全、是否有文件没有 manifest 行。不通过就补，**不要带着缺口交差**。

### 4. 操作日志
每个动作一行：`action（move/rename/dedup/archive）/ src / dst / result / operator / timestamp`。目的：任意一个文件都能说清"从哪来、怎么变的、现在在哪"。

### 5. 增益对照
同批次、同权限、同条件，基础 Agent vs 本 Skill 各跑一次，报：落库正确率、字段填充率、人工修改条目数、重复上传次数。

### 6. 异常处置
| 异常 | 动作 |
|-|-|
| 上传中断 | 记录已成功与未成功的文件清单，按 sha256 续传，不重复上传 |
| 权限不足 | 该文件标 `blocked`，写清缺什么权限，不算作已完成 |
| 重名冲突 | 同名不同内容 → 进版本链，不覆盖；同名同内容 → 去重并记录 |
| 文件损坏（哈希不符） | 保留原件、标 `corrupt`、重新采集；**不得用损坏文件顶替** |
| 元数据缺失 | 逐条列出缺哪个字段；无法补的标 `unknown`，不臆造 |
| 存储空间不足 | 停止搬移并报告剩余空间与待搬量，不产生半截归档 |

### 7. 诚实输出
```bash
python3 scripts/file_tool.py schema /app/output/result.json
```

## result.json 契约

```json
{
  "case_id": "", "status": "pass|issues|partial|failed",
  "directory_tree": {"data": ["raw.csv"]},
  "manifest": [{"path": "data/raw.csv", "sha256": "…", "source": "upload/第1批", "version": "v1",
                "collected_at": "2026-11-20", "project": "P1"}],
  "dedup": {"groups": [{"sha256": "…", "files": ["a.txt", "a_copy.txt"]}], "freed_bytes": 0},
  "versions": {"report": {"current": "report_final.pdf", "history": ["report_v1.pdf", "report_v2.pdf"]}},
  "operations": [{"action": "move", "src": "raw.csv", "dst": "data/raw.csv", "result": "ok",
                  "operator": "agent", "timestamp": "2026-11-20T10:00Z"}],
  "gain": {"baseline_fill_rate": null, "skill_fill_rate": null, "manual_edits_saved": null},
  "unchecked": [], "sources": [], "uncertainty": [], "change_log": []
}
```

## 底线
不静默跳过难处理的文件、不用文件名代替内容哈希、不留没有 manifest 行的文件。

## 本课题聚焦
本题聚焦**落库与版本管理**。去重按内容哈希而非文件名；同名不同内容进版本链并标 current/history；空文件与软链必须显式处置。`checkmap` 的路径违规与缺失元数据必须清零，不留没有 manifest 行的文件。
