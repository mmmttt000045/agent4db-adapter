| benchmark | subset | DBs | tasks | with knowledge % | uses | distinct | uses repeating % | uses/item | sharing tasks % |
|---|---|---|---|---|---|---|---|---|---|
| bird_dev | all | 11 | 1534 | 90.4 | 2681 | 2078 | 22.5 | 1.29 | 40.9 |
| bird_dev | calculations | 11 | 1534 | 36.4 | 628 | 549 | 12.6 | 1.14 | 19.0 |
| bird_dev_terms | all | 11 | 1534 | 83.4 | 2224 | 1598 | 28.1 | 1.39 | 50.7 |
| bird_dev_terms | calculations | 11 | 1534 | 35.1 | 603 | 445 | 26.2 | 1.36 | 36.2 |
| livesqlbench_full | all | 22 | 600 | 81.8 | 1365 | 689 | 49.5 | 1.98 | 78.2 |
| livesqlbench_full | calculations | 22 | 600 | 64.2 | 748 | 348 | 53.5 | 2.15 | 78.7 |
| livesqlbench_full | all|Management | 22 | 189 | 73.0 | 309 | 249 | 19.4 | 1.24 | 39.1 |
| livesqlbench_full | calculations|Management | 22 | 189 | 46.0 | 143 | 108 | 24.5 | 1.32 | 42.5 |
| livesqlbench_full | all|Query | 22 | 411 | 85.9 | 1056 | 609 | 42.3 | 1.73 | 76.5 |
| livesqlbench_full | calculations|Query | 22 | 411 | 72.5 | 605 | 326 | 46.1 | 1.86 | 72.8 |
| livesqlbench_full | direct_only | 22 | 600 | 81.8 | 767 | 552 | 28.0 | 1.39 | 54.0 |
| livesqlbench_lite | all | 18 | 270 | 96.7 | 758 | 458 | 39.6 | 1.66 | 78.2 |
| livesqlbench_lite | calculations | 18 | 270 | 87.0 | 466 | 245 | 47.4 | 1.9 | 80.0 |
| livesqlbench_lite | all|Management | 18 | 90 | 92.2 | 174 | 153 | 12.1 | 1.14 | 34.9 |
| livesqlbench_lite | calculations|Management | 18 | 90 | 78.9 | 104 | 90 | 13.5 | 1.16 | 36.6 |
| livesqlbench_lite | all|Query | 18 | 180 | 98.9 | 584 | 414 | 29.1 | 1.41 | 64.0 |
| livesqlbench_lite | calculations|Query | 18 | 180 | 91.1 | 362 | 225 | 37.8 | 1.61 | 64.6 |
| livesqlbench_lite | direct_only | 18 | 270 | 96.7 | 510 | 371 | 27.3 | 1.37 | 60.9 |
| spider2_lite | all | 158 | 547 | 19.6 | 107 | 70 | 34.6 | 1.53 | 52.3 |
| spider2_lite | calculations | 158 | 547 | 19.6 | 107 | 70 | 34.6 | 1.53 | 52.3 |

Share of the n-th task's knowledge uses already needed by an earlier task on the same database (random orders):
- bird_dev_terms: n=2: 3.0% (11 DBs), n=5: 8.9% (11 DBs), n=10: 14.8% (11 DBs), n=20: 23.5% (11 DBs), n=50: 31.0% (9 DBs), n=100: 32.9% (8 DBs)
- livesqlbench_full: n=2: 9.8% (22 DBs), n=5: 29.8% (22 DBs), n=10: 48.4% (22 DBs), n=20: 65.2% (16 DBs)
- livesqlbench_lite: n=2: 8.7% (18 DBs), n=5: 29.5% (18 DBs), n=10: 47.3% (18 DBs)
- livesqlbench_full knowledge base: {'kb_entries': 1369, 'kb_types': {'calculation_knowledge': 544, 'domain_knowledge': 577, 'value_illustration': 248}, 'matched_in': 'normal_query'}
- livesqlbench_lite knowledge base: {'kb_entries': 1082, 'kb_types': {'calculation_knowledge': 432, 'domain_knowledge': 463, 'value_illustration': 187}, 'matched_in': 'query'}
