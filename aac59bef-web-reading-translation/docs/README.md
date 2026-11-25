# 网页文献阅读与翻译：运行与复用说明

版本 3.0.0；result schema 2.0.0。主调用说明见 `SKILL.md`。

## 安装与支持边界

无需安装第三方依赖，Python 3.9+ 标准库即可运行全部脚本与 bench。网络权限只用于用户指定网页的幂等 GET；登录/订阅依赖用户已有合法权限。静态页面直接 `fetch`；动态页面由平台现有浏览器保存最终 DOM 后 `stamp`，脚本本身不内置浏览器、不执行 JS、不自动翻译。

已在开发烟测中跑通 arXiv HTML（含 LaTeXML 公式、表格、作者脚注）；并使用本地 HTTP 案例覆盖导航/推荐/参考文献排噪。其他出版社并非无条件支持：主节点无正文、内容仅在 PDF/图片、未解决分页/懒加载均须降级。站点改版时保留快照与 DOM 定位，新增规则后必须通过 bench，不能凭单一 URL 推断全站成功。

## 命令速查

```bash
# 公开静态 HTML
python3 scripts/webread.py fetch URL --out source.html --meta fetch.json
# 浏览器渲染/题面快照
python3 scripts/webread.py stamp source.html --url URL --out fetch.json \
  --capture-method browser_rendered --capture-notes '等待、滚动、分页实录'
# 正文、元数据、章节、公式、表格、图注、脚注与来源锚点
python3 scripts/webread.py extract source.html --meta fetch.json --out corpus.json
# 人工/Agent 写 translation.json 后逐段校验与合并
python3 scripts/webread.py align corpus.json translation.json --out bilingual.json
# DAG、恢复点、schema、从原 HTML 重算审计
python3 scripts/auto_tool.py trace result.json
python3 scripts/auto_tool.py resume result.json
python3 scripts/auto_tool.py schema result.json
python3 scripts/auto_tool.py audit result.json bilingual.json --snapshot source.html --meta fetch.json
# 有真实同输入同权限双跑时
python3 scripts/auto_tool.py compare baseline-run.json skill-run.json --out gain.json
```

命令输出单行 JSON，0 表示机检无错误；`extract` 有分页/懒加载 `issues` 时文件仍写出，`complete=false`；`align` 缺段/保真错误时也尽量写 `bilingual.json` 供定位修复，但返回 1。失败不能靠 `|| true` 隐藏。

## translation.json 可编辑格式

```json
{
  "schema_version":"2.0.0",
  "corpus_sha256":"从 corpus.json 复制",
  "metadata":{"title":"原题名","authors":["原作者"],"journal":"原刊名或 null","year":"原日期或 null","doi":"原 DOI 或 null"},
  "paragraphs":[{"id":"B0001","target":"对应译文；不得增删 ID"}],
  "glossary":[{
    "source":"graph neural network", "source_variants":["graph neural net"],
    "target":"图神经网络", "first_target":"图神经网络（GNN）",
    "target_variants":["图神经网络（GNN）","GNN"],
    "occurrence_policy":"first_full_then_abbreviation"
  }],
  "semantic_review":{"status":"reviewed|not_checked","paragraph_ids":[],"notes":"记录实际复核，不影响机器字段"}
}
```

上例仅演示接口，不是任何正式案例译法答案。`target_variants` 是允许的显式后文形式，不是任意同义词豁免。默认策略要求每个出现源术语/登记同义词的段落至少有一个约定目标形式；首现策略要求第一处使用 `first_target` 或 `target`。

## corpus/bilingual 定位字段

- `source.requested_url/url/http_status/fetched_at/page_version/snapshot_sha256/capture_method`：区分原请求、最终 URL、页面版本、抓取方式。
- `blocks[].id/order/kind/section_path`：顺序、块型与章节。
- `dom_path`：含同标签序号的完整路径；`html_anchor` 优先使用原元素或祖先的真实 ID，无 ID 时使用工具块 ID，不冒充页面原锚点。
- `char_start/char_end`：在按双换行拼接的 `blocks[].text` 中的区间，0 基、末端排除。
- `quote/text_sha256`：规范化 DOM 文本（公式/上下标结构化）的逐段证据及哈希。引用是源正文的可重算表示，不是“截图已经证明”。
- `snapshot_sha256/corpus_sha256/full_text_sha256`：分别为原始字节、规范化语料对象、拼接正文的版本锁。
- `align` 的 `verification.semantic_fidelity` 永久为 `not_checked_by_tool`；语义复核写 `translation.semantic_review` 与 result 的 change/uncertainty，避免把 token 相等当成语义正确。

## result status 与异常

- `pass`：已知范围无抽缺失、所有原文块有译文、机检无警告、全部步骤 done、快照能重算、产物 hash 一致。
- `issues`：主体完成但分页/懒加载/语义或非关键字段仍有明确问题；问题写 failures/unchecked。
- `partial`：只有部分段落或部分页面；`missing_blocks`/unchecked 必须能枚举缺口，保留 resume_point。
- `failed`：第一步也可能失败。source 尚不存在的字段显式 null，failures 写信号、动作和权限需求，不编 URL 哈希或正文。

完整异常处置见 `templates/flow_spec.md`，覆盖题面要求的登录失效、懒加载、分页、元素缺失、超时、权限不足、付费墙、跨域、动态失败、翻译中断、段落错位和冲突。

## 同输入对照 run-record

baseline 和 skill 各写一个 JSON，格式如下；所有数字来自对应实际产物/日志，不是预估值：

```json
{
  "case_id":"同一 case",
  "run_id":"本次唯一 ID",
  "source_sha256":"两次运行相同的快照 sha256",
  "permissions":["http:read","filesystem:write"],
  "totals":{
    "expected_body_blocks":0, "extracted_body_blocks":0,
    "translated_body_blocks":0, "quote_verified_blocks":0,
    "protected_tokens_total":0, "protected_token_violations":0,
    "glossary_checks":0, "glossary_consistent_checks":0,
    "manual_actions":0, "repeated_fetches":0, "elapsed_seconds":1
  },
  "evidence":{"result_path":"/path/result.json","log_path":"/path/run-log.json"}
}
```

`expected_body_blocks` 应由同一参考语料确定，不能为了给 baseline 低分更改分母。`quote_verified_blocks` 须实际回原文核对，工具 vars 只计算比率。`compare` 会校验 case、页面版本、权限、独立 run ID、证据可读性与计数上界，记录证据 SHA256，并输出质量差值与人工动作/重复抓取/耗时节省。它不声称官方榜单，不取代平台白板。

## 最小示例与自测

`bench/fixtures/article.html` 是合成最小网页，含元数据、摘要、三章节、MathML、上下标、单位、表格、图注、脚注变体、导航与参考文献排噪。bench 动态生成译文与 result，不附正式案例答案。

```bash
python3 bench/bench_run.py                       # 终端逐项 PASS + X/Y
python3 bench/bench_run.py --report bench/last_report.json
```

bench 启本地 HTTP 服务，覆盖正向零误杀与登录/401、403 类权限逻辑、429、跨域、超时、懒加载、分页、动态骨架、摘要页、缺元素、哈希篡改、错版/漏重乱序、公式/数值/单位/表格/作者/术语变异，以及非同权限/同版本伪对照。

## 复用和维护

- 新增站点优先复用 `article/main` 与正文类名，不要以“文字最多”直接替代正文判定。
- 修改抽取规则后同时跑完整 bench 和目标原 HTML 的 audit；新噪声规则必须有“正常正文不误删”的正向用例。
- 修改 token 规则会改变 `corpus_sha256`，旧译文必须回源重跑 align；不能沿用旧哈希。
- 新异常先归一到 `scripts/auto_tool.py:FAILURE_KINDS`，写识别 signal、可执行 action、状态和恢复点，并加变异 bench。
- 资源、安装及浏览器可选性见 `environment/resources.yaml`；术语与同义词可在每个案例的 translation.json 中迁移复用。
