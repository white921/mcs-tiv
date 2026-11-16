# 正規化凸結合式 lambda 0.90/0.95・600秒対応比較

- 台帳ID: `2026-11-16-normalized-convex-lambda090-095-600s-development`
- 状態: `planned`
- 位置づけ: `development`
- 開始日時:
- 終了日時:
- 実験ディレクトリ:
  - `results/runs/normalized-convex-lambda090-eval7-r1000-a1000-seeds33-42-600s-20261116/`
  - `results/runs/normalized-convex-lambda095-eval7-r1000-a1000-seeds33-42-600s-20261116/`

## 目的

300秒スイープで上位だった`lambda=0.90`と`lambda=0.95`を、同一seed・同一固定入力の
600秒Eval.7で対応比較する。長時間渋滞での速度、停止、流出量、最悪seed、安全性を確認し、
次の未使用seed最終評価に進めるlambdaを選ぶ。

## 仮説と比較対象

- 仮説: 300秒で平均値が近かった2候補は、600秒の長時間渋滞で車線別トレードオフと最悪seedに差が出る。
- 基準実験: `2026-11-16-normalized-convex-lambda-sweep-300s-development`、
  `2026-11-15-normalized-convex-seeds33-42-600s-development`の`lambda=80/81`。
- 基準から変更するもの: 正規化凸結合式のlambdaのみ。
- 固定するもの: 実行ソース、seed、固定入力、交通量、Bus比率、軌道生成、競合検出、
  交渉プロトコル、`T_pred=10 s`、`N_max=40`、診断trace、60秒checkpoint。
- 採否基準: 20/20正常終了、ソース不変、入力SHA一致、物理衝突0、必須artifactが揃うこと。
- 結果を見た後に変更しないもの: lambda、seed、duration、入力、交通条件、失敗run。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 正規化減速伝播提案のみ |
| ケース | Eval.7 |
| lambda | `0.90`, `0.95` |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl` |
| 交通量・Bus比率 | 要求側1000 / 受入側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 診断ログ | FCD、交渉、車両状態、軌道競合、予測、物理衝突、60秒checkpoint |
| Python | 3.15.1 |
| SUMO | 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | 候補ごと5、機械全体最大10 |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| 元ブランチ | `codex/conflict-region-arrival` |
| 実行ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | 完了後に記録 |
| 記録commit | 本記録のcommit |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 600 --eval7-flows 1000 1000 --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl --bus-allocation fixed --workers 5 --deceleration-active --deceleration-convex-lambda <lambda> --diagnostic-traces --checkpoint-interval 60` |

## 完了・完全性確認

- [ ] 2バッチ・20 runが正常完了
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] 実行開始時Git cleanとsource SHAを確認
- [ ] 同一seedの固定入力SHAが2候補・300秒sweep・既存600秒比較で一致
- [ ] Python/SUMO版、runner/stdout/stderr、必須artifact、終了時刻を確認
- [ ] 物理衝突0、致命的ログ0を確認
- [ ] 結果ディレクトリとrunner logだけを専用commitでpush

## 結果

完了後に記録する。

## 結論

完了後に記録する。

## 限界・異常

seed 33–42は既実験と候補選択に使用済みであり、本実験は独立holdoutではない。

