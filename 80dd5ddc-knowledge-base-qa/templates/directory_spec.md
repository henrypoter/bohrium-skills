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
| path | 相对项目根的路径 | 否 |
| sha256 | 内容哈希 | 否 |
| source | 原始来源（谁给的/哪个库/哪台仪器） | 否 |
| version | 版本号 | 否 |
| collected_at | 采集日期 | 否 |
| project | 归属项目 | 否 |
| note | 备注（处理方式、异常） | 是 |

## 4. 去重与版本判据

| 情形 | 判定 | 动作 |
|-|-|-|
| 不同名，sha256 相同 | 重复 | 保留一份，另一份进 05_archive 并记 `duplicate_of` |
| 同名，sha256 不同 | 版本 | 链成版本链，标 current / history |
| 同名，sha256 相同 | 覆盖式重复 | 只留一份，记操作日志 |
| 内容 99% 相似（人工判断） | 疑版本 | 标 `suspected_version` 交人工，**不自动合并** |

## 5. 归档自检

- [ ] `inventory` 里 `empty_files` 与 `anomalies` 已全部处置
- [ ] 每个文件都有 manifest 行（`checkmap` 的 `no_manifest_row` 为空）
- [ ] 路径符合命名规则（`path_violations` 为空）
- [ ] 操作日志可还原任意文件的来源与变更

## 6. 知识库问答附加字段

`index.json` 中文档除上述字节/来源字段外，保留 `doc_id/version/role/include_in_search/text_status/text_source/extraction_method`。引用必须包含：

| 字段 | 判对要求 |
|-|-|
| path | 能回到 index 中实际文件 |
| sha256 | 与该文件完整内容版本一致 |
| version / role | 版本标签和 current/history/duplicate 均与索引一致 |
| chunk_id | 指向具体段落，不能跨段拼接 |
| quote | 目标 chunk 原文的精确子串 |
| locator | page/paragraph/start_line/end_line 全部与 chunk 一致；无页界时 page=null |
| scope.index_sha256 | 与实际索引重算指纹一致 |
| missing | no_evidence/partial 说明缺少的文件、字段或版本 |

重复副本的 `duplicate_of`、历史版本的 `superseded_by`、当前版本的 `supersedes` 用于解释角色，不能把重复副本当独立证据。版本冲突未由行政说明解决时，不填 current 猜测值，分版本并列回答并记异常。
