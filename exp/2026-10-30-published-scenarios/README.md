# Published-memory comparison for Fig. 6

This study is authorized by the user's CNY 20 ceiling. `protocol.json` specifies the new cohort before any paid calls. It compares ACE, AWM, G-Memory, and full MAVRA on three fixed metrics, single-period queries, two schemas, and all eleven archived data-change generators. The question scope is smaller than the historical multi-form study; method mechanisms are retained.

The existing Rust `mem-*` implementations are excluded because they are simplified paper-inspired baselines. The new bridge uses the released ACE utilities/prompts, the existing faithful online AWM adapter, and the official G-Memory core. All paid calls, including retries, memory and MAVRA extraction/optimization, must pass the shared loopback budget relay. Its conservative peak-price ceiling and account-decrease guard both enforce the total CNY 20 authorization.

Execution ran on 2026-10-30 from 14:43 UTC to 18:23:43 UTC, after the offline relay checks and a fake-model memory/checkpoint smoke passed. The protocol and executable source hashes were frozen before the first paid request. Both matched repeats completed: **464 formal tasks, comprising 96 learning and 368 scored answers**, in 16 complete method/dataset cells. Two earlier failed G-Memory learning attempts are retained separately. All 3,378 API requests, including those attempts and every memory/extraction/optimization call, enter the cost ledger; there were no HTTP errors. The relay is closed to further model calls, and the study's temporary databases have been removed.

Final account decrease was **CNY 8.65**. The per-request token estimate is CNY 8.69698742 at the official off-peak rates; the conservative peak-price charge is CNY 17.39397484. Each is below the authorized CNY 20. These are distinct accounting measures; the token estimate is not presented as the actual debit. The final balance check exposes only the decrease, not either private account balance. See `financial-close.json` and `database-cleanup-check.json`.

Post-hoc case analysis on 2026-10-31 found unequal test-time feedback/update opportunities and a shared SQL-admission error that rejects correctly filtered/aggregated joins, alongside MAVRA's semantic-retention and unit/repair limits. The archived accuracies remain the observed outcomes; they do not isolate the effect of the maintenance method. See [failure-analysis.md](failure-analysis.md) for concrete cases, source locations and correction priorities. This analysis used no further model calls.

`memory-service.py` supplies only each question, the agent's own transcript and post-task binary correctness to the published memory components. It never passes gold SQL or gold values. `patch-runtime.py` makes this bridge in the isolated runtime; the main checkout's Rust sources are unchanged. The historical generic `report.json` judge description predates this bridge; this protocol governs the new cohort's feedback boundary.

The ACE Reflector/Curator and playbook utilities and AWM prompt files were checked against their pinned upstream sources. G-Memory's 139 Python files match the archived upstream tree; its memory core, prompts, LLM client and configuration also match the pinned upstream URLs directly. Verification hashes accompany the study. SQL adaptations are identified explicitly; the browser and ALFWorld environments are not part of the workload.

The fixed metric selection is:

| Metric | Synthetic retail | TPC-H SF1 |
|---|---|---|
| M1 | Store-sales net revenue | Shipped net revenue |
| M3 | Store-return amount divided by store sales | Promotional-product revenue |
| M5 | Electronics-category store-sales revenue | Order count |

Each dataset has six source-learning questions, three held-out period questions, and the questions whose tables are affected by each of the eleven changes. A complete method/dataset cell contains 32 tasks on synthetic retail (26 scored) or 26 on TPC-H (20 scored). Thus each complete matched repeat contains **232 tasks: 48 learning and 184 scored**. The same agent A learns and returns, so private published memories retain usable experience. Every task starts a fresh conversation. These results concern single-period questions on the three selected metrics; they do not measure the historical five-form workload or cross-agent transfer.

The API must report `deepseek-flash` on each accepted response. `documented_version` in the protocol is the official documentation's mapping, not an explicit checkpoint identifier returned by the API. The planner/extractor use low-effort thinking, 20 turns and a 120-second SQL limit. AWM induction and G-Memory memory calls retain their 2,048/512-token non-thinking settings. The study keeps at most two paired repeats; the predeclared second-repeat decision uses spending and elapsed time only.

On the first G-Memory attempt, the older server adapter inferred the provider from the URL and failed to recognize the loopback accounting relay. Its intended non-thinking override was omitted; both cells stopped on their first memory update after 512 reasoning tokens produced no content. These two incomplete attempts remain in the execution record and total spending. The repair sets the known DeepSeek profile in `memory-service.py`; a fake-API SDK check verifies `thinking=disabled`, `max_tokens=512`, and a successful memory write. `resume-study.py` reuses completed ACE/AWM cells, starts G-Memory in fresh `-a2` stores, then continues the fixed schedule with the same durable budget state. No protocol, native Rust binary, upstream core or data was changed. The recovery manifest confirms that `memory-service.py` is the only changed existing source. The original source archive and the recovery delta are both retained.

An integrity check of AWM's low synthetic score in repeat 1 found five correct source-learning answers, nonempty induced workflows, and no adapter exceptions. The induced workflows generalized the metric measure to a placeholder; subsequent named-metric SQL used gross sales instead of the learned net-paid measure, and the return-rate query used return time instead of sales time. These are scored semantic errors. This complete run is retained. Neither low baseline scores nor MAVRA's relative ranking changes the workload, method settings, or repeat gate.

The final figure uses both complete repeats, equal weights per setting and then per repeat; error bars show the two observed values, not confidence intervals. MAVRA answers every held-out/non-breaking question correctly in both schemas. On covered changes it reaches 60.0% on synthetic retail versus ACE's 66.7%, and 75.0% on TPC-H versus the best baseline G-Memory's 65.0%. Overall setting-weighted accuracy is 66.7%/81.2% for MAVRA and 75.0%/77.1% for ACE. The paper reports these limits without selecting a favorable repeat. Full group averages and all twelve setting counts are in [summary.md](summary.md); machine-readable phases, outcomes and run ranges are in `study-stats.json`.

The final raw evidence is archived locally as `raw-results.tgz` (31,403,839 bytes; SHA-256 `60038c0c10ffb82d57fe9ec194ea2b225d636749b0b2eae5ad14e7f0b5f54006`). Its 893 files include complete reports, failed attempts, API usage/transcripts, source/recovery manifests, checkpoints and the financial close. Every member was verified against `archive-manifest.json` after download and extraction into `results/published-scenarios-20261030/`. Only the two private balance fields are redacted; request usage and spending remain intact. The original balance-bearing record remains on the experiment server. Original executable sources are in `runtime-source.tgz`; the provider-profile recovery delta is in `runtime-source-recovery.tgz`. Database templates and external dependencies are not bundled; the archive alone is not a standalone database reproduction package.

To reproduce the aggregation without additional API calls, run from the repository root:

```sh
python exp/2026-10-30-published-scenarios/analyse.py --results results/published-scenarios-20261030
```

Copy `overleaf-numbers.tex` to `overleaf/gen/published-scenarios.tex`, then run `python tools/figures/two_schemas.py`. This creates the English/Chinese vector figures from `study-stats.json` and checks every plotted mean against the manuscript macros. Figure 6 remains a single-column 84.6 × 55 mm chart with 32 bars. The final English manuscript has 12 body pages, 15 including the AI acknowledgment and references; the bilingual reading copy has 23 pages. The current source package is `overleaf/build/mavra-icde-bilingual.zip`.
