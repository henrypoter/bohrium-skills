# 修订说明（v5.0.0，对齐“串得起来 / 对得上原文 / 留得下来 / 讲得清楚”）

## 新增答案—原文强绑定

- 保留已有打开→定位→选中→问答→批注→导出闭环和四级锚点，没有替换阅读客户端。
- 每次成功打开记录材料 `path/bytes/sha256/format`；QA 新增 `answer_id/answer_sha256/document_sha256/selection_sha256`，证据新增 `evidence_id/answer_id/document_sha256`，并同步进入 result_draft 与 W3C annotations。
- 新纯标准库命令：`python3 scripts/delivery_guard.py audit --workdir W --result /app/output/result_draft.json`。它用独立匹配实现重读材料、pages.jsonl、session 和导出，检查答案改字、选区变化、原文替换、引文脱锚、材料版本丢失、批注答案改写；fuzzy/page_line_only 不得通过。报告落 `W/binding_audit.json`，失败 exit 1。
- `result.json` 新增 `schema_version/tool_version/run_id/material_version/open_error/artifact_manifest/status_reason`；`export --case /input/case.json` 自动保留 case_id 与 output_contract 键生成最终文件，减少手工拼装漏字段。

## 加密与超大文件的可靠处置

- 新纯标准库命令：`python3 scripts/delivery_guard.py inspect FILE [--max-file-mib 64]`；分别返回 `encrypted_pdf`、`oversized_file`、`material_missing`，附 material_version 和接管动作，正常文本不误报。
- `reader_client.py open` 内部执行同一预检，默认上限 64 MiB / 2000 页；新增 `--max-file-mib/--max-pages`。还检查 pdftotext 返回码与 stderr，区分密码/加密、其他解析错误和超时，不再忽略非零退出码。
- 打开失败会保存结构化 `last_open_error` 并清空旧页面/Question/批注，**仍允许 export**：交付 status=partial、status_reason/open_error、空 answers 和材料版本，而不是留下旧会话冒充本次成功或根本没有产物。

## 相对基础 Agent 的边界与价值

基础 Agent 往往能给出页码或引文，但不稳定绑定“同一答案文本—同一选区—同一证据 id—同一材料哈希—同一批注导出”，也很难保证加密/超限失败有统一代码和保底终稿。本 Skill 把绑定和失败降级变成独立、可复跑、可变异攻击的检查。哈希只用于发现漂移，不是防恶意重签的密码学凭证；机械核验不能判断一段引文是否在科学上充分支持答案，OCR、图表理解和学科正确性仍不在范围内。

## 验证记录

`python3 bench/bench_run.py`：**19/19**（原支持度 7 项 + 新 guard 12 项）全绿；`python3 bench/bench_delivery_guard.py` 可单独复跑新增项。包括正常文本含 `/Encrypt` 零误杀，以及加密、超限、答案改字、引文脱锚、原文漂移、选区漂移、缺材料版本、批注改答等必命中。该数字仅为本地确定性 bench，不是官方成绩或 LLM 语义正确性证明。
