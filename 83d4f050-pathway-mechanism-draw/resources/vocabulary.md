# 通路图元素词汇表

原则：每个图元都有语义；词表外关系一律画 `unknown`（点线+?）并写 `uncertainty`，绝不猜。机器判据见 `assets/edge_rules.json`（build/check 共用）；本文件给 LLM 抽取用触发措辞与放置规范。

## 节点类型（node.type → 图元 / 放置）

| type | 图元 | 放置 |
|-|-|-|
| ligand / small_molecule | 六边形橙/黄 | 最外层（小分子可跨膜） |
| receptor | 跨膜竖矩形蓝 | kind=membrane 且跨膜双线 |
| protein / tf | 圆角矩形蓝 | 任意（tf 胞质/核） |
| complex | 叠影矩形绿 | 任意（亚基–连接） |
| gene | 斜体平行四边形紫 | 核样区室（≠蛋白） |
| organelle / process | 椭圆橙 / 六边形灰 | 任意 |

## 相互作用语义（edge.relation → 触发措辞）

| relation | 触发措辞 |
|-|-|
| activates / inhibits | promotes, 促进, 上调 / blocks, 抑制, 下调 |
| binds | binds, recruits, 结合, 募集 |
| phosphorylates / ubiquitinates | 磷酸化 / 泛素化 |
| methylates / acetylates | 甲基化 / 乙酰化 |
| degrades | degrades, destabilizes, 降解 |
| translocates / transports | 转位, 入核 / 转运, 分泌 |
| unknown | regulates, affects 等无方向措辞 |

反馈环 → edge 加 `"feedback":true`（曲线，checker 不上游告警）。

## 区室（compartments，自上而下按机制流向）

`{"id","label","kind"}`；kind=membrane 画双层膜带，kind=unknown 画虚线框。常用序：extracellular → membrane → cytosol → nucleus。

## 命名规范

人源：基因 ALL-CAPS 斜体（*EGFR*），蛋白 Roman 首字母大写；鼠源相反；**以材料原文为准——label 逐字抄材料写法**，checker 逐字核验、未命中给 top-3 近似建议。基因/蛋白同名：拆 gene/protein 两节点或按语境取一，歧义写 uncertainty。同义名/旧名：label 用材料名，权威名（HGNC/UniProt）写 source；不发明材料外实体名；家族成员不合并（除非材料如此表述）。

## 覆盖清单（spec.required）

task/输入点名的必做分子/通路/事件逐条写入 `required`（用图面上的表层写法）。checker 审计缺项并列入 `entity.missing_required`；**有缺项时 result.json 禁止 answered/complete，必须 partial + 缺失清单**。
