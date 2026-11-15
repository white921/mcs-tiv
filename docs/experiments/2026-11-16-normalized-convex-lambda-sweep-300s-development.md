# 正規化凸結合式 lambda 300秒スイープ

- 台帳ID: `2026-11-16-normalized-convex-lambda-sweep-300s-development`
- 状態: `running`
- 位置づけ: `development`
- 開始日時: 2026-11-16 02:00:07 JST
- 終了日時: 未開始
- 実験ディレクトリ:
  - `results/runs/normalized-convex-lambda090-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda093-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda095-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda40over41-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda80over81-eval7-r1000-a1000-seeds33-42-300s-20261116/`

## 目的

正規化凸結合式の`lambda=80/81`は旧式の生係数比を理論上の最大値で換算した値であり、
交通性能に対する最適値ではない。2026-11-15実験で提案方式のAccept率が山下方式より
低かったため、現行値近傍でlambdaを下げ、全車平均速度を改善できる候補を探索する。

## 仮説と比較対象

- 仮説: lambdaを`80/81`から適度に下げると到着時間差項の寄与が増え、過度なRejectが減り、
  全車平均速度が改善する。
- 比較対象: `lambda=80/81`を現行基準とし、`0.90`, `0.93`, `0.95`, `40/41`を比較する。
- 変更するもの: 正規化凸結合式のlambdaのみ。
- 固定するもの: 実行ソース、seed、固定入力、交通量、Bus比率、軌道生成、競合検出、
  交渉プロトコル、`T_pred=10 s`、`N_max=40`。
- 本seed集合は過去結果を確認済みであり、候補選択専用のdevelopmentデータとする。
  採用候補を固定した後の最終評価には再利用しない。

## 候補選択規則

1. 物理衝突、異常終了、ソース変更がある候補は除外する。
2. 10 seedの全車平均速度の平均が高い候補を優先する。
3. 上位候補間のseed対応差が明確でない場合は上位2候補を600秒developmentへ進める。
4. 減少車線・継続車線の速度、流出台数、停止時間、急減速時間、最悪seedを併記し、
   一方の車線の破局的悪化を平均値で隠さない。
5. 300秒結果を見た後に候補lambda、seed、固定入力、交通条件を差し替えない。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.7 |
| lambda | `0.90`, `0.93`, `0.95`, `40/41`, `80/81` |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 300 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl`の300秒prefix |
| 交通量・Bus比率 | 要求側1000 / 受入側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 記録方針 | screeningのため大容量diagnostic traceとcheckpointを無効化し、manifest、runtime、評価指標、stdout/stderrを保存 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | 機械全体最大15（5候補×3 worker） |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| 元ブランチ | `codex/conflict-region-arrival` |
| 実行ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | 未定 |
| 記録commit | 未定 |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 300 --eval7-flows 1000 1000 --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl --bus-allocation fixed --workers 3 --deceleration-active --deceleration-convex-lambda <lambda> --no-diagnostic-traces --checkpoint-interval 0` |

実行unitは`mcs-normalized-convex-lambda{090,093,095,40over41,80over81}-300s-20261116.service`。
各候補を同一commitから作ったsparse worktreeで実行し、候補ごとに3 worker、機械全体で
実SUMO 15並列とする。正式実行前にλ=0.95・seed 33・10秒smokeがPython 3.15.1、
SUMO 1.28.0、`exit_code=0`、`source_unchanged=true`で完了した。

## 完了・完全性確認

- [ ] 5バッチ・50 runが正常完了
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] 固定入力hashと300秒prefix hashが候補間で一致
- [ ] runner/stdout/stderr、runtime、評価指標を確認
- [ ] 物理衝突と致命的ログを確認
- [ ] 候補選択規則に従って上位候補を決定
- [ ] 正常結果だけを専用commitへ保存・push

## 結果

未実行。

## 結論

- 確認できたこと: 未実行。
- 確認できなかったこと: 未実行。
- 採否・次の判断: 未実行。
- 既存の研究判断から変わったこと: 未実行。

## 限界・異常

seed 33–42は2026-11-09および2026-11-15に使用済みであり、本実験は独立holdoutではない。
300秒screeningは600秒で現れる長時間渋滞を捉えない可能性があり、候補選択後に600秒確認と
未使用seedによる最終評価を別バッチとして実施する。
