# 最小调用示例（示例，非正式案例结果）

材料为自拟短文 `mini.txt`：
```
光合作用是植物把光能转化为化学能的过程。
其光反应发生在类囊体膜上，产生 ATP 与 NADPH。

卡尔文循环在叶绿体基质中进行，固定二氧化碳。
每固定 3 分子 CO2 需要 9 分子 ATP 和 6 分子 NADPH。
```

调用（`$R` 见 SKILL.md）：
```bash
python3 scripts/delivery_guard.py inspect mini.txt
$R open mini.txt
$R search 卡尔文
$R select --quote "每固定 3 分子 CO2 需要 9 分子 ATP"
$R qa --question "卡尔文循环在哪里进行？" --answer "在叶绿体基质中进行。" \
      --evidence "卡尔文循环在叶绿体基质中进行，固定二氧化碳。"
$R note --page 1 --line 6 --text "核心数据点" --quote "卡尔文循环在叶绿体基质中进行"
$R status
$R resume
$R export --out /app/output --case /input/case.json
python3 scripts/delivery_guard.py audit --workdir /app/work/reader_session --result /app/output/result_draft.json
```

示意输出（示例）：
```json
{"ok":true,"pages":1,"text_status":"ok","session_health":"fresh"}
{"total":1,"hits":[{"page":1,"line":6,"text":"卡尔文循环在叶绿体基质中进行…"}]}
{"ok":true,"needs_confirmation":false,"selection":{"kind":"quote","anchor":{"physical_page":1,"line":7,"confidence":"verbatim"}}}
{"ok":true,"qa_id":1,"all_verified":true,"confidence":["verbatim"],"needs_confirmation":[]}
{"ok":true,"note_id":1,"anchor_confidence":"verbatim","needs_confirmation":false}
{"session_health":"ok","backup_exists":true,"reading_position":{"physical_page":1,"line":6},"resume_hint":"续读 p1:L6(note)","qa_needs_confirmation":[]}
{"ok":true,"resume_hint":"续读 p1:L6(note)","context_paragraph":"卡尔文循环在叶绿体基质…"}
{"ok":true,"reading_record":"/app/output/reading_record.md","annotations":"/app/output/annotations.json","status":"success","needs_confirmation":0}
```

示意 result.json 关键字段（示例；完整文件还含选区、证据 id/哈希、批注与制品清单）：
```json
{"case_id":"example-demo","status":"success","schema_version":3,"tool_version":"5.0.0",
 "run_id":"reader-<材料哈希与打开时间导出>","material_version":{"path":"mini.txt","bytes":256,"sha256":"<示例哈希>","format":"text"},
 "answers":[{"answer_id":"qa1","answer_sha256":"<示例哈希>","question":"卡尔文循环在哪里进行？","answer":"在叶绿体基质中进行。",
   "evidence":[{"evidence_id":"qa1-ev1","answer_id":"qa1","quote":"卡尔文循环在叶绿体基质中进行，固定二氧化碳。","verified":true,
     "confidence":"verbatim","needs_confirmation":false,"anchor":{"physical_page":1,"line":6}}]}],
 "sources":[{"path":"mini.txt"}],"uncertainty":[],"needs_confirmation":[]}
```

反例：`verify --quote "光反应发生在线粒体膜上"` 返回 `{"verified":false,"needs_confirmation":true,"locations":[]}`（退出码 1=需人工确认，非阻断导出），论断须改写或标“材料未报告”。
