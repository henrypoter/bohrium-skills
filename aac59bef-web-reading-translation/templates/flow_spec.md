# 网页阅读翻译流程规格 v3.0.0

## 1. 状态机与完成定义

```
pending ─成功且有输出哈希→ done
   ├─可恢复失败→ failed ─同一幂等键有界重试→ pending
   ├─权限/人工操作→ blocked ─人工解锁→ pending
   └─明确条件不满足→ skipped（必须说明，不计完成）
```

只有 W1 抓取、W2 抽取、W3 全块翻译、W4 机检、W5 交付均 done，`align` 无 errors/warnings/missing，`audit --snapshot --meta` 重算一致，且 unchecked 为空时，result 才可标 pass。分页/懒加载/权限/缺段的产物必须 issues/partial/failed。

## 2. DAG 与幂等键

| id | 步骤 | depends_on | input | output | 幂等键示例 |
|-|-|-|-|-|-|
| W1 | 锁定 URL、抓取/保存真实 DOM、stamp | — | case.json、URL、权限 | source.html、fetch.json | W1-最终URL-目标快照日期 |
| W2 | 正文抽取、排噪、覆盖审查 | W1 | source.html、fetch.json | corpus.json | W2-source-sha256 |
| W3 | 术语表、逐 ID 中文翻译、语义抽查 | W2 | corpus.json、用户术语约束 | translation.json | W3-corpus-sha256 |
| W4 | align 保真对齐 | W3 | corpus.json、translation.json | bilingual.json | W4-translation-sha256 |
| W5 | result、artifact hash、原快照 audit | W4 | bilingual.json、全部轨迹 | result.json | W5-bilingual-sha256-run-id |

同一失败事件只写一条 failures，以 retry 记次数。已完成 W1/W2 不重复抓取；缓存查找必须匹配 source/corpus hash。失败依赖不会放行下游；只有显式 optional 的 skipped 依赖可例外。

## 3. 来源与数据传递

| from → to | 字段映射 | 完整性校验 | 权限 |
|-|-|-|-|
| W1→W2 | source_sha256→snapshot_sha256；final_url→source.url | 文件字节 hash 相同；meta URL 非空 | green 仅当前合法页面 |
| W2→W3 | blocks[]→paragraphs[]；metadata→metadata | ID 数量、顺序、metadata 原值一致 | yellow 术语出域前脱敏 |
| W3→W4 | corpus_sha256→corpus_sha256；target→target | 版本相同；缺/重/乱 ID 为零 | green |
| W4→W5 | paragraphs→result.paragraphs | 每字段原样、artifact hash、原快照重算 | green |

`red` 的登录 cookie、个人数据、受限全文禁止传第三方翻译接口或跨站；本 Skill 无外部翻译 API 依赖。`yellow` 需先按任务规则脱敏。同步冲突保留两边内容、版本和 hash，标 conflict 交人工，不自动覆写。

## 4. 失败识别—动作—恢复表

| kind | 识别信号（至少一项，同时须排除正文完整情形） | 动作 | 状态/恢复点 |
|-|-|-|-|
| login_expired / second_factor_required | HTTP 401；密码输入；session expired；正文不足 | 保留最终 URL 与已得文件，停止，要求人工正常认证/2FA | blocked；认证后 W1，已有未受影响产物保留 |
| paywall / permission_denied / access_control | 402/403/407；订阅购买提示且正文不全；Access denied | 不绕过；写缺少的订阅/权限，正文不称完成 | blocked/partial；合法权限后 W1 |
| cross_domain_redirect | 最终 netloc 与请求不同 | 不继续抽取；人工确认最终域和权限后用新 URL 起独立抓取 | failed；W1 |
| dynamic_render_failed | 主要只有 script/骨架，正文块 0 | 用平台浏览器等待正文并保存 DOM，stamp 后重跑；不拿 JS 文本当正文 | failed；W1→W2 |
| lazy_load_unresolved | data-src/data-original 且 src 为 data/placeholder | 滚动至元素、等待加载、重存；未解决注明图/表缺口 | issues/partial；W1/W2 |
| pagination | link/a rel=next 或分页 next class | 逐页编号抓取并检查衔接；未齐全前 complete=false | partial；下一未抓页 W1 |
| page_changed / missing_article_element | 主根无正文块、原选择器不存在 | 保存 root_dom_path/excluded；人工判页面改版，新增适配+正向/变异 bench | failed；W2 |
| abstract_only | 只有摘要及至多一个其他正文块 | 回全文链接/合法全文快照，不以摘要充正文 | failed/partial；W1 |
| timeout / network_error | socket timeout、URLError、5xx | 仅幂等 GET 一次有界重试；保留请求与异常，不无限循环 | failed；W1 |
| rate_limited | HTTP 429、Retry-After | 遵循 Retry-After 或指数退避，到上限停止 | failed/blocked；W1 |
| oversized_page | 字节数超过 max-bytes | 不写截断正文；调整有界预算或用浏览器真实 DOM | failed；W1 |
| unversioned_snapshot | meta hash 缺失、空 HTML、文件 hash 不符 | 拒绝抽取；重新取得真实非空快照并 stamp/fetch | failed；W1 |
| translation_interrupted | target 空、translation 文件缺失/JSON 损坏 | 保存已译条目，按 corpus 缺 ID 续写 | partial；W3 |
| alignment_interrupted / paragraph_misalignment | 缺/重/乱/额外 ID，corpus hash 不符 | 不按位置强配；恢复原顺序/版本后 align | partial；W3→W4 |
| 公式/数字/单位破坏 | protected token source/target 计数不同 | 从 quote/formulas 原样恢复，重跑 align；不靠领域常识猜 | issues/partial；W3 |
| 表格变形 | Markdown 行列与 table.n_rows/n_columns 不同 | 以 table.rows 修复同形 Markdown；原 HTML 不动 | issues；W3 |
| 元数据改写 | 作者/刊名/年/DOI 与 corpus 不同 | 恢复 meta 原值，源未报告显式 null | issues；W3 |
| sync_conflict | 源和目标均有独立修改 | 留两个版本与 hash，人工裁决，不覆盖 | blocked；W5 |
| field_missing / field_type_error | 必需字段缺、计数非整数、hash 非 64hex | 真实字段补齐或 null+not_checked；不填默认值伪装完成 | issues/partial；相应步骤 |

任何失败都必须有 `step/kind/signal/action/state/retry/idempotency_key`。恢复只从未完成步骤继续，`resume` 输出 waiting/blocked_deps 时不得强跑。

## 5. 交付前逐项核对

- [ ] `fetch/stamp` 成功，source URL/时间/版本/快照 hash 来自真实页面。
- [ ] `extraction_status=pass`；正文首中末抽查无导航/广告/相关推荐/参考文献列表。
- [ ] coverage 覆盖主体、章节、图表标题、行内引文、公式、上下标、脚注；缺项 not_checked。
- [ ] translation ID 与 corpus 同集合同序；术语同义词与首现策略已定义并执行。
- [ ] `align` 通过；语义抽查有足够 ID 与 change_log，不谎报机器语义证明。
- [ ] schema/trace/audit（带 snapshot+meta）全部零错误；result paragraphs 与 bilingual 完全一致。
- [ ] failures 覆盖实际异常；resume 无错误可执行项；artifact 文件存在且字节 hash 一致。
- [ ] gain 来自真实同输入同权限双跑，否则 not_measured，baseline/skill 均 null。
