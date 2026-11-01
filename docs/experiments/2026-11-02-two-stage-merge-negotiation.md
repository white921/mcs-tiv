# 早期判断と200 m実行を分ける2段階合流交渉

- 台帳ID: `2026-11-02-two-stage-merge-negotiation`
- 状態: `planned`
- 位置づけ: `development`
- 開始日時: 未開始
- 終了日時: 未完了
- 実験ディレクトリ:
  - `results/runs/two-stage-merge-eval7-r300-a1000-yamashita-seeds6-8-9-10-12-300s-20261102T`
  - `results/runs/two-stage-merge-eval7-r300-a1000-proposal-lambda2-seeds6-8-9-10-12-300s-20261102T`

## 目的

車線端まで自由走行で10秒残る位置から情報交換と承諾判断を始めながら、実際の譲歩軌道、
速度指令、車線変更は従来の200 m地点まで開始しない2段階交渉を評価する。10秒前開始で
増えた急減速が、情報交換の早期化ではなく早期の譲歩走行に起因するという仮説を直接調べる。

## 仮説と比較対象

- 仮説: 希望経路作成と承諾判断を10秒前へ移し、実行を200 mまで遅らせると、固定200 m
  方式の急減速水準を悪化させず、既知の車線端停止を防げる。
- 基準実験:
  - 固定200 m: `2026-11-01-eval7-flow-ratio-sweep`の300/1000台/時、同一5 seed。
  - 10秒前即時実行: `2026-11-01-maneuver-deadline-5seed-validation`。
- 基準から変更するもの:
  - 希望経路作成、衝突相手特定、承諾判断を車線端の10秒前から開始する。
  - 承諾時は相手ID、参加車両集合、承諾時刻、判断方式だけを予約する。
  - 200 m到達時に参加集合を再確認し、現在状態から代替軌道を再生成してから通常の
    合意handshakeと譲歩・車線変更を開始する。
- 保持しないもの: 早期判断時の代替軌道、速度指令、車線変更指令、承諾リース。
- 予約解除条件: 希望経路消失、別requesterとの衝突、新しい参加車両を含む参加集合変化、
  200 m時点での代替軌道生成不能。
- 固定するもの: 判断式、参加車両の算出法、軌道生成、安全判定、固定入力、交通量、seed、
  シミュレーション時間、Python/SUMO環境。
- 併用しないもの: 承諾リース、priority hold、参加集合保持、反復拒否待ち加点。
- 採否基準:
  - 全10 runが正常完了し、TraCI物理衝突が0であること。
  - 各方式の5-seed平均急減速時間が、自身の固定200 m基準より増えないこと。
  - 提案方式で車両73、33、35の10秒以上の`main_0`車線端停止が再発しないこと。
  - 両方式で、別車両の10秒以上の`main_0`車線端停止件数を固定200 m基準より増やさないこと。
  - 平均速度、停止時間、流出台数を全seedで報告すること。
- 結果を見た後に変更しないもの: 10.0秒、200 m、seed `6, 8, 9, 10, 12`、
  提案`lambda=2`、300/1000台/時、300秒、上記採否基準。

同じ5 seedで改善案を繰り返し評価しているため、独立holdoutではなく原因切り分け用の
development実験とする。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep、提案方式`lambda=2` |
| ケース | Eval.7 |
| seed | `6, 8, 9, 10, 12` |
| シミュレーション時間 | 300秒 |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-300-accepting-1000/` |
| 交通量・Bus比率 | 合流側300、本線側1000台/時、Bus 25%固定 |
| 主要パラメータ | `merge_negotiation_lead_seconds=10.0`、`two_stage_merge_negotiation=true`、実行開始200 m、提案のみ`lambda=2.0` |
| 診断ログ | 有効、checkpoint 60秒間隔 |
| Python | 3.15.1 |
| SUMO | 1.28.0 |
| OS・実行機 | Ubuntu、`sgnlab` |
| 並列数 | 各方式5、同時実行で最大10 SUMO |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | `codex/two-stage-merge-negotiation` |
| 実行ソースcommit | 実行前に確定 |
| 実行開始時dirty | 実行前に確認 |
| 結果commit | 未完了 |
| 記録commit | 未完了 |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --workers 5 --seeds 6 8 9 10 12 --duration 300 --eval7-flows 300 1000 --bus-allocation fixed --merge-negotiation-lead-seconds 10 --two-stage-merge-negotiation --diagnostic-traces --checkpoint-interval 60`。提案batchだけ`--deceleration-active --deceleration-time-half-life 0 --deceleration-loss-lambda 2`を追加する。 |

## 完了・完全性確認

- [ ] バッチmanifestが正常完了
- [ ] 予定した全case/seedが存在
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] runner/stdout/stderr/SUMOログを確認
- [ ] 必須artifactとhashを確認
- [ ] 固定入力prefix SHAが基準・方式間で一致
- [ ] 2段階交渉以外の追加機能が無効
- [ ] 物理衝突と既知警告を確認
- [ ] 結果ディレクトリだけの専用commitをpush

## 結果

未実行。

## 結論

未判定。

## 限界・異常

- 5 seed、単一交通量、300秒のdevelopment実験であり、一般的な方式優位性や安全性を
  確立する確認実験ではない。
- 比較seedは既存の改善検討で使用済みであり、独立な未使用seedではない。

## 次の作業

1. 単体テストと短時間スモークで、200 m以前に`yield`・車線変更・古い代替軌道保持が
   発生しないことを診断ログで確認する。
2. cleanなUbuntu環境から2方式を同時実行する。
3. 完了監査後、固定200 m基準と10秒前即時実行の両方へ比較する。
