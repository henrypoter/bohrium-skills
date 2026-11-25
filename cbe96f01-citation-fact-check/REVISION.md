# 修订说明（v2 → v3：引用与事实核验）

## 对齐判对标准

v2 只核“issue 的 quote 是否在稿件中”，没有自动核被引来源证据、语义支持标签或版本状态。v3 以**稿件论断与来源证据双侧定位、语义一致性、可重跑记录**为主线：每条结论有 claim/source 两侧页段锚点、哈希、支持理由和来源元数据，换一人可从相同快照重跑。

## 实际效果（40）

- `locate`：同时校验 `claim_quote` 和 `source_quote`，输出页、段、occurrence、quote SHA-256 和全文 SHA-256；重复 quote 不默认取第一次，严重歧义必须消歧。
- `align`：强制 full/partial/none/unknown 和 support_rationale；对 full 标签下的否定方向、全称/治愈外推、相关到因果、显式中英文样本量矛盾作保守拦截。
- `provenance`：按带来的 registry 快照核 canonical DOI、预印本/正式版、出版状态、更正、关注声明、撤稿和访问权限；明确不是实时网络声明。
- `coverage`：六类及 methods/results/discussion 显式记录，避免“没有问题=没查”。
- `gate`：交叉校验 claims/issues/sources，锚点全文哈希必须对应 manuscript_version 和注册 source 内容哈希；partial/none 必须关联问题，unknown/权限不足必须有边界记录。

## 使用增益（25）

同源快照一次登记后供定位、语义和版本检查复用，减少重复检索。定位错误、歧义 occurrence、版本冲突和权限缺口直接以 source_id/claim_id 返回，降低逐条回查和补写依据成本。平台 `gain` 只记录同稿件、同工具权限、同预算真实对照，bench 通过率不被冒充召回或效率增益。

## 创新增益（15）

| 新增能力 | 方法改进 | 创新证据与边界 |
|-|-|-|
| 段落级双侧证据定位 | 从“稿件有这句”升级为“双方哪一句相互支持”；重复引文要求 occurrence | bench 正向双侧定位/消歧，变异删句/错哈希/歧义均命中；不声称 OCR 完整 |
| 引文—结论语义标签检查 | 分开 full/partial/none/unknown，用保守方向/范围/因果/样本量规则抓错标，同时允许合法 partial/none | 正向和定向变异可复跑；规则不是通用 entailment，仍需人工判断对象/终点/限定语 |
| 来源版本与撤稿状态核验 | DOI+版本+出版/撤稿状态+证据日期/URL+访问权限联合记录 | 预印本不一致、撤稿、未知状态和权限变异覆盖；只核实际快照，不造实时状态 |
| 可重跑交付总闸 | 原 output_contract、run/tool、稿件和来源全文哈希、双侧引句哈希、issue 链接全链绑定 | 变异错误来源哈希、缺版本、撤稿无 issue、unknown 无 uncertainty 均拦截 |

## 可靠体验（10）

异常表逐项补齐原文取不到、PDF 无法解析、引文严重歧义、来源撤稿/版本不一致、数据库权限不足，并补图表/补充材料和语言混杂。每项规定恢复动作、access/support/review_status、partial/unchecked/uncertainty 和禁止推断。`--allow-partial/--allow-unknown/--allow-incomplete` 只保留未完成事实，不把未知改判通过。

## 生态贡献（10）

工具仅标准库，无个人路径和隐性服务依赖；checklist、claims/sources/registry 接口、严重度规则、异常表、合成 fixture 与 bench 均可复用。命令不依赖正式案例答案。

## 相对基础 Agent 的边界与未解决差距

- 通用语义蕴含、图表 OCR、全文取得和实时撤稿状态仍受材料/工具权限限制；规则通过不代表语义和支持关系必然正确。
- 只有实际保存并哈希的快照可复跑；付费墙和不可得来源只能 partial，不能声称完整核验。
- 尚无平台固定三案例三次重复的新召回、定位精度、误报率和人工修改量对照；不能据此宣称超过榜首。后续优先用平台 traces 量化跨学科与仅摘要/扫描件案例的定位成功率及误报控制。
