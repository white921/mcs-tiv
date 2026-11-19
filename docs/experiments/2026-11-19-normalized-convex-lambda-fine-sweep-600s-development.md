# 正規化凸結合式 lambda 0.50–0.70細密600秒スイープ

- 台帳ID: `2026-11-19-normalized-convex-lambda-fine-sweep-600s-development`
- 状態: `planned`
- 位置づけ: `development screening`
- 開始日時:
- 終了日時:
- 新規実験ディレクトリ:
  - `results/runs/normalized-convex-lambda0525-eval7-r1000-a1000-seeds33-42-600s-20261119/`
  - `results/runs/normalized-convex-lambda0550-eval7-r1000-a1000-seeds33-42-600s-20261119/`
  - `results/runs/normalized-convex-lambda0575-eval7-r1000-a1000-seeds33-42-600s-20261119/`
  - `results/runs/normalized-convex-lambda0625-eval7-r1000-a1000-seeds33-42-600s-20261119/`
  - `results/runs/normalized-convex-lambda0650-eval7-r1000-a1000-seeds33-42-600s-20261119/`
  - `results/runs/normalized-convex-lambda0675-eval7-r1000-a1000-seeds33-42-600s-20261119/`
- 既存再利用:
  - `lambda=0.50`: `results/runs/normalized-convex-lambda050-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `lambda=0.60`: `results/runs/normalized-convex-lambda060-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `lambda=0.70`: `results/runs/normalized-convex-lambda070-eval7-r1000-a1000-seeds33-42-600s-20261117/`

## 目的

1000/1000 veh/h・600秒の粗いlambdaスイープで全車平均速度が高かった`0.50–0.70`を
`0.025`刻みで細密化し、平均速度と合流側・本線側のトレードオフが最も良い領域を絞る。
本実験はlambdaを選ぶdevelopmentであり、最終的な一般性能の確認ではない。

## 仮説と比較対象

- 仮説: 粗いスイープの平均1位`lambda=0.60`付近に高性能域があるが、真の最良点は
  `0.525–0.675`の中間点にある可能性がある。
- 基準実験:
  [`2026-11-17-normalized-convex-lambda-wide-sweep-600s-development`](2026-11-17-normalized-convex-lambda-wide-sweep-600s-development.md)
- 基準から変更するもの: lambdaだけを`0.525, 0.550, 0.575, 0.625, 0.650, 0.675`へ変更する。
- 固定するもの: 実行ソース、評価式、固定入力、seed、交通量、Bus比率、時間、ログ条件、
  Python/SUMO版を粗いスイープと一致させる。
- 採否基準: 完全性・物理衝突を通過した候補について、全車平均速度を主指標とし、
  合流側・本線側速度、停止、急減速、流出、未挿入、残留、Accept率、最悪seed、標準偏差、
  seed対応差、bootstrap区間、Pareto関係を併記する。
- 結果を見た後に変更しないもの: seed、固定入力、600秒評価窓、評価式、候補点、再実行規則。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 正規化減速伝播提案 `M=(1-lambda)Z_time+lambda Z_follow` |
| ケース | Eval.7 |
| 新規lambda | `0.525, 0.550, 0.575, 0.625, 0.650, 0.675` |
| 既存再利用lambda | `0.50, 0.60, 0.70` |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl` |
| 交通量・Bus比率 | 合流側1000 / 本線側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 診断ログ | screeningのためdiagnostic traceなし、checkpointなし。manifest、runner/stdout/stderr、評価指標、物理衝突、prediction auditは保存 |
| Python / SUMO | 3.15.1 / 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | lambda昇順・seed昇順の共有queue、機械全体最大15 SUMO、1件終了ごとに次の1件を補充 |

最初は`lambda=0.525`の10件と`lambda=0.550`のseed 33–37を投入する。以後は15件の
同時完了を待たず、空いたslotへqueue先頭の1件を補充する。失敗時は新規投入を停止し、
自動再実行やseed差し替えは行わない。

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| 記録branch | `codex/normalized-convex-lambda-fine-sweep-600s-development` |
| 実行ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 実行開始時dirty | `false`を必須とする |
| scheduler | `scripts/run_lambda_shared_queue.py`。先行バッチなしのfresh queueとして起動 |
| 結果commit | 正常終了後、lambdaごとに専用commitを作成する |
| 記録commit | 本記録のcommit |

各lambdaは実行ソースcommitから作成した独立clean worktreeを使い、各結果ディレクトリを
そのworktreeの`results/runs/`へ保存する。実行条件は次の共有queue投入と等価である。

```text
scripts/run_thesis_batch.py
  --cases eval7
  --seeds 33 34 35 36 37 38 39 40 41 42
  --duration 600
  --eval7-flows 1000 1000
  --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl
  --bus-allocation fixed
  --deceleration-active
  --deceleration-convex-lambda <lambda>
  --no-diagnostic-traces
  --checkpoint-interval 0
  --run-name normalized-convex-lambda<tag>-eval7-r1000-a1000-seeds33-42-600s-20261119
```

## 監視

- 対象unit: 起動後に記録する。
- 60%未満は30分、60%以上は15分ごとにUbuntuの実状態を確認する。
- 各確認で完了/60、失敗数、最遅simulation time、実SUMO数、queueの次候補、停滞、
  traceback、ディスクを報告する。

## 完了・完全性確認

- [ ] 新規6バッチ・60 runが正常完了
- [ ] 全runが`exit_code: 0`、`source_unchanged: true`
- [ ] 実行開始時Git clean、source SHA、固定入力SHAを確認
- [ ] lambda以外の条件が全候補で一致
- [ ] Python/SUMO版、manifest、runner/stdout/stderr、評価指標を確認
- [ ] 物理衝突と致命的ログを確認
- [ ] lambda別・seed別集計と既存`0.50/0.60/0.70`を統合
- [ ] 正常結果だけをlambdaごとの専用commitで保存・push

## 結果

完了後に記録する。

## 結論

- 確認できたこと: 完了後に記録する。
- 確認できなかったこと: 完了後に記録する。
- 採否・次の判断: 完了後に記録する。
- 既存の研究判断から変わったこと: 完了後に記録する。

## 限界・異常

seed 33–42は粗いlambda探索に使用済みであり、今回も同じseedを使って細密候補を選ぶ。
したがって本実験は独立holdoutではなく、lambda固定後に未使用seedで最終評価する必要がある。

## 次の作業

1. 新規6候補の実行と完全性監査を完了する。
2. 既存3候補と統合し、seed対応差と不確実性を評価する。
3. lambdaを固定し、診断trace・checkpoint付き確認と未使用seed最終評価へ進める。
