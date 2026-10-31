# Fig. 6: published-memory comparison

This is the newly budgeted single-period cohort. Only complete matched repeats enter accuracy; every paid attempt enters spending.

Complete matched repeats: 2. Observed ranges are not confidence intervals.

| Dataset | Method | Held out | Non-breaking | Covered breaks | All settings |
|---|---|---:|---:|---:|---:|
| synthetic | ACE | 100.0% | 100.0% | 66.7% | 75.0% |
| synthetic | AWM | 16.7% | 0.0% | 0.0% | 1.4% |
| synthetic | G-Memory | 66.7% | 33.3% | 40.0% | 34.7% |
| synthetic | MAVRA | 100.0% | 100.0% | 60.0% | 66.7% |
| tpch | ACE | 100.0% | 100.0% | 60.0% | 77.1% |
| tpch | AWM | 100.0% | 93.8% | 60.0% | 72.9% |
| tpch | G-Memory | 100.0% | 100.0% | 65.0% | 77.1% |
| tpch | MAVRA | 100.0% | 100.0% | 75.0% | 81.2% |

Priced usage (including every attempt): CNY 8.6970. Conservative peak-price ceiling: CNY 17.3940; authorization: CNY 20.
Observed account decrease at final close: CNY 8.65. Total API requests: 3378; HTTP errors: 0.

The cohort fixes M1/M3/M5, two learning questions per metric, one scored period per setting, and eleven independent changes on synthetic retail and TPC-H SF1. ACE/AWM are SQL adaptations of released components; G-Memory uses the unchanged official core. Post-task binary correctness, without gold answers/SQL, feeds published memory updates. Full MAVRA retains its native checked publication, maintenance, optimization and snapshot execution.

## synthetic: every setting

Counts are correct/scored over complete matched repeats.

| Setting | ACE | AWM | G-Memory | MAVRA |
|---|---:|---:|---:|---:|
| holdout | 6/6 | 1/6 | 4/6 | 6/6 |
| append | 6/6 | 0/6 | 4/6 | 6/6 |
| backfill | 2/2 | 0/2 | 0/2 | 2/2 |
| correct | 6/6 | 0/6 | 4/6 | 6/6 |
| addcol | 2/2 | 0/2 | 0/2 | 2/2 |
| status | 2/2 | 0/2 | 0/2 | 2/2 |
| revision | 5/6 | 0/6 | 4/6 | 6/6 |
| dupload | 3/6 | 0/6 | 2/6 | 0/6 |
| dimhist | 2/2 | 0/2 | 2/2 | 2/2 |
| latekey | 0/6 | 0/6 | 0/6 | 0/6 |
| unit | 1/6 | 0/6 | 1/6 | 0/6 |
| mirror | 1/2 | 0/2 | 0/2 | 0/2 |

## tpch: every setting

Counts are correct/scored over complete matched repeats.

| Setting | ACE | AWM | G-Memory | MAVRA |
|---|---:|---:|---:|---:|
| holdout | 6/6 | 6/6 | 6/6 | 6/6 |
| append | 4/4 | 4/4 | 4/4 | 4/4 |
| backfill | 2/2 | 2/2 | 2/2 | 2/2 |
| correct | 4/4 | 3/4 | 4/4 | 4/4 |
| addcol | 2/2 | 2/2 | 2/2 | 2/2 |
| status | 2/2 | 2/2 | 2/2 | 2/2 |
| revision | 4/4 | 3/4 | 4/4 | 4/4 |
| dupload | 0/4 | 1/4 | 1/4 | 3/4 |
| dimhist | 2/2 | 2/2 | 2/2 | 2/2 |
| latekey | 0/4 | 0/4 | 0/4 | 0/4 |
| unit | 1/4 | 0/4 | 0/4 | 0/4 |
| mirror | 2/2 | 2/2 | 2/2 | 2/2 |
