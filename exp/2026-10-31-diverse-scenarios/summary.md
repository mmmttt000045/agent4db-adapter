# Fig.6: checked execution and cross-form transfer

All six unchanged baseline controls are retained from the valid corrected cohort; the changed native method is rerun. Additional M3 forms: 3/schema, chosen by spending only.

## Both schemas: descriptive summary

Both schemas and all settings are retained with equal weights. This summary was added after execution; it does not change the frozen protocol or claim statistical significance.

| Method | Equal-schema accuracy | Correct / answers | Micro accuracy |
|---|---:|---:|---:|
| ACE | 73.1% | 38/52 | 73.1% |
| AWM | 81.4% | 41/52 | 78.8% |
| G-Memory | 61.5% | 32/52 | 61.5% |
| MAVRA | 84.6% | 43/52 | 82.7% |

| Schema | Method | Non-breaking | Covered breaks | New forms | All settings |
|---|---|---:|---:|---:|---:|
| synthetic | ACE | 100.0% | 73.3% | 66.7% | 76.9% |
| synthetic | AWM | 75.0% | 80.0% | 100.0% | 74.4% |
| synthetic | G-Memory | 33.3% | 40.0% | 100.0% | 38.5% |
| synthetic | MAVRA | 100.0% | 80.0% | 100.0% | 92.3% |
| tpch | ACE | 100.0% | 40.0% | 100.0% | 69.2% |
| tpch | AWM | 100.0% | 70.0% | 100.0% | 88.5% |
| tpch | G-Memory | 100.0% | 80.0% | 100.0% | 84.6% |
| tpch | MAVRA | 75.0% | 80.0% | 100.0% | 76.9% |

## synthetic: all settings

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
| unit | 2/3 | 2/3 | 0/3 | 3/3 |
| mirror | 0/1 | 0/1 | 0/1 | 1/1 |
| holdout-extra | 2/3 | 3/3 | 3/3 | 3/3 |

## tpch: all settings

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
| unit | 0/2 | 2/2 | 0/2 | 0/2 |
| mirror | 1/1 | 1/1 | 1/1 | 1/1 |
| holdout-extra | 3/3 | 3/3 | 3/3 | 3/3 |

## Fresh transfer-query cost

| Schema | Method | Correct | Calls | Tokens/question | CNY/question |
|---|---|---:|---:|---:|---:|
| synthetic | ACE | 2/3 | 18 | 24,093 | 0.031334 |
| synthetic | AWM | 3/3 | 18 | 27,713 | 0.018216 |
| synthetic | G-Memory | 3/3 | 27 | 22,510 | 0.016023 |
| synthetic | MAVRA | 3/3 | 10 | 14,098 | 0.006251 |
| tpch | ACE | 3/3 | 14 | 17,100 | 0.029867 |
| tpch | AWM | 3/3 | 12 | 10,616 | 0.007813 |
| tpch | G-Memory | 3/3 | 21 | 16,477 | 0.012459 |
| tpch | MAVRA | 3/3 | 9 | 11,450 | 0.005640 |

208 scored answers, 48 learning tasks and 12 distinct scored questions. Cached source warmup is excluded from these totals.
Cumulative account debit CNY19.72; conservative ceiling CNY19.745186; all 7090 old/new official API requests included.
One run per method, with unchanged condition-matched frozen controls. No confidence intervals or statistical-significance claim. Every original failure is retained; the entire failed diverse-trajectory cohort is development-only and its costs remain charged.
