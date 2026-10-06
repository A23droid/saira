# SAIRA Benchmark Results

### TABLE 1: Paper Chat performance

| Architecture | P50 (ms) | P95 (ms) | P99 (ms) | Throughput (req/s) | Failure % |
|---|---|---|---|---|---|
| dbms | 33.9 | 13299.8 | 15172.2 | 0.16 | 25.0 |
| cloud | 8.1 | 22.4 | 23.9 | 0.12 | 0.0 |

### TABLE 2: Project Chat performance

| Architecture | P50 (ms) | P95 (ms) | P99 (ms) | Throughput (req/s) | Failure % |
|---|---|---|---|---|---|
| dbms | 22.1 | 207.4 | 223.8 | 0.06 | 0.0 |
| cloud | 7.9 | 19.6 | 20.7 | 0.03 | 0.0 |

### TABLE 3: Resource utilization

| Architecture | CPU Avg (%) | CPU Peak (%) | Memory Avg (MB) | Memory Peak (MB) |
|---|---|---|---|---|
| dbms | 10.3 | 100.0 | 22118 | 22315 |
| cloud | 13.9 | 68.3 | 22242 | 23005 |

### TABLE 4: Ingestion

| Architecture | Corpus | Total Time (s) | Time/Paper (s) |
|---|---|---|---|
| dbms | 2 | 25.0 | 12.5 |
| cloud | 5 | 33.1 | 6.6 |
