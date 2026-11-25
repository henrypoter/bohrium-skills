# 可复用专利工作表

以下列名可直接用于 CSV；原始响应仍以 JSON/文本文件和 SHA-256 为准，CSV 不能替代逐字回源。

## 1. candidates.csv
```text
record_id,input_number,number_role,publication_number,application_number,grant_number,priority_numbers,title,decision,reason_code,relevance_reason,source_id,uncertainty
P1,US 1000000 B2,publication,US1000000B2,US16123456,US1000000B2,US62123456,Example,include,P-NUM,号码与主题均命中,S1,
```

## 2. evidence.csv
```text
owner_id,evidence_type,source_id,field,quote,locator,start,end,access
P1,relevance,S1,documents[0].abstract,"Exact source sentence.","abstract sentence 1",,,green
P1,claim_v1,S1,documents[0].claim_v1,"1. Exact claim text.","claim 1",,,green
```
`quote` 必须是原字段内唯一逐字子串；若不唯一，填字符 `start/end`。页或 OCR 段不得合并成一条引文。

## 3. families.csv
```text
family_scope,group_id,member_ids,basis,complete,claim_scope_equal
simple,F1,P1|P2,identical normalized priority set,false,false
extended,E1,P1|P2|P3,shared normalized priority,false,false
```
以 `family` 命令重算输出为准；不能手工删掉不便解释的成员。

## 4. legal_events.csv
```text
record_id,event_status,effective_date,source_id,official,as_of,verification,current_status,uncertainty
P1,Grant,2020-01-02,S1,true,2026-11-25,official_events_only,unknown,历史事件不证明当前有效
```

## 5. source_access.csv
```text
source_id,name,version,query_date,path,sha256,access,allowed_fields,retention,confidentiality_action
S1,Authorized snapshot,v1,2026-11-25,/app/work/source.json,<64hex>,yellow,documents[].title,per task policy,仅展示白名单字段
```

## 6. iterations_and_misses.csv
```text
iteration,query_id,change,new_record_ids,zero_hit_or_error,miss_code,miss_attribution,stop_decision
1,Q1,initial number query,P1,0,,,continue to topic
2,Q2,add classification, ,0,M2,Q1 only searched title,stop: authorized snapshot exhausted
```

## 7. gain.csv
```text
case_id,input_hash,permissions,qrels_ref,k,arm,ranking,tool_calls,manual_checks,seconds,platform_run_id
fixture,<sha256>,green-only,qrels.json,2,baseline,P3|P2|P1,6,4,,not-measured
fixture,<sha256>,green-only,qrels.json,2,skill,P1|P2|P3,4,2,,not-measured
```
本地 qrels 与平台正式对照分开；没有真实运行时 `gain.mode=not_measured`。
