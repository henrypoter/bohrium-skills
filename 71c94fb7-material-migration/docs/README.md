# 科研资料收集与迁移

版本 `2.0.0`。纯标准库；实际要求与字段示例见 `SKILL.md`。

## 命令

```bash
python3 scripts/auto_tool.py trace result.json
python3 scripts/auto_tool.py schema result.json
python3 scripts/auto_tool.py recovery_check result.json
python3 scripts/auto_tool.py migration_check result.json
python3 scripts/auto_tool.py resume result.json
python3 scripts/auto_tool.py manifest artifacts.json <真实文件> [...]
python3 scripts/auto_tool.py verify_manifest artifacts.json
```

- `recovery_check`：登录失效、下载失败、写入报错及其他分类恢复。
- `migration_check`：来源/attribution、映射、去重、事务、记录与附件恒等式。
- `schema`：原 output_contract、来源数、版本字段。
- manifest：对真实文件计算并重算 SHA-256。

## 自测

```bash
python3 bench/bench_run.py   # 46/46
```

合成夹具仅验证工具，不是官方案例或提升分数。
