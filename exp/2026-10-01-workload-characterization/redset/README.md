# Redset application-workload baseline

Statistics computed from the public Amazon Redset dataset (van Renen et al.,
"Why TPC Is Not Enough: An Analysis of the Amazon Redshift Fleet", VLDB 2024;
<https://github.com/amazon-science/redset>, CC BY-NC 4.0) as a traditional
application/BI workload baseline for the MAVRA paper. Everything here is
computed from the data; see `redset_stats.json` (machine-readable, with the
definition, numerator and denominator of every number) and `redset_stats.txt`
(same numbers, one line per statistic).

## Data used

| file | what it is (verified, see `samples_check.json`) |
|---|---|
| `provisioned/parts/N.parquet` (200 files, 17.66 GB) | one file per cluster; file N holds exactly the rows of `instance_id = N` |
| `serverless/full.parquet` (0.32 GB) | all 200 serverless clusters in one file (the `serverless/parts/` split is the same per-cluster layout; spot-checked) |
| `*/sample_0.01.parquet`, `*/sample_0.001.parquet` | query-level uniform random samples (≈1 % / 0.1 % of rows, every cluster sampled at ≈ the same rate, all rows present in the full data). **Not used for any statistic** — they break per-cluster streams. |

All statistics use **complete per-cluster streams of all 200 provisioned and
all 200 serverless clusters** (no cluster subsampling, no seed needed).
Time span: 2024-03-01 to 2024-05-31 (three months). Provisioned and serverless
are reported separately.

Redset itself is a *biased* sample of clusters (selected to cover different
"busyness" levels); the README says aggregating over it "will not yield a
representative view of the overall Amazon Redshift fleet". Numbers are a
baseline for "real production application/BI/ETL workloads", not fleet
averages.

## Column semantics relied on (verbatim from the Redset README)

- `instance_id`: "Uniquely identifies a redshift cluster"
- `user_id`: "Identifies the user that issued the query"
- `query_id`: "Unique per instance"
- `arrival_timestamp`: "Timestamp when the query arrived on the system"
- `feature_fingerprint`: "Hash value of the query fingerprint. A proxy for query-likeness, though not based on text. Will overestimate repetition."
- `was_aborted`: "Whether the query was aborted during its lifetime"
- `was_cached`: "Whether the query was answered from result cache"
- `cache_source_query_id`: "If query was answered from result cache, this is the query id for the query which populated the cache"
- `query_type`: "Type of query, e.g.., `select`, `copy`, ..."
- `num_permanent_tables_accessed`: "Number of permanent table accesses by the query (regular database table)"
- `num_external_tables_accessed`: "Number of external tables accessed by the query"
- `num_system_tables_accessed`: "Number of system tables accessed by the query"

Paper (Sec. 6): Redset "contains metadata for user queries from 200 serverless
and provisioned clusters (each) over a three-month period in 2024. We sampled
clusters from our fleet such that the published dataset contains
representatives for the various levels of observed busyness."

## Observed encoding facts (from the data, `explore*.txt`)

- **Result-cache hits are not labelled `select`.** Every `was_cached = 1` row
  has `query_type = 'other'`, NULL `feature_fingerprint` and NULL table
  counts; `cache_source_query_id` resolves to a row of the same cluster for
  96.3 % (provisioned) / 99.8 % (serverless) of cached rows (the rest point to
  queries outside the log window); resolved sources always arrived earlier,
  are `select` in 99.96 % (prov.) / 100 % (serverless), and have the same
  `user_id` in 99.7 % (prov.) / 99.97 % (serverless)
  (`cache_source_check_provisioned.txt`, `explore2_serverless.txt`).
- `feature_fingerprint` is a 64-hex hash, cluster-specific (virtually never
  shared across clusters), and practically pure w.r.t. `query_type` and to
  system-table access.
- `query_id` is not monotone in arrival time; stream order is
  `(arrival_timestamp, query_id)` (timestamp ties are rare).
- `was_aborted` rows exist for every query type; there is no error code or
  message column.

## Definitions

- **Classes.** `all` = every row; `read` = `query_type = 'select' OR
  was_cached = 1` (primary "read query" definition); `select` =
  `query_type = 'select'` (executed selects only; sensitivity check). Each
  statistic of a class is computed on that class's own per-cluster stream.
- **Effective fingerprint / table counts.** For cached rows we use the
  fingerprint and table counts of the `cache_source_query_id` row.
- **Pooled** = Σ numerator / Σ denominator over all clusters of the variant.
  **Cross-cluster** = per-cluster ratio, then median [p25, p75] over clusters
  whose denominator is ≥ 1000 (k = number of such clusters). Cross-user
  statistics are also given over eligible clusters with ≥ 2 users.
- Full definitions of each statistic are in `redset_stats.json`
  (`definition`, `numerator`, `denominator` fields).

## Context

| | provisioned | serverless |
|---|---|---|
| clusters | 200 (143 with ≥1000 queries; 111 with ≥1000 read queries) | 200 (39 with ≥1000 queries; 29 with ≥1000 read queries) |
| queries (all / read / select) | 433,107,811 / 133,764,075 / 87,708,340 | 8,244,382 / 2,549,708 / 2,171,354 |
| read share of all queries | 30.9 % | 30.9 % |
| result-cache hits (`was_cached`) | 46,055,735 (1,718,428 with source outside log) | 378,354 (871) |
| principals = (cluster, user_id) | 190,196 (187,003 of them in 3 clusters: 13, 52, 97) | 2,412 |
| median queries / users per cluster | 31,045 / 2 | 33 / 1 |
| time span | 2024-02-29 23:59:55 .. 2024-05-31 00:00:04 | 2024-02-29 23:59:58 .. 2024-05-30 23:59:30 |

## Results

Cell format: `pooled; cross-cluster median [p25, p75] k=#eligible clusters`.
Denominators (from `redset_stats.json`): repetition/concurrency statistics
use queries of the class with a non-NULL effective fingerprint (provisioned
read 131,219,451; all 424,764,067; serverless read 2,543,697; all 8,212,838);
cached/aborted/system-table fractions use all queries of the class
(provisioned read 133,764,075; all 433,107,811; serverless read 2,549,708;
all 8,244,382).

| statistic | provisioned read | provisioned all | serverless read | serverless all |
|---|---|---|---|---|
| fp_repeat_frac | 93.45%; 91.72% [82.66%, 96.58%] k=111 | 90.16%; 84.68% [74.40%, 94.15%] k=143 | 93.11%; 91.16% [73.55%, 95.32%] k=29 | 87.52%; 91.20% [78.86%, 97.11%] k=39 |
| fp_repeat_frac_from_apr1 | 93.88%; 91.19% [82.74%, 96.64%] k=108 | 91.06%; 84.92% [76.15%, 95.04%] k=127 | 91.22%; 92.24% [72.64%, 95.70%] k=24 | 87.36%; 91.60% [77.38%, 98.60%] k=35 |
| distinct_fp_per_100 | 6.6; 8.3 [3.4, 17.3] k=111 | 9.8; 15.3 [5.8, 25.6] k=143 | 6.9; 8.8 [4.7, 26.5] k=29 | 12.5; 8.8 [2.9, 21.1] k=39 |
| distinct_fp_per_100q_block | 37.2; 32.3 [19.1, 51.0] k=111 | 40.9; 43.5 [27.9, 56.3] k=143 | 29.1; 21.6 [9.4, 49.9] k=29 | 35.5; 33.4 [14.1, 45.0] k=39 |
| top10_fp_share | 32.41%; 33.46% [12.94%, 60.77%] k=111 | 33.72%; 37.38% [24.60%, 59.17%] k=143 | 51.27%; 35.63% [20.48%, 86.31%] k=29 | 53.41%; 45.53% [32.02%, 77.50%] k=39 |
| cached_frac | 34.43%; 13.30% [1.72%, 36.40%] k=111 | 10.63%; 1.14% [0.07%, 9.80%] k=143 | 14.84%; 8.72% [1.35%, 20.91%] k=29 | 4.59%; 1.20% [0.00%, 6.38%] k=39 |
| aborted_frac | 0.35%; 0.07% [0.00%, 0.49%] k=111 | 0.51%; 0.02% [0.00%, 0.22%] k=143 | 0.28%; 0.17% [0.00%, 1.06%] k=29 | 0.91%; 0.14% [0.00%, 0.50%] k=39 |
| sys_table_frac | 7.63%; 2.20% [0.07%, 22.75%] k=111 | 2.39%; 0.25% [0.00%, 2.79%] k=143 | 40.12%; 0.26% [0.03%, 2.50%] k=29 | 12.42%; 0.04% [0.00%, 0.97%] k=39 |
| sys_only_frac | 7.59%; 2.16% [0.06%, 22.75%] k=111 | 2.35%; 0.19% [0.00%, 2.57%] k=143 | 40.12%; 0.26% [0.03%, 2.50%] k=29 | 12.42%; 0.04% [0.00%, 0.97%] k=39 |
| xuser_same_fp_60s | 0.61%; 0.01% [0.00%, 0.23%] k=111 | 4.61%; 0.01% [0.00%, 1.80%] k=143 | 0.08%; 0.00% [0.00%, 0.01%] k=29 | 0.52%; 0.00% [0.00%, 0.01%] k=39 |
| xuser_same_fp_10s | 0.20%; 0.00% [0.00%, 0.05%] k=111 | 2.62%; 0.00% [0.00%, 0.46%] k=143 | 0.05%; 0.00% [0.00%, 0.00%] k=29 | 0.26%; 0.00% [0.00%, 0.00%] k=39 |
| suser_same_fp_60s | 72.39%; 63.81% [34.52%, 80.51%] k=111 | 69.68%; 64.58% [48.09%, 80.77%] k=143 | 67.15%; 62.97% [43.54%, 81.23%] k=29 | 66.49%; 64.85% [47.74%, 87.39%] k=39 |
| suser_same_fp_10s | 62.55%; 43.33% [21.81%, 65.53%] k=111 | 63.49%; 52.77% [37.84%, 70.41%] k=143 | 42.33%; 36.14% [18.18%, 58.64%] k=29 | 53.02%; 51.76% [37.69%, 80.05%] k=39 |
| fp_first_seen_other_user_frac | 3.67%; 0.24% [0.00%, 2.64%] k=111 | 6.91%; 0.27% [0.00%, 5.34%] k=143 | 0.32%; 0.21% [0.00%, 1.82%] k=29 | 2.98%; 0.03% [0.00%, 5.59%] k=39 |
| fp_first_seen_other_user_frac_of_repeats | 3.93%; 0.35% [0.00%, 3.14%] k=108 | 7.67%; 0.64% [0.00%, 7.75%] k=131 | 0.34%; 0.24% [0.00%, 2.78%] k=27 | 3.40%; 0.04% [0.00%, 7.10%] k=38 |
| fp_null_frac | 1.90%; 0.10% [0.01%, 0.65%] k=111 | 1.93%; 0.02% [0.00%, 0.47%] k=143 | 0.24%; 0.01% [0.00%, 0.11%] k=29 | 0.38%; 0.01% [0.00%, 0.08%] k=39 |

| principal / session statistic | provisioned read | provisioned all | serverless read | serverless all |
|---|---|---|---|---|
| principals (cluster,user_id) | 188975 | 190196 | 2328 | 2412 |
| share of queries by principals active >=7 days: pooled; x-cluster | 97.79%; 99.99% [99.84%, 100.00%] k=111 | 98.33%; 99.99% [17.34%, 100.00%] k=143 | 99.63%; 99.98% [99.12%, 100.00%] k=29 | 97.80%; 99.99% [99.79%, 100.00%] k=39 |
| x-cluster: per-cluster median principal active days | 43.0 [10.8, 83.2] k=111 | 31.0 [3.0, 84.0] k=143 | 10.0 [4.0, 45.5] k=29 | 19.5 [5.5, 49.0] k=39 |
| x-cluster: per-cluster median principal span (days) | 79.9 [50.0, 89.0] k=111 | 73.5 [3.4, 88.9] k=143 | 44.5 [30.7, 79.6] k=29 | 60.7 [29.9, 81.5] k=39 |
| x-cluster: per-cluster frac principals active >=7 days | 0.78 [0.53, 1.00] k=111 | 0.73 [0.06, 1.00] k=143 | 0.60 [0.33, 1.00] k=29 | 0.60 [0.36, 1.00] k=39 |
| pooled over principals: active days | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| pooled over principals (excl. 3 ephemeral-id clusters): active days | 14.0 [3.0, 58.0] | 12.0 [2.0, 49.0] | 1.0 [1.0, 1.0] | 1.0 [1.0, 1.0] |
| pooled frac principals >=7 days (all; excl. eph.) | 0.006; 0.617 | 0.010; 0.602 | 0.034; 0.034 | 0.042; 0.042 |
| sessions (30-min gap) | 458500 | 543278 | 12199 | 21375 |
| pooled over sessions: queries/session | 7.0 [3.0, 15.0] | 13.0 [4.0, 38.0] | 2.0 [1.0, 12.0] | 7.0 [2.0, 45.0] |
| pooled over sessions: duration (s) | 123.8 [13.5, 753.8] | 173.2 [22.4, 944.3] | 27.9 [0.0, 1081.7] | 90.2 [4.8, 1576.2] |
| x-cluster: per-cluster median queries/session | 6.0 [4.0, 24.0] k=111 | 31.0 [8.5, 1062.0] k=143 | 7.0 [3.0, 14.5] k=29 | 13.0 [6.5, 53.5] k=39 |
| x-cluster: per-cluster median session duration (s) | 283.2 [96.2, 665.0] k=111 | 384.6 [175.6, 1480.1] k=143 | 543.0 [131.0, 1018.4] k=29 | 553.5 [132.1, 1355.3] k=39 |
| query-weighted median session size (queries) | 855129 | 1309966 | 12764 | 370044 |

Statistic definitions (short; exact wording in the JSON):

- `fp_repeat_frac`: query's effective fingerprint already occurred earlier in the same cluster's class stream (first occurrence = new). `_from_apr1`: same, counting only queries on/after 2024-04-01 (March = look-back history).
- `distinct_fp_per_100` = 100 × distinct fingerprints / fingerprinted queries (identically 100 × (1 − `fp_repeat_frac`)); `distinct_fp_per_100q_block` = mean distinct fingerprints within consecutive non-overlapping blocks of 100 fingerprinted queries of the cluster stream (length-normalised local diversity).
- `top10_fp_share`: share of the class's fingerprinted queries whose fingerprint is among the cluster's 10 most frequent.
- `cached_frac` = `was_cached = 1`; `aborted_frac` = `was_aborted = 1`.
- `sys_table_frac`: effective `num_system_tables_accessed > 0`; `sys_only_frac`: additionally 0 permanent and 0 external tables.
- `xuser_same_fp_60s/10s`: another query of the class, same cluster and fingerprint, **different** `user_id`, arrival within ±60 s / ±10 s. `suser_*`: same, **same** `user_id` (excluding the query itself). Multi-user x-cluster medians are in the JSON (`xcluster_multiuser`).
- `fp_first_seen_other_user_frac`: fingerprint's first occurrence in the cluster's class stream was issued by a different `user_id` (denominator all fingerprinted queries; `_of_repeats`: denominator repeated queries only).
- Principals: (cluster, user_id); active days = distinct `arrival_timestamp::DATE`; span = last − first arrival. Sessions: per principal, a gap > 30 min starts a new session; duration = last − first arrival in the session.
- `ephemeral-id clusters`: provisioned clusters 13, 52, 97 have 81,462 / 51,308 / 54,233 distinct user_ids whose median lifetime is 93-166 s (median 22-25 queries each); they are included everywhere and excluded only in the `*_excl_ephemeral_id_clusters` sensitivity fields.

## Caveats

1. **Fingerprint ≠ exact template.** Per the docs the fingerprint is "not based on text" and "will overestimate repetition": structurally different SQL can share a fingerprint. Fingerprint repetition is an *upper bound* on template repetition and says nothing about literal-level (exact-query) repetition. The VLDB paper's own text-hash result ("in 50 % of clusters 80 % of queries are 1-to-1 repetitions", Sec. 4.4) is computed on internal fleet data, not on Redset, and is not reproducible from Redset. Fingerprints are cluster-scoped, so no cross-cluster template sharing can be measured.
2. **Left censoring.** Only 3 months are logged; a query "new" in the window may have run before March. The April-onward variant changes pooled repeat fractions by at most 2.7 pp and not systematically upward (e.g. provisioned read 93.45 % → 93.88 %, serverless read 93.11 % → 91.22 %), so censoring is not the main driver.
3. **Result-cache hits** are logged as `query_type = 'other'` with NULL fingerprint/table counts; we resolve them through `cache_source_query_id`. 3.7 % of provisioned cached rows (1.72 M) point to a source outside the log and stay NULL (this is most of `fp_null_frac` for provisioned reads). `cached_frac` is an exact-result-reuse *lower bound* for exact repetition (the cache is invalidated by writes, skips system tables, non-deterministic functions, etc.; see paper Sec. 4.6).
4. **`was_aborted` ≠ SQL error rate.** The docs only say "aborted during its lifetime"; Redset has no error code or message, and neither the README nor the paper states whether statements rejected at parse/bind time (syntax errors, unknown relations, permission errors) are logged. Aborted rows mix instant aborts (median execution 2 ms for aborted `update`, 102 ms for `copy`) and long cancels/timeouts (aborted provisioned `select`: median execution 8.5 s; 48 % have a NULL fingerprint) — see `aborted_breakdown_provisioned.txt`. It should not be compared one-to-one with an agent's failed-SQL rate.
5. **`user_id` is a database user, not a person.** BI tools and applications commonly share one service account among many humans, so cross-user statistics (5) are lower bounds on cross-human sharing. Conversely, three provisioned clusters mint tens of thousands of short-lived user_ids, and small serverless clusters have many one-day principals; hence pooled principal-level medians (1 active day) are dominated by these and the per-cluster medians are the meaningful lifetime statistics. The query-weighted view is robust to this: the share of queries issued by principals active on ≥7 days is ≥96.9 % pooled and ≥99.98 % as cross-cluster median in every variant/class.
6. **Skewed clusters.** Pooled values can be driven by a few very large clusters (e.g. serverless read `sys_table_frac` pooled 40 % vs cross-cluster median 0.26 %; provisioned all `xuser_same_fp_60s` pooled 4.6 % vs median 0.01 %). Report both. Serverless is dominated by tiny clusters (median 33 queries over 3 months), so only 29-39 serverless clusters meet the ≥1000-query eligibility threshold.
7. **System tables ≠ exploration.** `num_system_tables_accessed` counts catalog/monitoring tables (drivers' metadata calls, BI schema introspection, monitoring dashboards); it is only a proxy for metadata access. Queries that read system tables almost never also read user tables (system-only share of system-table queries: provisioned all 98.7 % / read 99.6 %; serverless all 99.999 % / read 100 %).
8. **Not fleet-representative.** Redset clusters were chosen to span "busyness" levels; clusters ≠ customers (README FAQ). Reads are only ~31 % of queries; the rest is ETL (insert/delete/copy/analyze/...).
9. `arrival_timestamp` time zone is undocumented; day boundaries use the raw timestamp. `query_id` is not arrival-ordered; ties in arrival time (rare) are broken by `query_id`.

## Files

- `download.py` — parallel range downloader for the S3 bucket (`docs/listing.xml` = bucket listing).
- `explore.py`, `explore2.py` (+ `explore_serverless.txt`, `explore2_serverless.txt`, `explore2_provisioned_sample.txt`), `aborted_breakdown_provisioned.txt`, `cache_source_check_provisioned.txt` — semantic checks.
- `make_table.py` — renders the Results table above from `redset_stats.json`.
- `analyze.py` — per-cluster statistics into `redset.duckdb`; `test_analyze.py` — synthetic test with hand-computed answers.
- `run_provisioned.sh` — driver (serverless full file, then provisioned parts).
- `aggregate.py` — `redset.duckdb` → `redset_stats.json`, `redset_stats.txt`.
- `verify_samples.py` → `samples_check.json` (what parts/samples are).
- `docs/` — Redset README, bucket listing, paper PDF/text.
- `data/` — downloaded parquet files (not needed after `redset.duckdb` exists).
