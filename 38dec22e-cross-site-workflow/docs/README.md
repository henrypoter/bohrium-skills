# 38dec22e-cross-site-workflow

版本 `2.0.0`，纯标准库工具与合成机检闭环。

```bash
python3 scripts/crosssite_tool.py flow_check result.json
python3 scripts/crosssite_tool.py schema result.json
python3 scripts/crosssite_tool.py audit result.json
python3 scripts/crosssite_tool.py resume result.json
python3 scripts/crosssite_tool.py manifest artifacts.json <真实文件> [...]
python3 scripts/crosssite_tool.py verify_manifest artifacts.json
python3 bench/bench_run.py   # 32/32
```

`audit` 覆盖任务状态、操作、权限、传递、恢复、冲突；`schema` 检查原 output_contract 和版本；manifest 命令核验真实文件字节。使用约束、最小合成示例、异常表见 `SKILL.md`。bench 不是正式案例结果。
