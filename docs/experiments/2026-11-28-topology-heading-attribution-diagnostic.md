# 形状別 heading/yaw unsupported 帰属診断

- 台帳ID: `2026-11-28-topology-heading-attribution-diagnostic`
- 状態: `planned`
- 位置づけ: `diagnostic`
- 実行対象: Ubuntu `sgnlab`

## 目的

共通 `lambda=0.95` の最終holdoutで、合流の改善は安定した一方、交差点は
prediction attemptの約8.5%が `trajectory has no usable heading or yaw` となった。
本診断は、そのunsupportedがAccept/Rejectのどちらの反実仮で、どの車両・車線・
軌跡種別に生じるかを特定する。予測式、判断、TIVtepへのfallbackは変更しない。

## 条件

| 形状 | 交通量 (veh/h) | seed | run |
| --- | --- | --- | ---: |
| Eval.3 T字路 | 500 / 500 / 500 | 13–17 | 5 |
| Eval.5 十字路 | 300 / 300 / 300 / 300 | 13–17 | 5 |
| Eval.7 合流 | 1000 / 1000 | 33–37 | 5 |

- 時間: 300 s、提案法 `lambda=0.95`、Bus比25% fixed-nearest。
- 並列: 各形状5 workerを同時起動し、machine-wide 15 SUMOを使う。
- 診断: FCD、交渉、車両状態、競合、予測、物理衝突、60秒checkpoint。
- 既存development seedを再利用する探索的診断であり、最終holdoutの主結果や
  `lambda`を変更するために使わない。

## 実装と評価

`PredictionUnsupported`に次の機械可読コンテキストを追加する。

- Accept/Rejectの反実仮種別、root/leader車両ID、割当済み車両ID
- path ID、path type、lane ID、lane position、road ID
- 時刻範囲、位置sample数、異なる位置数、yaw sample数と有限値数

主な判定は、形状別のunsupported率と上記コンテキストの分布である。
この診断だけで性能差の因果は確定しない。結果が車線・軌跡の特定パターンに
集中する場合は、別記録で最小のfallback反証実験を設計する。

## 実行・保存

- scheduler: `scripts/run_topology_heading_attribution_diagnostic.py`
- source branch: `codex/intersection-heading-diagnostic`
- source commit: 起動時manifestから追記する（現在は未検証）。
- raw output: UbuntuData上の `mcs-tiv-diagnostic-artifacts/`。
- 完了後、manifest、metrics、unsupported集計、物理衝突、固定入力hash、ログを検証する。
- 失敗runは自動再実行しない。diagnostic raw traceは、原因の説明と回帰テストを
  永続化した後にretention policyに従って縮約する。

## 結果

未実行。
