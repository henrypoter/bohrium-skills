# 修订说明（v2 → v3；file_tool 2.0.0）

## 实际效果（40）：三道判对闸变成可执行检查

- **目录/元数据一致**：保留 v2 的 `inventory`、`checkmap`，新增 `verify`。除目录路径和必填字段外，逐文件核对完整 64 位 SHA-256、大小、四位八进制权限、来源主体与 `source_locator`、未登记文件和不安全路径。
- **重复与版本按内容**：`inventory` 现在输出逐文件清单和完整哈希；同 base 同哈希只进重复组，不再误报版本。只有不同哈希才形成候选版本链，并用 mtime 给出可复核排序；`current_candidate` 明确要求人工/任务说明确认。
- **可复跑**：`inventory_sha256` 固定输入盘点，`result.json.run` 强制记录工具版本、实际命令、输入根、输入指纹和起止时间；操作记录补 `operator/timestamp`，`recovery` 记录异常、处置和恢复闭环。

## 使用增益（25）

`mapmeta` 将伴随表格批量映射为 manifest，减少逐条手工填字段；`verify` 一次列出哈希/权限/来源/漏登记问题，避免多轮人工核对；`archive` 一次完成校验、打包和 CRC 回读。`gain` 只接受同输入、同权限的实测；没有基础 Agent 对照时保持 `null`，不把 bench 通过率写成平台增益。

## 创新增益（15）

在已有内容哈希去重和目录规范基础上新增四个纯标准库命令：

1. `mapmeta`：版本化 `column_map/constants/required/allow_unknown`，输出 `mapping_version + field_provenance`，每个字段可追溯到源列、行或映射常量。
2. `diff`：哈希相同直接判 duplicate；不同 UTF-8 文本输出 unified diff 和增删行数；非 UTF-8/二进制明确只报字节证据。
3. `verify`：内容、大小、权限、来源、漏登记与 `supersedes` 关系联合核验；能抓住“相同内容伪装替代版本”。
4. `archive`：verify 前置闸、原子写 ZIP、内嵌归档 manifest、CRC 回读和ZIP/源 manifest 完整哈希；重名默认拒绝覆盖，失败不留下成功假包。

## 可靠体验（10）

异常表保留上传中断、权限不足、重名冲突、损坏哈希、元数据缺失、空间不足，并补空文件/空目录/软链与归档重名。损坏文件标 `corrupt` 且保留原件，从 `source_locator` 重采；校验失败降级为 `issues/partial/failed`，`status=pass` 时 schema 禁止未解决恢复项。

## 生态贡献（10）

`SKILL.md` 给出完整调用、输入输出、异常恢复、最小示例和适用边界；`templates/directory_spec.md` 补 `size/source_locator/permissions/supersedes/duplicate_of/field_provenance/mapping_version`；`docs/README.md` 可直接复用全部命令。

## Bench 证据与边界

`python3 bench/bench_run.py`：**29/29 PASS**。正常批次验证零误杀；变异必命中覆盖软链、路径违规、必填来源缺失、文本/二进制变化、哈希损坏、权限漂移、未登记文件、伪版本、归档重名、损坏拒打包和 schema 缺字段。测试为合成数据，不是正式三案例成绩。

相对基础 Agent 的边界：本 Skill 可稳定验证字节、权限、字段、文本差异和归档结构，但不证明科学结论、不自动理解扫描 PDF/图片、不操作私人账户，也不能在缺失来源时推断真实元数据。相对榜首仍需平台固定三案例的目录归位正确率、复杂真实批次字段映射成功率、真实 PDF/大二进制版本处理和基础 Agent 同条件增益证据；本地 bench 不能替代这些平台结果。
