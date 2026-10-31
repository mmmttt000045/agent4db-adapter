# Fig. 6: published-memory comparison

This is the corrected single-period cohort with common environment feedback for all four methods. Only complete matched repeats enter accuracy; every paid attempt enters spending.

Complete matched repeats: 1. Observed ranges are not confidence intervals.

| Dataset | Method | Held out | Non-breaking | Covered breaks | All settings |
|---|---|---:|---:|---:|---:|
| synthetic | ACE | 100.0% | 100.0% | 73.3% | 77.8% |
| synthetic | AWM | 100.0% | 75.0% | 80.0% | 72.2% |
| synthetic | G-Memory | 66.7% | 33.3% | 40.0% | 33.3% |
| synthetic | MAVRA | 100.0% | 100.0% | 80.0% | 86.1% |
| tpch | ACE | 100.0% | 100.0% | 40.0% | 66.7% |
| tpch | AWM | 100.0% | 100.0% | 70.0% | 87.5% |
| tpch | G-Memory | 100.0% | 100.0% | 80.0% | 83.3% |
| tpch | MAVRA | 100.0% | 75.0% | 80.0% | 79.2% |

Cumulative priced usage (including prior study and every new attempt): CNY 14.3077. Cumulative verified-rate ceiling: CNY 14.3077; authorization: CNY 20.
Observed account decrease at final close: CNY 14.30. Total API requests: 1766; HTTP errors: 0.

The cohort fixes M1/M3/M5, two learning questions per metric, one scored period per setting, and eleven independent changes on synthetic retail and TPC-H SF1. ACE/AWM are SQL adaptations of released components; G-Memory uses the unchanged official core. Post-task binary correctness, without gold answers/SQL, feeds published memory updates. Full MAVRA retains its native checked publication, maintenance, optimization and snapshot execution. All four planners receive the same bounded format of their own recent task results and binary correctness; no reference SQL/value or hidden change label is exposed.

## synthetic: every setting

Counts are correct/scored over complete matched repeats.

| Setting | ACE | AWM | G-Memory | MAVRA |
|---|---:|---:|---:|---:|
| holdout | 3/3 | 3/3 | 2/3 | 3/3 |
| append | 3/3 | 0/3 | 2/3 | 3/3 |
| backfill | 1/1 | 1/1 | 0/1 | 1/1 |
| correct | 3/3 | 3/3 | 2/3 | 3/3 |
| addcol | 1/1 | 1/1 | 0/1 | 1/1 |
| status | 1/1 | 1/1 | 0/1 | 1/1 |
| revision | 2/3 | 3/3 | 1/3 | 3/3 |
| dupload | 3/3 | 3/3 | 2/3 | 3/3 |
| dimhist | 1/1 | 1/1 | 1/1 | 1/1 |
| latekey | 0/3 | 0/3 | 0/3 | 0/3 |
| unit | 2/3 | 2/3 | 0/3 | 1/3 |
| mirror | 0/1 | 0/1 | 0/1 | 1/1 |

## tpch: every setting

Counts are correct/scored over complete matched repeats.

| Setting | ACE | AWM | G-Memory | MAVRA |
|---|---:|---:|---:|---:|
| holdout | 3/3 | 3/3 | 3/3 | 3/3 |
| append | 2/2 | 2/2 | 2/2 | 0/2 |
| backfill | 1/1 | 1/1 | 1/1 | 1/1 |
| correct | 2/2 | 2/2 | 2/2 | 2/2 |
| addcol | 1/1 | 1/1 | 1/1 | 1/1 |
| status | 0/1 | 1/1 | 1/1 | 1/1 |
| revision | 2/2 | 2/2 | 2/2 | 2/2 |
| dupload | 0/2 | 1/2 | 2/2 | 2/2 |
| dimhist | 1/1 | 1/1 | 1/1 | 1/1 |
| latekey | 0/2 | 0/2 | 0/2 | 0/2 |
| unit | 0/2 | 2/2 | 0/2 | 1/2 |
| mirror | 1/1 | 1/1 | 1/1 | 1/1 |
