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
  1. The Generator is our tool-using agent instead of a single JSON answer; `submit` takes an optional `bullet_ids` so
     that the Reflector can tag the bullets used (ACE's Generator reports bullet ids).
  2. Reflector inputs: question = task description and cutoff; reasoning trace = the session transcript (tool outputs
     cut at 20,000 characters, as the released code cuts outputs); predicted answer = the submitted feature SQL;
     environment feedback = the validation scores (or errors) of the session and its stop reason. RelBench has no
     single correct answer, so the no-label variant is the one that applies; validation scores are execution
     feedback (ACE §4.3).
  3. No multi-epoch offline adaptation: revisiting earlier cutoffs would expose later labels.
  4. The playbook shown to the agent keeps the counters (as in the finance code); the AppWorld code strips them.

## G-Memory (Zhang et al., NeurIPS 2025)

- **Code:** the official repository bingreeky/GMemory @ 7b581c5, used unchanged from a local copy that is not
  committed (the repository has no license; the authors are asked for permission before the code or a diff of it is
  published). It runs in its own Python 3.12 environment (`results/ext/venv-gmem`, the versions pinned in its
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
  6. The LLM is the study's model through the same gateway (`OPENAI_API_BASE`/`OPENAI_API_KEY` set for the service);
     G-Memory's calls go without a reasoning setting, as its code sends none.
- **Checked (10-20):** two fake sessions: the first stores the trajectory and its extracted key steps (557 tokens);
  the second retrieves it (one relevance-scoring call) and the agent prompt shows it in G-Memory's format.
