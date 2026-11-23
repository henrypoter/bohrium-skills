# 内容级核验夹具测试报告（正向零误杀、变异必命中）

复跑：`python3 tests/run_tests.py`（纯标准库，真实子进程 + 真实退出码），结果落
`tests/test_results.json`。本报告记录 v2 → v3 的真实 bug 复现与修复证据。

## 1. 先用夹具复现真实 bug（修复前，v2 脚本实测）

对同一合规正向夹具（`tests/fixtures/positive/`），v2 脚本输出：

```
"errors":   ["E9 C2: 强词 ['广泛接受'] 但证据等级 C 非 A"]
"warnings": ["M1 论断 C1 未在 manuscript 引用", "M1 论断 C2 未在 manuscript 引用"]
exit code = 1
```

逐条定位出三个真实 bug：

| # | 类型 | 现象 | 根因 |
|-|-|-|-|
| B1 | **误杀** | 合规论断 C2（A 级 full 绑定 + C 级 partial 绑定）被 E9 错杀 | `max(bound_levs)` 按 ASCII 取到**最差**等级 C；应取最强等级（min） |
| B2 | 误报 | 正文 `[C1:E1]` 引用式（本 Skill 自带示例就在用）被判「未引用」 | `CLAIM_ID_RE = \[C\d+\]` 不匹配带证据后缀的 `[C#:E#]` |
| B3 | **漏检** | 证据/论断 id 重复（编号冲突）静默通过，绑定可指向错误证据 | 建索引时直接覆盖，无唯一性检查 |

修复前 `run_tests.py` 实测：17 项中 6 项 FAIL（正向误杀 1 + 编号冲突漏检 2 +
受 B1 污染的其他正向路径 3）。

## 2. 修复（scripts/evidence_lib.py，另含 check_result.py 一处口径补强）

- B1：论断强度上限改取**最强**绑定证据 `min(bound_levs)`（A<B<C<D）。
- B2：`CLAIM_ID_RE` 改为 `\[C(\d+)(?::E\d+)?\]`，兼容 `[C#]` 与 `[C#:E#]`。
- B3：新增 **E12** 证据/论断编号唯一性硬检查（编号冲突 → error）。
- check_result.py：`change_records` 纳入必需字段（允许空列表，其余字段空则拒）。

## 3. 修复后实测（exit code 见 tests/test_results.json）

| 组 | 用例 | 期望 | 实测 |
|-|-|-|-|
| 正向 | 合规样例 | rc=0 零误杀 | **rc=0 ✓** |
| 变异 | E1 缺字段 / E5 编造 quote / E7 数值失真 / E9 弱证据强结论 / E10 仅 partial 判 supported / E2 缺 note / E4 conflicted<2 / M1 未定义编号 / E12 证据编号冲突 / E12 论断编号冲突 / E6 非法等级 | rc=1 且规则码命中 | **11/11 全部 rc=1 且码命中 ✓** |
| 异常 | 论断超出材料（判 unsupported） | rc=0 不误杀 | **rc=0 ✓** |
| 异常 | 材料缺失（无原文目录） | rc=0 且显式降级 note「E5=unchecked」 | **rc=0 ✓** |
| 异常 | 超长输入（约 450KB 语料） | rc=0 且 <30s | **rc=0，0.1s ✓** |
| 契约 | 合规 result.json / 缺 uncertainty 的 result.json | rc=0 / rc=1 | **✓ / ✓** |

**合计 17/17 通过，`python3 tests/run_tests.py` 退出码 0。**

## 4. 边界（诚实声明）

- 夹具材料与文献均为自编虚构，只验证核验脚本行为，不代表真实案例难度。
- 变异集覆盖的是「单点故障注入」，组合故障未穷举。
- 充分性判定的语义起点仍由 LLM 给出（verdict/scope/note），脚本复核其
  与 quote、数值、强度词、编号的一致性；脚本不能证明「原文在科学上足以支撑」。
