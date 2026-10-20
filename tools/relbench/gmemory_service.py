#!/usr/bin/env python3
"""G-Memory (Zhang et al., NeurIPS 2025) as a JSON-lines service for the RelBench harness (exp/2026-10-20-relbench).

Runs the official memory code (bingreeky/GMemory @ 7b581c5, a local copy that is not committed: the repository has no
license) unchanged, in its own Python 3.12 environment, with the settings of the released runs: successful_topk 1,
failed_topk 0, insights_topk 5, threshold 0, hop 1, all-MiniLM-L6-v2 embeddings, max_tokens 512, temperature 0.1.
The memory is one store for all agents of a run (G-Memory keeps one store per multi-agent system and benchmark).

Only text written for ALFWorld is replaced (PROMPT_OVERRIDES below, published with the paper's reproduction notes):
the key-steps example of extract_true_traj_user_prompt, "a household environment" in the success-critique prompt, and
the object-state checks of detect_mistakes_system_prompt. Our agents do not converse, so each tool call is one state
(action = the call, observation = its output) with no upstream agents, as the official AutoGen workflow passes
`upstream_agent_ids=[]`; the role projector stays off (the official default).

Protocol: one JSON request per line on stdin, one JSON reply per line on stdout.
  {"op": "begin", "task_main": ..., "task_description": ...}  -> {"prompt": <memory section>, "n_success", "n_insights", tokens}
  {"op": "step", "agent", "action", "observation", "reward"}  -> {"ok": true}
  {"op": "end", "label": bool, "feedback": str}                -> {"ok": true, tokens}
Every reply carries the G-Memory LLM tokens spent since the previous reply (prompt_tokens, completion_tokens).

  results/ext/venv-gmem/bin/python tools/relbench/gmemory_service.py --repo results/ext/GMemory --working-dir <run>/gmemory
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys

PROMPT_OVERRIDES = {
    "critique_success_rules_system_prompt": (
        "You will be given successful tasks trials in which you were placed in a household environment and tasks to complete.",
        "You will be given successful tasks trials in which you were placed in a relational database and feature engineering tasks to complete.",
    ),
    "detect_mistakes_system_prompt": (
        """The reason for the failure is that the final task state does not match the required task state.

You need to carefully analyze the final state of the failed trajectory and compare it with the required task state to identify inconsistencies. Please check:
    - Whether the state of the target object matches the required task state.
    - Whether the target object has been placed in the required location.

Rules:
    - Any object with the same name (even with different numbers) satisfies the task requirements. For example, if the task requires "an apple" and the agent finds "apple 2," it is still considered correct.
    - Your analysis must ignore numbers and ensure matching is based only on names and states.""",
        """The reason for the failure is that the submitted features did not reach a better validation score than the reference features.

You need to carefully analyze the final state of the failed trajectory and compare it with the required task state to identify inconsistencies. Please check:
    - Whether the submitted feature SQL ran and returned one row per seed.
    - Whether the features describe the target entity before the seed time.""",
    ),
}

EXTRACT_EXAMPLE = (
    """### Task
You are in the middle of a room. Looking quickly around you, you see a bed 1, a desk 2, a desk 1, a drawer 6, a drawer 5, a drawer 4, a drawer 3, a drawer 2, a drawer 1, a garbagecan 1, a laundryhamper 1, a safe 1, a shelf 6, a shelf 5, a shelf 4, a shelf 3, a shelf 2, and a shelf 1.
Your task is to: look at bowl under the desklamp.""",
    """### Task
Predict for each driver whether they finish in the top 3 in the next race (rel-f1, a database not used in this study).""",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--working-dir", required=True)
    ap.add_argument("--model", required=True)
    a = ap.parse_args()
    out = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout = sys.stderr  # G-Memory prints progress (and, in mas/llm.py, the API key) to stdout
    repo = os.path.abspath(a.repo)
    working_dir = os.path.abspath(a.working_dir)
    os.chdir(repo)  # mas/llm.py reads configs/configs.yaml relative to the working directory
    sys.path.insert(0, repo)
    with contextlib.redirect_stdout(io.StringIO()):
        import mas.llm as gllm
        from mas.memory.common import AgentMessage
        from mas.memory.mas_memory import GMemory
        from mas.memory.mas_memory import prompt as gprompt
        from mas.utils import EmbeddingFunc
    spec = importlib.util.spec_from_file_location("gmem_format", os.path.join(repo, "tasks", "mas_workflow", "format.py"))
    fmt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fmt)

    P = gprompt.GMemoryPrompts
    for name, (old, new) in PROMPT_OVERRIDES.items():
        text = getattr(P, name)
        assert old in text, f"{name}: the text to replace was not found"
        setattr(P, name, text.replace(old, new))
    i = P.extract_true_traj_user_prompt.index("## Example 1:")
    j = P.extract_true_traj_user_prompt.index("Now it's your turn!")
    example = P.extract_true_traj_user_prompt[i:j]
    assert EXTRACT_EXAMPLE[0] in example
    new_example = """## Example 1:
""" + EXTRACT_EXAMPLE[1] + """

### Trajectory
... The agent has inspected the tables drivers, results and races
Act 7: run_sql: SELECT count(*) FROM results r JOIN races ra ON ra.raceid = r.raceid WHERE ra.date <= '2010-01-01'
Obs 7: {"result": [[24104]]}
Act 8: validate_features: SELECT s.driverid, s.seed_time, count(r.*) FILTER (WHERE r.positionorder <= 3) AS podiums FROM {seeds} s LEFT JOIN results r ON r.driverid = s.driverid ... GROUP BY 1, 2
Obs 8: {"validation_roc_auc": 0.79, "improved": true}
Act 9: submit
Obs 9: {"ok": true}
reward: True

### Output
Construct the overall approach: Count each driver's past podiums before the seed time and validate them as features.
Inspect the results and races tables to find how results are dated.
Aggregate podium finishes per driver over races dated before the seed time.
Validate the features and submit them.

"""
    # the template is filled with str.format: braces of the example are escaped
    new_example = new_example.replace("{", "{{").replace("}", "}}")
    P.extract_true_traj_user_prompt = P.extract_true_traj_user_prompt[:i] + new_example + P.extract_true_traj_user_prompt[j:]
    P.extract_true_traj_user_prompt.format(task="", trajectory="")  # fails here, not in a session, if a brace slipped through

    os.makedirs(working_dir, exist_ok=True)
    with contextlib.redirect_stdout(io.StringIO()):
        llm = gllm.GPTChat(model_name=a.model)
        memory = GMemory(namespace="g-memory", global_config={"working_dir": working_dir, "hop": 1}, llm_model=llm,
                         embedding_func=EmbeddingFunc("sentence-transformers/all-MiniLM-L6-v2"))
    last = [gllm.prompt_tokens, gllm.completion_tokens]

    def reply(v):
        v["prompt_tokens"] = gllm.prompt_tokens - last[0]
        v["completion_tokens"] = gllm.completion_tokens - last[1]
        last[:] = [gllm.prompt_tokens, gllm.completion_tokens]
        out.write(json.dumps(v, ensure_ascii=False) + "\n")

    reply({"ready": True})
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        try:
            if req["op"] == "begin":
                memory.init_task_context(req["task_main"], req["task_description"])
                success, _, insights = memory.retrieve_memory(query_task=req["task_main"], successful_topk=1, failed_topk=0,
                                                              insight_topk=5, threshold=0.0)
                shots = [fmt.format_task_context(t.task_description, t.task_trajectory, t.get_extra_field("key_steps")) for t in success]
                prompt = fmt.format_task_prompt_with_insights(few_shots=[], memory_few_shots=shots, insights=list(insights),
                                                              task_description=memory.summarize())
                reply({"prompt": prompt, "n_success": len(shots), "n_insights": len(insights)})
            elif req["op"] == "step":
                memory.add_agent_node(AgentMessage(agent_name=req.get("agent"), message=req["action"]), upstream_agent_ids=[])
                memory.move_memory_state(req["action"], req["observation"], reward=req.get("reward", 0))
                reply({"ok": True})
            elif req["op"] == "end":
                memory.save_task_context(label=bool(req["label"]), feedback=req.get("feedback"))
                memory.backward(bool(req["label"]))
                reply({"ok": True, "memory_size": memory.memory_size})
            else:
                reply({"error": f"unknown op {req['op']}"})
        except Exception as err:  # noqa: BLE001 - every failure goes back to the harness as a reply
            import traceback

            traceback.print_exc()
            reply({"error": f"{type(err).__name__}: {err}"})


if __name__ == "__main__":
    main()
