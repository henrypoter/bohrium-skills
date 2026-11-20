# bohrium-skills — 文献检索（科研检索领域）

Bohrium 产品周赛·第四周「科研检索：找到文献，也保留筛选依据」12 个参赛 Skill。
每个子目录是一个可独立加载的 Skill，含 `SKILL.md`、`scripts/search_tool.py`、`templates/`（协议/理由码/工作表）、`bench/`（自测夹具）、`REVISION.md`（v1→v2 修订理由）。

## 目录

| 子文件夹 | 题目 |
|-|-|
| `baddb1f9-literature-search/` | 文献检索领域总课题 |
| `5b90f5e9-systematic-search-screening/` | 系统性文献检索与纳排筛选 |
| `60a8202d-citation-tracking/` | 引文追踪与关联文献发现 |
| `ad3e9357-patent-search/` | 专利与技术文献检索 |
| `802a7115-cross-lingual-search/` | 跨语言文献检索 |
| `e7598a44-question-driven-search/` | 科研问题驱动检索 |
| `2dd1f64c-screening-ranking/` | 文献筛选与智能排序 |
| `a2909a72-academic-literature-search/` | 学术文献检索 |
| `0467f5db-coverage-gap-analysis/` | 检索覆盖率与遗漏分析 |
| `1e85736f-literature-tracking-alert/` | 最新文献发现与追踪 |
| `bace1c46-literature-quality-assessment/` | 文献研究质量评价 |
| `5c918ff0-multi-database-search/` | 多数据库联合检索 |

## 自测
```bash
cd <子文件夹> && python3 bench/bench_run.py   # 10/10
```

## 说明
- 夹具（`bench/fixtures/`）为自测与调用示例，非正式案例结果。
- 处理的是给定题录的有限快照，不声称在线数据库全覆盖或全局召回率。
