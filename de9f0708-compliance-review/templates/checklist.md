# 学术规范与合规检查清单 v3

## 通用硬约束

1. 六个分面均有 `checked/partial/not_applicable/not_checked` 处置；未查写明原因。
2. 每条 issue：`type`、严重度、`confirmed/needs_review`、精确 location、逐字 quote、quote/source SHA-256、evidence、basis、可执行 fix。
3. 缺失项：`detection=absence` + `absence_evidence(searched=true,search_scope,source_sha256,expected,statement)`。
4. 风险出现 ≠ 违规成立；声明关键词出现 ≠ 授权覆盖。无法取得依据时不得 confirmed。
5. 完成前跑 `verify`、`coverage`、`schema`。

## integrity 学术诚信

- [ ] 图像/数据复用是否有原始出处、授权和明确说明？
- [ ] 重复发表是否有两篇实际文本及实质重合证据，而非相似主题？
- [ ] 作者贡献、署名、致谢、基金是否相互一致？利益冲突声明是否按实际要求处理？
- **交人工：** 原始实验记录、投稿史、署名贡献不可从稿件确认时。

## citation 引用规范

- [ ] 运行 `citations` 解析数字引用；悬空条目逐条补条或改号。
- [ ] 存在性/元数据来自实际题录来源，未获得的 DOI/题名不猜。
- [ ] 本文论断和被引主张双 span 对照对象、方向、条件、强度。
- [ ] 格式差异仅在目标规范明确要求时判 normative_issue。

## privacy 隐私与数据合规

- [ ] 运行 `privacy`；直接标识符和受限数据逐条核对，不只看“已脱敏”声明。
- [ ] 伦理/同意/授权是否覆盖当前主体、数据类型、公开/共享范围？
- [ ] 替换为研究代码、泛化地址、删除直接标识；链接表与分析数据分离并限权。
- [ ] 无名身份、准标识符组合、图像/声音/基因组是否明确列入人工检查？
- **输出控制：** 受限 quote 只在受控产物；对外清单用哈希/定位/替代文本，禁止上传。

## copyright 版权与许可

- [ ] 运行 `license`；每个第三方图/表/代码/数据集是否有 creator/title/source/license/permission？
- [ ] CC 许可版本、署名、NC/ND/SA 条件是否与实际使用一致？ND + 改作需单独授权。
- [ ] 无复用依据时给出补授权或用原创/开放素材替换的具体位置。
- [ ] 文本无法证明像素复用或代码相似，未做取证即 unchecked。

## ethics 伦理审查

- [ ] 涉及人/动物时，审批主体、批件编号、知情同意/豁免是否与实际设计一致？
- [ ] 风险、获益、招募和隐私处理是否一致，是否出现超出审批范围的用途？
- [ ] 只有“已获批”而范围不明时设 needs_review，fix=verify/add；不替代伦理委员会。

## submission 投稿要求

- [ ] 实际指南的 source/version/date 是否记录？无指南则本分面 not_checked。
- [ ] 指南拆为 `required_pattern/required_section/max_words/max_pages` 后运行 `guidelines`。
- [ ] 每条 pass/issue 是否有 actual/limit、稿件映射、条款定位和修复动作？
- [ ] 字数算法与官方口径不一致时明确降级，不把本工具计数冒充官方结果。

## 严重度

- `critical`：已核实的直接标识泄露或严重复用/伦理风险，需要立即停止公开/传播并人工处置。
- `major`：授权、伦理、引用、许可或投稿关键依据缺失/冲突，通常可补救。
- `minor`：不影响实质合规判断的局部格式问题。
- 扫描候选一般先 `needs_review`；严重度看实际影响，不随误报抑制而随意降级。
