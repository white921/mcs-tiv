# 交差点のlane metadata heading fallbackアブレーション

- 台帳ID: `2026-11-28-intersection-lane-heading-fallback-ablation`
- 状態: `planned`
- 位置づけ: `diagnostic development ablation`

## 目的

現行予測器は、明示的なlane IDとlane positionで同一車線の前後関係を確定できる
場合でも、leader軌跡のheading/yawを先に復元する。交差点の停止軌跡でyawがないと
評価全体がunsupportedになり、山下TIVtepへfallbackする。本アブレーションは、
lane metadataで追従関係を完全に確定できる場合に限ってheading復元を遅延し、
unsupportedと交差点性能への影響を反証的に確認する。

## 起動gate

[heading/yaw帰属診断](2026-11-28-topology-heading-attribution-diagnostic.md)の有効15 runが
完全性監査に成功し、物理衝突0であることを先に確認する。保持された詳細付き
unsupportedが20件以上あり、次の3比率がすべて80%以上の場合だけ起動する。

1. 軌跡が停止し、finite yawがない。
2. lane positionが存在する。
3. lane IDが存在する。

gateを満たさない場合は起動せず、追加計測または別のfallback設計に戻る。

## 条件

| 形状 | 交通量 (veh/h) | seed | 本アブレーションrun |
| --- | --- | --- | ---: |
| Eval.3 T字路 | 500 / 500 / 500 | 13–17 | 5 |
| Eval.5 十字路 | 300 / 300 / 300 / 300 | 13–22 | 10 |

- 新規15 run、300 s、`lambda=0.95`、Bus比25% fixed-nearest。
- 完了済み帰属診断の同一seed・同一固定入力を現行方式対照とし、対照は再実行しない。
- 変更は`--deceleration-lane-metadata-heading-fallback`だけ。不要な場合の既存heading処理、
  予測式、`lambda`、TIVtep fallback、固定入力、並列条件は変更しない。
- 3 cohort×5 workerでmachine-wide 15 SUMO。失敗は自動再実行しない。

## 評価

- 主診断: 形状別unsupported率と現行方式からの減少。
- 安全gate: 全15 runで物理衝突0、完全性監査成功。
- 性能は同一seedの全車平均速度、停止時間、方向別速度を対応比較するが、
  development seedのため一般的優越性は主張しない。
- unsupportedが減って性能差も縮まる場合は有力な因果証拠。unsupportedだけ減る場合は、
  交差点性能差の主因を後続車項の小ささや複数競合点へ絞る。

## 実行・保存

- scheduler: `scripts/run_intersection_lane_heading_fallback_ablation.py`
- source branch: `codex/intersection-heading-diagnostic`
- source commit: 起動前に追記する。
- raw output: UbuntuData上の`mcs-tiv-diagnostic-artifacts/`。
- 完了後はmanifest、metrics、物理衝突、固定入力hash、診断artifact、checkpoint、
  致命ログを監査し、原因の説明と回帰テスを永続化してからraw traceを縮約する。
