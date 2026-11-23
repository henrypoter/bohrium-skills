# 最小调用示例（示例，非正式案例结果）

材料为**自拟合成图**（V = 2.5·t + 10，仅演示接口，输出均为示例）：
`python3 -c "import matplotlib.pyplot as plt;plt.plot([0,2,4,6,8,10],[10,15,20,25,30,35],'ro-');plt.xlabel('t (s)');plt.ylabel('V (mV)');plt.savefig('/app/work/demo.png',dpi=150)"`

```bash
python3 scripts/init_result.py --case /input/case.json --out /app/output/result.json
python3 scripts/probe.py /app/work/demo.png
python3 scripts/ocr_words.py /app/work/demo.png > /app/work/ocr.json
```

从 `ocr.json` 的 `tick_candidates` 取刻度词质心像素，写 spec（像素值仅为演示）：
```json
{"figure":"demo.png","panels":{"a":{"x":{"ticks":[[100,0],[176,2],[252,4],[328,6],[404,8],[480,10]],"type":"auto","unit":"s"},"y":{"ticks":[[640,10],[523,15],[406,20],[289,25],[172,30],[55,35]],"type":"auto","unit":"mV"},"points":[{"id":"red#peak","x_px":480,"y_px":55,"y_axis":"left","yerr_px":[40,70]}]}}}
```

```bash
python3 scripts/axisfit.py /app/work/spec.json --rules scripts/rules.json > /app/work/calib.json
python3 scripts/trace.py /app/work/demo.png colors   # -> 主色簇 rgb
python3 scripts/trace.py /app/work/demo.png extract --rgb 214,39,40 > /app/work/t1.json
# spec 的 panel a 加 "trace_files":{"red@left":"/app/work/t1.json"} 后重跑 axisfit
```

示意输出（示例）：x/y 轴 `type:"linear"`、`r2:1.0`、`spacing` 全一致、无 `dropped_ticks`；
点 `red#peak` → `{"x":10.0,"y":35.0,"yerr":[34.36,35.64],"evidence":"inferred"}`；
`traces["red@left"].data ≈ [[0,10],...,[10,35]]`。改错某刻度值再跑可自检：`dropped_ticks` 记录剔除并告警。

最后填 result.json 三档标注与 sources，`--finalize` 打印 OK 即完成（示例流程）。
