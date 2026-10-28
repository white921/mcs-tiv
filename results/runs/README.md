# Yamashita baseline result catalog

This branch keeps validated Yamashita TIVtep (`decision_method: thesis-tiv`)
results. The 600-second reproduction baseline and the 300-second axis-fixed
control are separate experiment directories because their source revisions,
durations, and comparison purposes differ.

| Duration | Experiment directory | Cases and seeds | Source revision | Purpose |
| --- | --- | --- | --- | --- |
| 600 s | `yamashita-tivtep-eval3-eval5-eval7-fixed-600s-documented-seeds-20261025-bbb46e5/` | Eval.3 and Eval.5: seeds 1–5; Eval.7: seeds 1, 2, 3, 7, 11 | `bbb46e5f8ed2dd5c170b16fc3c159ea042de2a40` | Formal reproduction baseline for comparison with the thesis results. This predates the Eval.5 upper-road axis fix. |
| 300 s | `yamashita-axisfix-eval3-eval5-fixed-300s-seeds1-5-20261028T/` | Eval.3 and Eval.5: seeds 1–5 | `9e44e368e599ee76e1772e3c7b78aba628402ab6` | Axis-fixed control for same-condition comparison with the proposed-method lambda sweep. |

Each experiment remains self-contained. Read its top-level manifest and
summary first, then the per-case/per-seed `manifest.json` and
`evaluation-metrics.json`. Do not compare the 600-second aggregate directly
with a 300-second aggregate as if duration and source revision were identical.

All included run manifests report `exit_code: 0`, `source_unchanged: true`, and
`decision_method: thesis-tiv`.
