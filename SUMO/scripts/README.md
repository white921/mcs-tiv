# SUMO Scripts

TraCI 制御、論文比較メトリクス、パラメータ探索用スクリプトを置く場所。

## Main Files

- `control.py`
  協調制御ありの実行スクリプト。`--summary-json` で論文比較用の要約を保存できる。
- `baseline_log.py`
  協調制御なしのベースライン実行。
- `controller_params.json`
  既定のコントローラパラメータ。
- `controller_sweep.json`
  第1ラウンド探索用の粗い sweep 定義。
- `tune_controller.py`
  sweep を回して `paper_alignment_score` 順に並べる。
- `refine_tuning.py`
  第1ラウンドの `ranking.json` から、第2ラウンド用の絞った sweep を生成する。
- `auto_tune_controller.py`
  `round1 -> refine -> round2` をまとめて回す粗密探索パイプライン。
- `generate_focus_sweep.py`
  上位の controller config から、`p2/p3/t_gap/k` 中心の focused sweep を生成する。
- `promote_best_config.py`
  tuning で得た `best_controller_params.json` を既定の `controller_params.json` に昇格する。
- `verify_adopted_config.py`
  採用した `controller_params.json` で cooperative/baseline を再実行し、比較レポートを出す。
- `evaluate_run_summary.py`
  `run_summary.json` を論文の時系列と安全 proxy に照らして評価する。
- `compare_run_summaries.py`
  協調あり/なしの `run_summary.json` を比較して改善量を確認する。

## Typical Workflow

1. 単発実行:
   `python scripts/control.py --nogui --controller-config scripts/controller_params.json --summary-json out/run_summary.json`
2. 結果評価:
   `python scripts/evaluate_run_summary.py out/run_summary.json`
3. 協調あり/なし比較:
   `python scripts/compare_run_summaries.py out/cooperative_summary.json out/baseline_summary.json`
4. 第1ラウンド sweep:
   `python scripts/tune_controller.py --base-config scripts/controller_params.json --sweep-config scripts/controller_sweep.json --output-dir out/tuning`
   baseline 比較込みなら `--baseline-summary out/baseline_summary.json` を追加する。
5. 第2ラウンド sweep 生成:
   `python scripts/refine_tuning.py out/tuning/ranking.json --sweep-config scripts/controller_sweep.json --output-dir out/tuning_refined`
6. 第2ラウンド sweep 実行:
   `python scripts/tune_controller.py --base-config out/tuning_refined/controller_params_refined_base.json --sweep-config out/tuning_refined/controller_sweep_refined.json --output-dir out/tuning_refined/run2`
7. まとめて自動実行:
   `python scripts/auto_tune_controller.py --base-config scripts/controller_params.json --sweep-config scripts/controller_sweep.json --output-dir out/auto_tuning`
   `--baseline-summary` を省略した場合は baseline summary を自動生成する。
8. focused round 付き自動実行:
   `python scripts/auto_tune_controller.py --base-config scripts/controller_params.json --sweep-config scripts/controller_sweep.json --output-dir out/auto_tuning --focus-round`
9. 最良設定を既定値へ昇格:
   `python scripts/promote_best_config.py out/auto_tuning/best_controller_params.json --backup`
10. 採用後の再検証:
   `python scripts/verify_adopted_config.py --controller-config scripts/controller_params.json --output-dir out/verification`
