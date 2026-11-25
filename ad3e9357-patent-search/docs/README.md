# 专利与技术文献检索 Skill

## 用途与安装
无需 pip、网络或第三方包；Python 3.8+ 标准库。安装到 `/skills/weekly-skill` 后由 Agent 读取根目录 `SKILL.md`。所有路径均可改为本目录的绝对路径。工具只处理实际输入，不包含三个正式案例或预制答案。

## 一次完整调用
1. 读 `/input/case.json`、`/input/task.md`、资源清单，保留原输出契约。
2. 按 `templates/protocol.md` 登记号码角色、主题、来源版本/日期/许可和实际查询。
3. 保存原始响应并计算 SHA-256；建立 `field_bindings` 和逐字证据。
4. 依次运行 `normalize`、`family`、`status`；把真实输出合并进结果。
5. 有同输入同权限 qrels 对照才运行 `gain`，否则 `gain.mode=not_measured`。
6. 写 `/app/output/result.json`，运行 `audit`。失败返回 1，修复后重跑；无法修复则保留 partial/issues 和具体未完成项。

```bash
python3 scripts/search_tool.py normalize bench/fixtures/records.json
python3 scripts/search_tool.py family bench/fixtures/records.json
python3 scripts/search_tool.py status bench/fixtures/legal.json
python3 scripts/search_tool.py gain bench/fixtures/gain.json
python3 scripts/search_tool.py audit bench/fixtures/good_result.json
python3 bench/bench_run.py
```

## 最小示例（合成自测，非正式结果）
`good_result.json` 演示两个共享优先权的专利、一个技术论文、两个权利要求版本和一个历史 Grant 事件。其当前法律状态仍为 `unknown`，族 `complete=false`、权利要求 `claim_scope_equal=false`。`source.json` 是实际供引文回读的合成源文件；修改任一引文或哈希都会使审计失败。

## 五命令边界
- `normalize`：只规范排版和角色，不验证号码在真实官方库存在；存在性由字段绑定和真实来源证明。
- `family`：仅按给定优先权/族标识归并，不补全在线族，不判断权利要求等同。
- `status`：整理事件及核验级别，不将最新事件自动解释为法律结论。
- `gain`：只计算给定 qrels/排名/成本，不自行生成 baseline。
- `audit`：验证本地证据闭环，不能替代官方登记、许可审查或人工法律复核。

## Bench
`bench/bench_run.py` 共 **19 项**：五个命令均有正向测试和定向变异；覆盖非法号码、族冲突、状态冲突、不公平对照、伪引文、哈希变化、越权展示、无官方当前状态、伪完整族、漏族成员、计数断裂、字段错配、权利要求等同与虚构增益。

## 维护与限制
版本见 `REVISION.md`。适用于授权的有限专利/论文快照；不声称实时在线覆盖、全球新颖性或完整法律状态。模板 `protocol.md`、`reason_codes.md`、`worksheets.md` 可复制复用。GitHub 链接见根目录 `GITHUB_URL.txt`，公开可用性需在未登录窗口另行确认。
