# Baseline reproduction notes (RelBench study)

For each baseline: where the code and prompts come from, what is used verbatim, and every change with its reason.
Settings shared by all methods (agent model, tools, stopping rule, learner, success signal) are in README §1.2;
none of them is changed per method except where the method's paper prescribes otherwise. This file is the source for
the paper's reproduction appendix.

## ACE (Zhang et al., ICLR 2026)

- **Code:** `third_party/ace/` (Apache-2.0): `reflector_prompts.py`, `curator_prompts.py`, `playbook_utils.py` from
  ace-agent/ace @ 82709de, unchanged; `utils.py` holds only `get_section_slug`; `appworld_playbook_block.txt` from
  ace-agent/ace-appworld @ 928e868. Harness: `Run.ace_update` in `tools/relbench/harness.py`.
- **Verbatim:** `REFLECTOR_PROMPT_NO_GT` and `CURATOR_PROMPT_NO_GT` (ACE without ground-truth labels); the empty
  playbook of `ACE._initialize_empty_playbook`; bullet format with ids and helpful/harmful counters; counter update
  (`update_bullet_counts`); ADD operations only (`apply_curator_operations`, as the released code); token budget
  80,000; one Reflector and one Curator call per session; same model for Generator, Reflector and Curator; temperature
  0 for Reflector and Curator; the whole playbook in the agent's prompt with the AppWorld instruction "Read the
  Playbook first ...".
- **Scope:** one playbook per agent, updated online after each of its sessions (one pass over the cutoffs in time
  order), as ACE adapts one agent's context.
- **Changes and why:**
  1. The Generator is our tool-using agent instead of a single JSON answer; `validate_features` and `submit` take an
     optional `bullet_ids`, and the last list reported goes to the Reflector, so that it can tag the bullets used
     (ACE's Generator reports bullet ids with every answer; our sessions often end by the stopping rule without a
     submission, so in the first P3 check with `submit` only, no bullet was ever tagged).
  2. Reflector inputs: question = task description and cutoff; reasoning trace = the session transcript (tool outputs
     cut at 20,000 characters, as the released code cuts outputs); predicted answer = the submitted feature SQL;
     environment feedback = the validation scores (or errors) of the session and its stop reason. RelBench has no
     single correct answer, so the no-label variant is the one that applies; validation scores are execution
     feedback (ACE §4.3).
  3. No multi-epoch offline adaptation: revisiting earlier cutoffs would expose later labels.
  4. The playbook shown to the agent keeps the counters (as in the finance code); the AppWorld code strips them.

## G-Memory (Zhang et al., NeurIPS 2025)

- **Code:** the official repository bingreeky/GMemory @ 7b581c5, used unchanged from a local copy (not committed here;
  the repository ships no license file). It runs in its own Python 3.12 environment (`results/ext/venv-gmem`, the versions pinned in its
  `requirements.txt`, CPU torch), because its code needs Python ≥ 3.12. Adapter: `tools/relbench/gmemory_service.py`
  (JSON lines), harness class `GMemoryService`.
- **Verbatim:** the GMemory class (insight, query and interaction layers, retrieval with LLM relevance scoring, key-step
  extraction, insight induction and merging schedules, insight scores); the settings of the released runs:
  successful_topk 1, failed_topk 0, insights_topk 5, threshold 0, hop 1, all-MiniLM-L6-v2 embeddings, max_tokens 512,
  temperature 0.1; the memory section of the agent prompt (`format_task_prompt_with_insights`, `format_task_context`).
- **Scope:** one store for all agents of a run, tasks one at a time (G-Memory keeps one store per multi-agent system
  and benchmark and runs tasks in order).
- **Changes and why:**
  1. Our agents do not converse: each tool call is one state (action = the call, observation = its output, both cut at
     2,000 characters), added with no upstream agents, as the official AutoGen workflow passes `upstream_agent_ids=[]`.
     The role projector stays off, the official default.
  2. Success label (`Resolved`) = the session's best validation score beats the entity-table reference; test labels
     are never used. Feedback text = best validation score, reference score, stop reason. A failed tool call gets
     reward −1 (FEVER's invalid action), so the storage-time filter of failed steps applies.
  3. The memory section goes into the first user message once; the official workflow re-renders it at every step
     because its agent sees no history, ours keeps the conversation.
  4. The task text includes the cutoff date: G-Memory merges tasks with identical text into one query node.
  5. Text written for ALFWorld is replaced at run time (`PROMPT_OVERRIDES` and the key-steps example in
     `gmemory_service.py`): "a household environment" → "a relational database and feature engineering tasks" in the
     success-critique system prompt; the object-state checks of the mistake-detection prompt → whether the feature SQL
     returned one row per seed and described the entity before the seed time; the ALFWorld key-steps example → a short
     rel-f1 example (a database not used in this study).
  6. The LLM is the study's model through the same service (`OPENAI_API_BASE`/`OPENAI_API_KEY` set for the service).
     G-Memory's code sends no reasoning setting; DeepSeek's API (used since 10-21) thinks by default, and the reasoning
     counts against G-Memory's `max_tokens` 512 (a reply cut there returns no text, which G-Memory turns into an empty
     answer). G-Memory's own calls therefore go in DeepSeek's non-thinking mode, as the paper's models (GPT-4o-mini,
     Qwen2.5) are non-reasoning; set in our adapter (`GMEMORY_THINKING`), G-Memory's code unchanged. The agents themselves
     use the study's setting (thinking, low).
- **Checked (10-20):** two fake sessions: the first stores the trajectory and its extracted key steps (557 tokens);
  the second retrieves it (one relevance-scoring call) and the agent prompt shows it in G-Memory's format.

## AWM (Wang et al., ICML 2025)

- **Code:** prompts from the official repository zorazrw/agent-workflow-memory @ 8c0ff8c (Apache-2.0), vendored in
  `third_party/awm/` (`instruction.txt`, `one_shot.txt` unchanged); the online loop of `webarena/pipeline.py` and
  `webarena/induce_prompt.py` reimplemented in `Run.awm_update` (harness), since the released code drives a browser.
- **Verbatim:** the online schedule (after every task: judge success, then induce workflows again from all successful
  experiences); at most one trajectory per task template, sampled at random (`num_samples` 1); the prompt =
  instruction + one-shot example + `## Concrete Examples` (`Query:` and `<think>`/`<action>` steps, actions only) +
  `## Summary Workflows`; temperature 1.0, at most 2,048 output tokens; the reply appended to the agent's system prompt
  (`sys_msg += '\n\n' + workflows`); same model as the agent.
- **Scope:** one workflow memory per agent and database (the agent owning one task), as ACE and as pre-registered:
  AWM's memory belongs to the agent that works through a website's tasks; a database-wide memory shared by the task
  agents would be our extension and is not run.
- **Changes and why:**
  1. Success = the study's signal (validation better than the entity-table reference), AWM's `gt` criterion in place of
     its LLM evaluator; test labels are never used.
  2. A step = one assistant turn: `<think>` = its text (or, when empty, its reasoning text), `<action>` = its tool calls
     as `name(arguments)`; calls that returned an error are left out, as AWM drops invalid actions; an action is cut at
     20,000 characters (the harness's limit for tool outputs).
  3. The web wording of the instruction is replaced (`AWM_OVERRIDES`): "web navigation tasks" -> "database feature
     engineering tasks", "(input text, button strings)" -> "(task-specific values such as time windows, thresholds and
     filter values)", the ids of "Search" or "Customers" -> "names of tables and columns"; the rest verbatim.
  4. The one-shot example (shopping-site clicks) is replaced by `one_shot_relbench.txt`, written for this study in the
     same format on rel-f1 (a RelBench database not in the study), whose SQL reads no rows after the seed time.
  5. The web-action reminders `induce_prompt.py` appends (`click('id')`, `select_option`) are left out.
  6. A task template = one prediction task (its sessions at different cutoffs are instances of it).
  7. Induction runs in DeepSeek's non-thinking mode (`AWM_THINKING`, 10-21): AWM induces with a non-reasoning model
     (GPT-4) within 2,048 output tokens; with thinking on, the reasoning used up that budget (`finish_reason` length)
     and most induced workflows were empty, so the first AWM runs were discarded and rerun. The agents themselves use
     the study's setting (thinking, low), as with G-Memory.

## DeepPrep (Fan et al., PVLDB 19(11), 2026)

- **Code:** the official repository ruc-datalab/DeepPrep @ b4e64b0 (no license file; ask the authors before the
  artifact is published), vendored in `third_party/deepprep/` (`SOURCE.md`), run by `tools/relbench/deepprep_arm.py`.
- **Verbatim:** the tree-based agentic reasoning loop (`TreeBasedAgenticReasoningAgent.reasoning_step`: `<think>`,
  exploratory `<operator>` chains executed with their observations, a final `<solution>` chain ending in Terminate),
  its prompts (`PromptGenerator.tree_based_agentic_reasoning_generate`), its 31 operators and rule executor, and the
  settings of its configuration for API models (`_CONFIG_tree_based_agentic_reasoning_claude.yaml`: max_explore_turn 5,
  max_explore_op 50, agent_max_err_cnt 5).
- **Scope:** DeepPrep keeps nothing between tasks: it searches every task and cutoff from the start.
- **Changes and why:**
  1. The LLM client is the study's model and service (every call recorded); the FastAPI/Redis execution service is
     replaced by the same executor calls in process (copy, step, simulate).
  2. The target-table description (DeepPrep's benchmarks give a fixed target schema) is the task's feature table: one
     row per (entity, seed_time), numeric features, at most 100 columns, no rows after seed_time.
  3. The input tables are the database at the cutoff (rows dated at or before test_k) plus `seeds`; DeepPrep explores on
     2,000 training seeds (its benchmarks are small tables), then its solution runs on the 50,000-seed training sample,
     the validation seeds and the test seeds, each within 600 s (the statement timeout of every other method's feature
     SQL; DeepPrep's own client also waits 600 s for its execution service). A run past 600 s counts as no solution and
     its time counts as validation time.
  4. A solution is checked for leakage like every method's features; a leaking solution is returned to the agent as an
     error, as DeepPrep returns any failed solution.
  5. Speed only, what the agent sees unchanged: tables are printed from their first rows (DeepPrep deep-copies a whole
     table to print its head), and a simulation shares the unmodified tables instead of copying all of them.
  6. Feature names are reduced to letters, digits and `_` before the fixed LightGBM (LightGBM rejects JSON characters).

## AgentSM (Biswal et al., arXiv 2601.15709, preprint)

- **Code:** no official code (the paper's anonymous repository has expired; two files survive on the Wayback Machine:
  the question generator and the trajectory parser). Reimplemented from the paper in `tools/relbench/agentsm.py`
  (offline build and online memory) and `Run.agentsm_sql` in the harness; embeddings from
  `tools/relbench/embed_service.py` (all-MiniLM-L6-v2 in the Python 3.12 environment).
- **As in the paper:** memory per database, built offline once before evaluation and read-only during it (§3.2,
  Eq. 1); Algorithm 1: GenQ(S, K, Q) from the schema description, external knowledge and up to 5 of the database's
  own tasks (the archived generator passes 5 exemplars from the evaluation set), global budget n = 100 (the archived
  `TOTAL_QUESTIONS`) split over the databases in proportion to their share of evaluation tasks (rel-stack: 15 of 46
  sessions → n = 33); synthetic tasks run by an agent with only schema and SQL tools, answers not checked; each step
  classified into exploration / execution / validation by rules, saved as markdown with model-written headers, outputs
  cut at 1,000 characters (archived parser); retrieval of the single most similar stored task of the same database by
  MiniLM similarity of the task text, returning the requested phase (exploration by default), called by the planner
  before it starts; a schema-linking sub-agent with vector search over columns and a 5-step budget; SQL self-repair on
  failure; composite tools from consecutive tool sequences within one phase (support ≥ τ, at most size 3, tools seen in
  several phases excluded), named and summarised by the model.
- **Choices the paper leaves open:** τ = 0.5, composite size ≤ 3; the synthesis agent's budget 20 model calls;
  the headers come from the study's model (the paper names a lightweight model, the archived parser uses fixed names);
  exact inner-product search over normalised MiniLM vectors (what a FAISS flat index computes) instead of a FAISS
  index object; the schema linker returns the mapping as text.
- **Changes and why:**
  1. A "question" is a prediction task: GenQ's prompt is the archived one with "Text2SQL questions" read as the
     benchmark's prediction tasks, and the database's own task descriptions as exemplars.
  2. The phase rules follow our tools: list/describe/join-path/check-join and LIMIT probes are exploration; other
     SQL and validate_features are execution; steps after the last execution step are validation.
  3. The paper's agents write Python code that calls tools; ours call the same tools as JSON function calls, the
     interface every method shares.
  4. The planner's step limit is the shared 40 model calls; the schema linker's and the SQL repair's model calls are
     counted in the session's cost but not in the planner's budget, so the architecture is not cut short.
- **Not cited:** the abstract's "25% fewer tokens, 35% shorter trajectories": the paper's Table 2 shows AgentSM's
  input tokens above the baselines'.

## FeatPilot (Liang et al., ICDE 2025)

- **Code:** the paper's released code (anonymous.4open.science/r/FeaturePilot-C308, read 10-21: `Search_algo/search.py`,
  `search_utils.py`, `rank_and_argu.py`, `Data_preprocess/collect_IQ_FI.py`, `Dataset_splitter.py`) works on CSV tables
  with AutoGluon, a GPU LSTM and BERT embeddings and has no database interface; FeatPilot is reimplemented in
  `tools/relbench/featpilot.py`, which uses the harness (`Run`) for the database copy, the appends, the seed tables, the
  reference columns, `Run.evaluate` and `Run.audit`. No LLM: a session has no tokens and no model calls; its tool calls
  are the SQL statements it runs (category probe) and one validation (the final feature SQL).
- **As in the paper:** utility gain UG = FI × IQ (Theorem 1); IQ = share of base rows with a non-null feature value
  (Definition 8); FI = the utility gain on the rows the feature augments (Definition 7 with Lemma 3; the released
  `compute_FI` drops the rows where the feature is null); breadth-first search from the base table, one more join per
  hop, no table twice on a path ("avoid cyclic joins"); Pruning Principle 1 (a path with IQ < T_IQ contributes no
  features and is not extended); Pruning Principle 2 (a min-heap keeps the H (feature, path) pairs with the largest
  FI × IQ; a pair below the heap's minimum is dropped); as in the released `search.py`, only the H paths of a hop with
  the highest IQ are extended; aggregation over 1:m joins (count, mean, min/max of numeric columns, one-hot of
  categorical columns); exploitation: up to B features taken from the heap one at a time by FI × IQ with the weight
  decay of similar features; B = 10, the paper's largest budget; the model is trained on the base table augmented with
  the chosen features. FeatPilot runs from scratch for every task and cutoff (it keeps nothing between tasks).
- **Choices the paper leaves open:** T_IQ = 0.1; H = 30 (the paper requires H > B and sets H to a multiple of B; the
  released code uses one value, `max_keep`, for the heap and the path beam); the number of hops = the entity table's
  eccentricity in the key graph, so that every table of the database is a candidate table (2 from users, posts and
  studies; 4 from facilities), as FeatPilot's discovery step returns every table within k joins and its DFS baseline
  uses a depth that covers all candidate tables; categorical = text or integer column with at most 50 distinct values
  (PostgreSQL statistics), one-hot over its 10 most common values; weight-decay neighbours = chosen features with
  |Spearman| ≥ 0.5 on the training sample; FI holdout = the seeds of 20% of the training sample's entities (seed 42),
  at least 200 training and 50 holdout rows (otherwise FI = no gain).
- **Changes and why:**
  1. Base table = the seed table with the reference columns (the entity table's numeric and time columns, the input of
     RelBench's LightGBM baseline); the entity's own categorical and text columns, which the reference leaves out, are
     candidates of the empty path (FeatPilot's base table keeps all its columns and AutoGluon encodes them). The entity
     row is bounded by seed_time like every other table (`Run.reference_sql` joins it unbounded; on user-engagement a
     seed's users row is dated after its seed_time, and the audit flagged the reference columns accountid and
     days_since_creationdate as reading later data). The reference scores in run.json remain `Run.evaluate` of
     `Run.reference_sql`, as in every arm.
  2. Join graph = RelBench's declared primary and foreign keys in both directions (child → parent m:1, parent → child
     1:m) instead of a discovery system (Aurum, Auctus).
  3. Time: every table on a path that has a time column contributes only rows dated at or before the seed's
     seed_time (a LATERAL subquery bound by the seed row), as the study's feature contract requires; FeatPilot's
     datasets have no time.
  4. Candidates are aggregates per seed. Paths with a 1:m join: count of rows, mean/min/max of numeric columns and of
     the days before seed_time of time columns, mean of booleans, count per value of categorical columns, mean byte
     length of text columns; m:1 paths: the value, an indicator per categorical value, the text length. Text embeddings
     pooled with a language model are replaced by the text length: one embedding per text feature would exceed the
     study's 100-column limit and need a model pass over millions of texts per session. Declared keys and identifier
     columns (name ending in "id" with more than 50 distinct values) are skipped. The released code keeps one joined
     row per base row (`drop_duplicates` after the join) instead of aggregating; we follow the paper.
  5. IQ is computed exactly from each path's candidate query on the training sample instead of the LSTM estimate, and
     FI is measured for every candidate with the study's fixed LightGBM instead of AutoGluon on a few selected pairs
     plus the embedding-cluster estimate; the data-point selection (Algorithm 1) is then unnecessary. Counts are 0, not
     null, for seeds without rows, so count features have IQ = 1; the IQ of a path (Principle 1 and the beam) is the
     share of training seeds reaching at least one row through it.
  6. FI is measured per path: the base table augmented with all candidates of the path is fitted once on the training
     entities, and FI(f) = the holdout utility on the rows f augments minus the utility with f's values permuted
     among those rows (mean of 3 permutations), i.e. permutation importance, which is also what AutoGluon's
     `feature_importance` (used by the released code's importance filtering) computes. The released `compute_FI` fits
     one AutoGluon model per (feature, path) and subtracts the base table's utility on all rows. One fit per candidate
     (150 to 400 per session) was tried first and took over 20 minutes per hop on the shared machine (about twelve
     8-thread LightGBM cells at once). The utility is compared on the same rows, not with the base table on all rows:
     the rows a path reaches are the active entities, whose labels differ from the rest, and a base utility on all rows
     would credit any feature of such a path with that difference.
  7. The FI holdout holds out whole entities: the released code splits base rows by their id
     (`Dataset_splitter.new_map_split`); a seed table repeats an entity at several seed times, and a split of seeds
     credits features that identify the entity (in the cutoff-1 test on site-success such features led the heap).
  8. Pruning Principle 2's floor is FI ≤ 0 (no measured gain); the released ranking always takes B features.
  9. Weight decay: similarity = |Spearman| of the feature values on the training sample instead of the cosine of BERT
     embeddings of column names and sampled values; decayed FI = FI × mean(1 − sim) over the chosen neighbours (we read
     the paper's FI(f) = 1/|N| Σ FI(f_i)(1 − sim(f, f_i)) with FI(f) in place of FI(f_i)). The released ranking instead
     multiplies the UG of the same column reached by another path by the share of rows it still leaves empty; here every
     path gives a different aggregate, so that rule never applies.
  10. Statement limits: a path whose candidate query takes over 300 s on the training sample is pruned; a candidate
     whose path would make the final SQL's estimated time on the larger of the validation and test seed tables exceed
     400 s is skipped (the study's 600 s statement limit applies to every method); if scoring the final SQL fails, the
     most expensive path is dropped and the SQL scored again (recorded in the session as `evaluate_fallbacks`).
  11. The downstream model is the study's fixed LightGBM instead of AutoGluon; the search never reads the validation
     seeds or test labels, which are used only by `Run.evaluate` for the reported scores.
  12. Algorithm 2 decrements B at every heap insertion and loops while B > 0; read literally, the search ends after the
     first hop whenever B pairs qualify, which contradicts the paper's multi-hop results. The search runs to the hop
     limit and B applies to the exploitation only, as in the released code (`search` has no budget; `rank_and_argu`
     takes B features from the heap).
  13. T_IQ also drops single features whose IQ is below it (e.g. a mean over a mostly null column); the paper applies it
     to paths. A path below T_IQ is not extended, as the paper says; the released code still extends it when it is
     among the K paths of the hop with the highest IQ.
  14. Run settings that do not change any computation: the harness's arrival order of run 1 per cutoff; one process
     per database; path queries of one hop run 4 at a time; `OMP_WAIT_POLICY=PASSIVE` (idle OpenMP threads sleep
     instead of spinning on the shared machine; reference scores are identical to the other arms').
- **Checked (10-21):** rel-stack user-badge and rel-trial site-success at cutoff 1, with one fit per candidate and a
  holdout of seeds (before changes 6 and 7): the feature SQL runs, the audit is clean, user-badge validation AUC 0.846
  against the reference's 0.598 (search 5 min), site-success search 10 min over 16 paths of up to 4 joins.
