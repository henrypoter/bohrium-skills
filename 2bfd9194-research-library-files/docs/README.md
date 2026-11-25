# 科研资料库与文件管理 v2.0.0

## 用途与完成标准

聚焦真实落库、内容去重、版本差异、字段映射和长期归档。目录与 manifest 一一对应，重复/版本按完整 SHA-256 区分，权限与来源可定位，操作和恢复可复跑。`checkmap + verify + schema` 是硬闸，任何失败不得报 `pass`。

## 命令（纯 Python 标准库）

```bash
python3 scripts/file_tool.py inventory batch/ --output inventory.json
python3 scripts/file_tool.py checkmap library/ --spec spec.json
python3 scripts/file_tool.py mapmeta input.csv --map map.json --output manifest.csv
python3 scripts/file_tool.py diff old_v1.txt new_v2.txt --old-version v1 --new-version v2
python3 scripts/file_tool.py verify library/ --manifest manifest.csv
python3 scripts/file_tool.py archive library/ --manifest manifest.csv --output handoff.zip
python3 scripts/file_tool.py schema result.json
```

- `inventory`：逐文件权限、完整哈希、mtime、重复组、候选版本、异常与复跑指纹。
- `mapmeta`：版本化批量映射，保留逐字段来源；缺失必填字段失败，显式 `unknown` 降级。
- `diff`：文本 unified diff；二进制只报哈希/大小，不伪造逐行差异。
- `verify`：哈希/大小/权限/来源/未登记文件/版本关系核验，损坏文件给出重采恢复。
- `archive`：verify 全过后原子生成 ZIP，内嵌 manifest、CRC 回读、包 SHA-256，重名默认拒绝覆盖。
- `schema`：检查可复跑 `run`、完整 manifest、操作时间、版本、去重和 `recovery` 闭环。

完整输入输出、异常表、最小示例见根目录 `SKILL.md`；目录与字段字典见 `templates/directory_spec.md`。

## 自测

```bash
python3 bench/bench_run.py
```

合成正常批次验证零误杀，变异覆盖软链、路径违规、字段缺失、文本/二进制变化、哈希损坏、权限漂移、未登记文件、伪版本、归档重名/半截包和 result 缺字段。测试临时目录自动创建，不使用正式案例。

## 适用边界

验证字节与结构，不证明科学内容正确；不自动理解扫描件，不访问私人网盘/Zotero，不编造缺失元数据或对照增益。无原始文件/权限时交付明确的 partial/blocked 记录。
