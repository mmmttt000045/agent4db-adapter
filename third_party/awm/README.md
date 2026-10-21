# AWM (vendored prompts, unmodified)

Prompt files of AWM (Wang et al., "Agent Workflow Memory", ICML 2025) used by the RelBench study's AWM baseline
(`exp/2026-10-20-relbench/README.md` §1.3). License: Apache-2.0 (`LICENSE`).

From https://github.com/zorazrw/agent-workflow-memory at commit `8c0ff8c`:
- `instruction.txt` = `webarena/prompt/instruction.txt` (the induction instruction of AWM's online WebArena pipeline);
- `one_shot.txt` = `webarena/prompt/one_shot.txt` (its one-shot example: concrete web trajectories, then the workflows
  induced from them).

The harness (`Run.awm_update` in `tools/relbench/harness.py`) follows `webarena/pipeline.py` and `webarena/induce_prompt.py`:
after every task, workflows are induced again from all successful past trajectories (at most one per task template,
sampled at random), with the instruction, the one-shot example and the examples in AWM's format (`Query:` / `<think>` /
`<action>`), at temperature 1.0 and at most 2,048 output tokens, and the reply is appended to the agent's system prompt
(`webarena/agents/legacy/agent.py`: `sys_msg += '\n\n' + workflows`).

Not used, with the reason (also in `exp/2026-10-20-relbench/reproduction-notes.md`):
- the web wording of `instruction.txt` ("web navigation tasks", "(input text, button strings)", the ids of "Search" or
  "Customers") is replaced at run time by database wording (`AWM_OVERRIDES` in the harness), the rest verbatim;
- `one_shot.txt` shows shopping-site click sequences; the harness uses `one_shot_relbench.txt`, written for this study
  in the same format, on rel-f1 (a RelBench database not used in the study);
- the two web-action reminders `induce_prompt.py` appends to the workflows (`click('id')`, `select_option`) do not
  apply to SQL tools and are left out.
