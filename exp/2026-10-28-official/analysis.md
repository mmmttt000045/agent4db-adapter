# Official API experiment status and results

All scheduled cells are shown. Only complete matched cells enter comparisons. A single sequence does not establish statistical significance.

Queue stage: evaluation. API calls: 855. Conservative spending bound: CNY 21.069; last observed account decrease: CNY 6.85; authorized cap: CNY 50.00.

| Dataset | Method | Status | Sessions | Issues |
|---|---|---|---:|---:|
| rel-stack | none | complete | 9/9 | 0 |
| rel-stack | mavra | incomplete | 6/9 | 1 |
| rel-stack | ace | incomplete | 9/9 | 0 |
| rel-stack | awm | not_started | 0/9 | 0 |
| rel-stack | gmemory | not_started | 0/9 | 0 |
| rel-trial | none | complete | 9/9 | 0 |
| rel-trial | mavra | complete | 9/9 | 0 |
| rel-trial | ace | incomplete | 3/9 | 1 |
| rel-trial | awm | not_started | 0/9 | 0 |
| rel-trial | gmemory | not_started | 0/9 | 0 |

## rel-trial

Complete five-method set: False. Published comparison available: False.

| Method | All tokens (M) | Reuse tokens (M) | Valid | Quality within stated margins |
|---|---:|---:|---:|---:|
| none | 4.215 | 2.818 | 6/9 | 3/3 |
| mavra | 2.851 | 1.280 | 6/9 | 2/3 |

Quality by task and phase (the all-cutoff result is retained; reuse is the predeclared cutoffs 2-3):

| Method | Task | Metric | All cutoffs | Reuse cutoffs | All within margin | Reuse within margin |
|---|---|---|---:|---:|---|---|
| none | site-success | mae | 0.444942 | 0.413188 | True | True |
| none | study-adverse | mae | 43.274756 | 47.152961 | True | True |
| none | study-outcome | roc_auc | 0.649634 | 0.648545 | True | True |
| mavra | site-success | mae | 0.418785 | 0.413188 | True | True |
| mavra | study-adverse | mae | 44.691687 | 45.699557 | False | True |
| mavra | study-outcome | roc_auc | 0.646981 | 0.647148 | True | True |

MAVRA mechanism audit (whole-program reuse and structured-feature reuse must not be conflated):

```json
{
  "memory_tools": {
    "find_program": 9,
    "find_features": 6,
    "compose_features": 0
  },
  "drafts": 9,
  "definitions_promoted": 8,
  "definitions_corroborated": 0,
  "programs_saved": 2,
  "rejected_gates": {
    "F1": 0,
    "F2": 0,
    "F3": 1,
    "F4": 0
  }
}
```
