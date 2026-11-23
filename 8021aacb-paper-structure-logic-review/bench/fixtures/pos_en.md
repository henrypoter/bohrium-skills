# Abstract

This paper studies task scheduling in data centers. Preliminary experiments suggest that the proposed method may reduce average latency under the tested workloads.

# 1. Introduction

Scheduling latency is a key bottleneck in modern data centers. We study how to reduce scheduling latency under heterogeneous workloads and propose a greedy scheduler that orders tasks by arrival time.

# 2. Related Work

Prior work relies on heuristic allocation or static priority policies, which degrade under dynamic workloads.

# 3. Method

The scheduler sorts tasks by arrival time and assigns each task to the earliest idle node. The time complexity is O(n log n).

# 4. Experiments

On three self-built testbeds, average latency drops by 12% (Table 1). The results show that latency decreases under most tested workloads.

# 5. Conclusion

Under our experimental conditions, the results suggest that the method may reduce average latency. The conclusion is limited to the tested workloads; future work includes a theoretical lower-bound analysis.
