# 返修交付自查清单（对应评分四问）

## 答得全
- [ ] 意见逐条编号核对，回复信条目数 == 意见数（verify coverage 无 fail）
- [ ] 每条意见内子要求逐条有结论，无合并遗漏；无笼统致谢句代替实质回应

## 改得准
- [ ] 回复信每处"已修改"锚点原样存在于修订稿（verify location 无 fail）
- [ ] 没改的写了理由（部分采纳/不采纳/无法执行）；实质性修改均在指定基线内

## 证得住
- [ ] 补实验/数据/文献类意见全部列入证据清单并标状态；无法补做写明原因与替代说明
- [ ] 反驳/无法执行条目含证据+替代方案+缓冲语（verify rebuttal_compliance 无 fail）
- [ ] 数字、术语、引用均出自材料本身，未新增材料外事实

## 对得上
- [ ] 回复信锚点 == 映射表锚点 == 修订稿原文；changes.diff 只含本轮真实改动
- [ ] 冲突意见已标注取舍；疑似误解（引文找不到）已按澄清/反驳处理
- [ ] verify tone 无对抗性措辞；锚点行号已回填（anchor_locations）
- [ ] result.json：output_contract 全字段 + case_id + 诚实 status/sources/uncertainty/change_log
