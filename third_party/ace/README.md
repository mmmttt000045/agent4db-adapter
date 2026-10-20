# ACE (vendored, unmodified)

Files of ACE (Zhang et al., "Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models",
ICLR 2026) used by the RelBench study's ACE baseline (`exp/2026-10-20-relbench/README.md` §1.3). License: Apache-2.0
(`LICENSE`).

From https://github.com/ace-agent/ace at commit `82709de`:
- `reflector_prompts.py` = `ace/prompts/reflector.py`, `curator_prompts.py` = `ace/prompts/curator.py` (unchanged;
  the baseline uses `REFLECTOR_PROMPT_NO_GT` and `CURATOR_PROMPT_NO_GT`, as ACE does without ground-truth labels);
- `playbook_utils.py` (unchanged): bullet parsing, counters, `apply_curator_operations`, `get_playbook_stats`,
  `extract_json_from_text`, `extract_playbook_bullets`;
- `utils.py`: only `get_section_slug` from `ace/utils.py`, the one function `playbook_utils.py` imports (the rest of
  that file needs openai and tiktoken).

From https://github.com/ace-agent/ace-appworld at commit `928e868`:
- `appworld_playbook_block.txt`: the lines of `experiments/prompts/appworld_react_generator_prompt.txt` that give the
  playbook to the agent ("Read the **Playbook** first ..."), with `{{ playbook }}` filled by the harness.

The empty playbook (seven section headers) is `ACE._initialize_empty_playbook` in `ace/ace.py`, reproduced in the
harness.
