# Shared memory study: audited results

Primary tasks provide identical business definitions; all attempts count. Costs per attempt exclude source learning. Errors are execution/service failures, separate from wrong answers. ≥ marks lower-bound usage after a failed execution.

| Policy | Correct | Errors | Turns | Input tokens | Schema calls | SQL probes | Seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| isolated | 47/54 | 7 | ≥4.76 | ≥13519.3 | 3.02 | 0.26 | 57.21 |
| frozen | 54/54 | 0 | 5.17 | 14977.1 | 3.17 | 0.31 | 58.34 |
| accumulating | 54/54 | 0 | 4.70 | 14133.9 | 2.57 | 0.30 | 51.11 |
| trajectory | 42/54 | 12 | ≥3.96 | ≥10990.3 | 2.44 | 0.41 | 53.41 |

Named secondary correctness: isolated 2/12, frozen 6/12, accumulating 11/12, trajectory 8/12.

Paired stream input-token changes relative to isolation:

| Stream | Frozen | Accumulating | Trajectory |
|---|---:|---:|---:|
| 1 | -9.4% | -1.9% | -8.7% |
| 2 | +8.3% | -4.4% | unavailable |
| 3 | unavailable | unavailable | unavailable |

Execution errors: 19 primary + 9 named, including 28 HTTP 402 credit failures. Full-matrix differences involving failed arms cannot establish method accuracy or cost benefits.

Post hoc recorded-execution sensitivity: 35 matched primary questions with no error in any arm. Selection ignores correctness and retains wrong answers or clarifications. Method order and service availability determine missingness; this does not replace the all-attempt analysis.

| Policy | Correct | Input tokens | Schema calls | SQL probes |
|---|---:|---:|---:|---:|
| isolated | 35/35 | 15691.5 | 3.49 | 0.29 |
| frozen | 35/35 | 13953.7 | 3.00 | 0.37 |
| accumulating | 35/35 | 13865.8 | 2.57 | 0.26 |
| trajectory | 35/35 | 13682.2 | 3.09 | 0.43 |

Source acquisition:

| Stream | Attempts | Published | Seconds | Agent tokens | Extraction tokens | Final valid entries |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 4 | 4 | 440.33 | 59339 | 21076 | 4 |
| 2 | 5 | 4 | 658.22 | 91836 | 32033 | 4 |
| 3 | 4 | 4 | 453.51 | 60846 | 23227 | 4 |

Three producer streams are descriptive replicates. Repeated probes are correlated. SQL probe counts are a trace proxy; error-token totals, if any, are lower bounds. Exact model guard applies to extraction, but its individual return labels are not separately recorded.

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
