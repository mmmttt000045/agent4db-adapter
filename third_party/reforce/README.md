# ReFoRCE (vendored, unmodified)

Six pipeline files of ReFoRCE (Deng et al., "ReFoRCE: A Text-to-SQL Agent with Self-Refinement, Consensus Enforcement,
and Column Exploration", arXiv:2502.00675), copied unchanged from `methods/ReFoRCE/` of
https://github.com/hao-ai-lab/ReFoRCE at commit `d2658991882f06fa0658bb7782ee9ea515fbb10b` (2025-08-01).
License: Apache-2.0 (`LICENSE`).

Not copied: the Spider 2.0 data, setup and evaluation scripts, schema linking (`schema_linking.py`, used only for
databases too large for the prompt) and `reconstruct_data.py` (its Spider 2.0 file layout is replaced by the prompt
builder in the adapter).

`tools/reforce/mavra_reforce.py` runs these files on one question over PostgreSQL. It adds, outside this directory:
a PostgreSQL backend for `SqlEnv` (read-only, statement timeout), PostgreSQL dialect hints for `Prompts`, an
OpenAI-compatible client for the configured model that counts tokens, and the fixed answer format `answer` (one row,
one column) given through ReFoRCE's own format-restriction input. The four steps of `scripts/run_main.sh` are run in
order for the one question: self-refinement with majority vote over 8 candidates; column exploration and rerun when the
vote has no winner; tie-break; final choice.
