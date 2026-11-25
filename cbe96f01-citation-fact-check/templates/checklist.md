# 引用与事实核验清单（v3）

> 每条核“稿件论断—来源证据”一对，而不是只检查参考文献是否存在。双侧均保留页/段/occurrence、逐字 quote、quote 哈希与全文内容哈希。无全文/歧义/权限不足必须 unknown。

## 1. citation 引用支持

- [ ] 方向：促进/抑制、有效/无效、正/负是否一致，否定词是否漏读
- [ ] 对象：物种、人群、年龄、疾病亚型、体外/体内是否一致
- [ ] 条件：剂量、时间、终点、干预、对照、场景是否一致
- [ ] 强度：相关是否升级为因果；部分/亚组/初步是否升级为所有/必然/治愈
- [ ] 数量：样本量、比例、效应量、单位是否一致
- [ ] 结论：`full / partial / none / unknown` 及 support_rationale；partial/none 必须关联 issue
- [ ] 运行 `align`；通过规则后仍人工核语义，不把词法规则当蕴含证明

## 2. 双侧证据定位

- [ ] 稿件端：实际连续 quote + page + paragraph + occurrence + quote_sha256 + manuscript source_sha256
- [ ] 来源端：实际连续 quote + page + paragraph + occurrence + quote_sha256 + reference source_sha256
- [ ] 多个相同 quote 时明确 occurrence，不默认第一次
- [ ] source_id、DOI/URL、来源全文哈希可对应；issue 的 evidence 同样可定位
- [ ] 运行 `locate`；取不到或歧义仅 partial，绝不拼接不相邻原句

## 3. 来源可靠性与版本

- [ ] 实际版本：preprint-vN / accepted / published-vN；若预印本与正式版并存，记录引的是哪版
- [ ] publication_status、version、canonical_doi 与带来的 registry 快照是否一致
- [ ] retraction_status：not_retracted / retracted / corrected / expression_of_concern / unknown
- [ ] checked_at 与 evidence_url 是本次实际记录；不是虚构“数据库已查”
- [ ] access：open / paywalled / permission_denied / unavailable；权限不足写明只见摘要/元数据范围
- [ ] 运行 `provenance`；撤稿来源必须关联 issue，版本差异明确披露但不自动判错

## 4. fact 与 statistics 数字一致性

- [ ] 摘要、正文、表格、图注、数据集的样本量/效应值/CI/p/单位交叉一致
- [ ] 区分稿件自己的错误与稿件对被引研究的错误转述
- [ ] 图表或补充材料不可得列 unchecked，不推定一致或不一致

## 5. design 与 argument 论证链

- [ ] 方法设计是否支持当前结论所需的对照、独立性和因果强度
- [ ] 结论句 + 证据句对照，检查以偏概全、循环论证、缺对照、时间/场景跳跃
- [ ] 引文支持的子结论与作者新增推断分层呈现，不能整句一概判错

## 6. compliance 学术规范

- [ ] 署名/贡献、重复或重叠发表说明、数据代码可用性、伦理和利益冲突按材料适用性检查
- [ ] 仅在有期刊/机构/声明规范依据时写 norm_issue；缺材料写 evidence_gap，不直接认定违规

## 覆盖、严重度与交付

- categories 六类及 methods/results/discussion 均显式 checked/not_applicable/pending/unchecked；零问题不是漏查。
- `critical`：问题使核心结论不成立；`major`：重要支持不足/实质版本差异但可补救；`minor`：格式定位或建议。`suggestion` 只能 minor。
- confirmed 必须双侧定位完成；unknown/pending 必须进入 uncertainty。运行 `coverage`、`schema`、`gate` 后才交付。
