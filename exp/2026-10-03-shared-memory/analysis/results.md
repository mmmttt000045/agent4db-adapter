# Shared memory study: audited results

Primary tasks provide identical business definitions; all attempts count. Costs per attempt exclude source learning. Errors are execution/service failures, separate from wrong answers. ≥ marks lower-bound usage after a failed execution.

| Policy | Correct | Errors | Turns | Input tokens | Schema calls | SQL probes | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| isolated | 54/54 | 0 | 5.46 | 15915.0 | 3.48 | 0.20 | 13.37 |
| frozen | 54/54 | 0 | 5.11 | 14835.1 | 3.13 | 0.19 | 13.46 |
| accumulating | 54/54 | 0 | 4.19 | 12033.7 | 2.52 | 0.06 | 9.45 |
| trajectory | 54/54 | 0 | 4.96 | 13956.5 | 3.31 | 0.17 | 11.63 |

Named secondary correctness: isolated 3/12, frozen 6/12, accumulating 12/12, trajectory 12/12.

Paired stream input-token changes relative to isolation:

| Stream | Frozen | Accumulating | Trajectory |
|---|---:|---:|---:|
| 1 | -8.8% | -28.5% | -9.1% |
| 2 | -6.4% | -24.4% | -12.7% |
| 3 | -5.2% | -20.3% | -15.1% |

Source acquisition:

| Stream | Attempts | Published | Seconds | Agent tokens | Extraction tokens | Final valid entries |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 4 | 92.93 | 59671 | 17782 | 4 |
| 2 | 4 | 4 | 130.49 | 66947 | 25154 | 4 |
| 3 | 4 | 4 | 120.13 | 87137 | 20527 | 4 |

Three producer streams are descriptive replicates. Repeated probes are correlated. SQL probe counts are a trace proxy; error-token totals, if any, are lower bounds. Exact model guard applies to extraction, but its individual return labels are not separately recorded.

Initial metered-route experiment is retained separately: 264 attempts; 19 primary and 9 named execution failures, including 28 documented HTTP 402 credit failures. The recovery repeats the full matrix with the same binary, workload, model guard and budget through an available subscription route; producer prefixes, costs and outcomes are never pooled. Of 197 returned initial primary answers, 197 were correct; apparent differences in all-attempt success must be separated from availability. Full original statistics and post hoc recorded-execution sensitivity are in `initial-service-censored/`; raw records remain in `raw/results/shared-memory-main/`.

Strategy test replay, summed across three timing captures of one workload:

| Repair setting | Adopted | Default ms | Selected ms | Reduction | Best fixed ms |
|---|---:|---:|---:|---:|---:|
| key-required | 0/3 | 3449.997 | 3449.997 | 0.0% | 3449.997 |
| repair-exhausted | 3/3 | 3449.997 | 1313.357 | 61.9% | 1313.357 |
| mixed | 3/3 | 3449.997 | 2142.052 | 37.9% | 2142.052 |

Full observation acquisition: 38.52 seconds of checks; 72.63 seconds including setup/collection. Verdict mismatches: 0. Acquisition is excluded from the counterfactual test costs; this is not a live agent speedup. The best fixed order is a retrospective test oracle.

Exploratory metadata diagnostic (not a preregistered main comparison):

- producer: explored; 2 probe queries; 4 column definitions; 100000 rows.
- new-consumer: reused; 0 probe queries; 4 column definitions; 100000 rows.
- after-notified-dml: explored; 2 probe queries; 4 column definitions; 100001 rows.
- after-comment-only: reused; 0 probe queries; 4 column definitions; 100001 rows.
- after-additive-ddl: explored; 2 probe queries; 4 column definitions; 100001 rows.
- after-explicit-restart: explored; 2 probe queries; 5 column definitions; 100001 rows.

Comment-only changes leave sourced comments stale; additive DDL leaves the profile's column definitions stale, although SELECT * sample columns already expose the new name. An explicit restart refreshes definitions and comments. This is a live-catalog-refresh limitation, not a complete absence of information about the new column.
