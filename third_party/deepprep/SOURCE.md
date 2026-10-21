# DeepPrep (vendored source)

Source of DeepPrep (Fan et al., "DeepPrep: An LLM-Powered Agentic System for Autonomous Data Preparation",
PVLDB 19(11): 3371–3384, 2026), copied from https://github.com/ruc-datalab/DeepPrep at commit `b4e64b0`:
`src/`, `app/` (without `static/`), `_config/`, `_values/`, `requirements.txt`, `README.md`, unchanged.
Left out: `assets/`, `chatapp/`, `data_synthesis/`, `example/`, `pdf/`, `git_push.py` (not used by the agent).

The repository has no license file. It is used here to run DeepPrep as a baseline of the RelBench study
(`tools/relbench/deepprep_arm.py`); permission from the authors is needed before this copy is redistributed,
otherwise a public release points to the official repository instead.

`tools/relbench/deepprep_arm.py` runs a scratch copy of this folder (DeepPrep writes its configuration and logs in its own
directory) and changes only, at run time: the base configuration's data paths and benchmark list (no benchmark data
is loaded), and the display settings its API-model configuration lacks (taken from its base configuration).
