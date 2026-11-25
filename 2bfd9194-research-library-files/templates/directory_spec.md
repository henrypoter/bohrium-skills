# 目录规范与元数据字典（directory_spec.md）

## 1. 目录层级（先定规范再搬文件）

```
project/
├── 01_raw/           原始数据，只读，不改名
├── 02_processed/     处理中间产物，可重生成
├── 03_docs/          方案/协议/记录
├── 04_figures/       图件（含可编辑源）
└── 05_archive/       历史版本与 superseded 文件
```

## 2. 命名规则

```
<项目>-<类型>-<主题>-<版本>.<ext>
例：P1-raw-cytometry-v2.csv
```
- 版本号 `v1/v2/v3`，**不用 final/最新/副本**（这类词无法排序）
- 日期用 `YYYYMMDD`，不用 `2026.11.20` 或 `11/20`

## 3. 元数据必填字段（manifest 每行）

| 字段 | 说明 | 允许为空 |
|-|-|-|
| path | 相对项目根的安全路径，不绝对化、不含 `..` | 否 |
| sha256 | 完整 64 位内容哈希 | 否 |
| size | 字节数，与实文件一致 | 否 |
| source | 原始来源（谁给的/哪个库/哪台仪器） | 否 |
| source_locator | 可回链的原路径、批次或交接记录 | 否 |
| version | 版本号；无版本写 `unversioned` | 否 |
| collected_at | 实际采集日期 | 否 |
| project | 有证据的归属项目 | 否 |
| permissions | 四位八进制权限，如 `0644` | 否 |
| supersedes | 当前版本替代的 manifest path | 仅新版需要 |
| duplicate_of | 同内容保留件的 manifest path | 仅副本需要 |
| field_provenance | 字段来自源列/行或映射常量的 JSON | 批量映射时否 |
| mapping_version | 字段映射配置版本 | 批量映射时否 |
| note | 备注（处理方式、异常） | 是 |

## 4. 去重与版本判据

| 情形 | 判定 | 动作 |
|-|-|-|
| 不同名，sha256 相同 | 重复 | 保留一份，另一份进 05_archive 并记 `duplicate_of` |
| 同名，sha256 不同 | 版本 | 链成版本链，标 current / history |
| 同名，sha256 相同 | 覆盖式重复 | 只留一份，记操作日志 |
| 内容 99% 相似（人工判断） | 疑版本 | 标 `suspected_version` 交人工，**不自动合并** |

## 5. 归档自检

- [ ] `inventory` 里 `empty_files`、`empty_directories` 与 `anomalies` 已全部处置
- [ ] 每个文件都有 manifest 行（`checkmap.no_manifest_row` 与 `verify.unlisted_files` 均为空）
- [ ] 路径符合命名规则（`path_violations` 为空），没有绝对路径或 `..`
- [ ] `verify` 的完整哈希、大小、权限、来源定位和版本关系全部通过
- [ ] 不同内容的文本版本附 `diff`；同内容只记 duplicate，不记 supersedes
- [ ] 操作日志可还原任意文件的来源与变更，`recovery` 无未说明的 open/blocked
- [ ] `run.commands/input_inventory_sha256/tool_version` 可支持复跑，`schema` 通过
- [ ] ZIP 只在 verify 通过后生成，内嵌 manifest、CRC 回读通过并记录包 SHA-256
