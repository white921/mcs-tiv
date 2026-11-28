# 形状別 heading/yaw unsupported 帰属診断

- 台帳ID: `2026-11-28-topology-heading-attribution-diagnostic`
- 状態: `completed`
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
- source commit: `79b14b4effe40570e6310f0e1962839be8fc2f49`。
- raw output: UbuntuData上の `mcs-tiv-diagnostic-artifacts/`。
- 完了後、manifest、metrics、unsupported集計、物理衝突、固定入力hash、ログを検証する。
- 失敗runは自動再実行しない。diagnostic raw traceは、原因の説明と回帰テストを
  永続化した後にretention policyに従って縮約する。

## 結果

有効15 runはすべて正常終了し、完全性監査に成功した。物理衝突は0。

| 条件 | run | attempt | unsupported | unsupported率 | 詳細保持 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Eval.3 500/500/500 | 5 | 2,940 | 171 | 5.82% | 147 |
| Eval.5 300/300/300/300 | 10 | 3,363 | 335 | 9.96% | 327 |

- 詳細付きunsupportedは合計474件で、474/474件が停止軌跡、finite yawなし、
  lane positionあり、既知lane IDだった。理由はすべて
  `trajectory has no usable heading or yaw`、反実仮はすべて`reject`、path typeは
  すべて`planned`だった。
- Eval.3のlane IDは`left_0` 31件、`bottom_0` 48件、`-right_0` 68件。
  Eval.5は`bottom_0` 199件、`left_0` 27件、`top_0` 90件、`-right_0` 11件。
- source commit、開始時clean、固定入力hash、必須artifact、5 checkpoint以上、
  prediction counter、物理衝突0を15/15 runで検証した。数値の正本はUbuntuData上の
  `topology-heading-attribution-summary-20261128.json`。
- 帰属は関連を示す診断であり、性能差の因果推定ではない。ただしlane metadata heading
  fallbackアブレーションの事前gate（詳細20件以上、3比率各80%以上）は3比率すべて
  100%で成立したため、別記録の反証実験へ進む。

### 2026-11-28 起動とEval.7の送出前失敗

- 主unit: `mcs-topology-heading-attribution-20261128.service`、invocation
  `cd5152f17686490fac2df5355a298a4b`。preflightはsource clean、SUMO 0、固定入力15本、
  machine-wide 15 workerを確認した。
- Eval.3と5本、Eval.5と5本はSUMOを開始した。Eval.7の5本はすべてSUMO起動前に
  `FileNotFoundError` で終了した。失敗の直接原因は、スケジューラがEval.7 1000/1000の
  固定入力に `fixed_inputs/thesis/eval7/seed-<seed>.jsonl` を暗黙選択し、実在する
  flow-sweep入力を `--fixed-input-override` で指定していなかったことである。
- 失敗したEval.7は自動再実行しない。出力とrunner logを失敗証跡として保持する。
  スケジューラに明示的なflow-sweep入力を追加し、コマンド生成テストで
  3 cohortすべてのoverrideを確認する。
- 空いた5枠には、失敗runの再実行ではなく、unsupportedの主要対象である
  Eval.5 300/300/300/300のseed 18–22を別cohortとして起動した。unitは
  `mcs-topology-heading-attribution-eval5-extra-20261128.service`、invocationは
  `b97245a4f9904567b54771b6626d1a45`。起動後の実SUMO数は15。

### 2026-11-28 完了監査

- 有効15 runは15/15成功、失敗0、物理衝突0。完了後にSUMO 0、runner 0を確認した。
- 当初失敗したEval.7 seed 33–37は再実行しておらず、本集計のvalidated runには
  含めていない。失敗証跡は保持している。
- finalizer sourceは`148ea5359a478885c49e66176ff83df5b7ed1f45`、実行結果の
  `validated_run_count`は15。
