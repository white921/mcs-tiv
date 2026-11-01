# 合流交渉10秒前開始の5-seed検証

- 台帳ID: `2026-11-01-maneuver-deadline-5seed-validation`
- 状態: `planned`
- 位置づけ: `development`
- 開始日時: 未開始
- 終了日時: 未完了
- 実験ディレクトリ:
  - `results/runs/maneuver-deadline10-validation5-eval7-r300-a1000-yamashita-seeds6-8-9-10-12-300s-20261101T`
  - `results/runs/maneuver-deadline10-validation5-eval7-r300-a1000-proposal-lambda2-seeds6-8-9-10-12-300s-20261101T`

## 目的

山下方式と提案方式`lambda=2`に共通する合流交渉の開始時期を、車線端まで自由走行で
10秒残る位置へ移した状態で5 seed比較する。2-seed診断で見られた提案方式の車線端停止
解消が他seedでも再現するか、および両方式で急減速が悪化しないかを確認する。

## 仮説と比較対象

- 仮説: 固定200 m開始より早く交渉を開始すると、拒否・再交渉後に残る時間が増え、
  特に提案方式の車線端停止、総停止時間、取消が減る。
- 基準実験: `2026-11-01-eval7-flow-ratio-sweep`の300/1000台/時、同一5 seed。
- 基準から変更するもの: 希望経路を作り始める位置だけを、車線端まで各車種の許容速度で
  10.0秒の位置へ移す。
- 固定するもの: 判断式、参加車両、承諾寿命、軌道生成、安全判定、固定入力、交通量、
  seed、シミュレーション時間、Python/SUMO環境。
- 採否基準:
  - 全10 runが正常完了し、TraCI物理衝突が0であること。
  - 山下方式・提案方式の各々で、5-seed平均の急減速時間が自身の基準より増えないこと。
  - 車線端停止、総停止時間、最大停止列、流出台数を合わせて評価し、平均速度だけで
    採用しないこと。
  - 方式間の優位性はseed別の方向を報告し、良いseedだけを選ばないこと。
- 結果を見た後に変更しないもの: 10.0秒、seed `6, 8, 9, 10, 12`、
  提案`lambda=2`、300/1000台/時、300秒、上記採否基準。

seed 6/8は2-seed診断で使用済み、seed 9/10/12はこの機能では未使用である。そのため
完全な独立holdoutではなく、診断を5 seedへ拡張するdevelopment検証と位置づける。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep、提案方式`lambda=2` |
| ケース | Eval.7 |
| seed | `6, 8, 9, 10, 12` |
| シミュレーション時間 | 300秒 |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-300-accepting-1000/`の固定入力 |
| 交通量・Bus比率 | 合流側300、本線側1000台/時、Bus 25%固定 |
| 主要パラメータ | `merge_negotiation_lead_seconds=10.0`、提案のみ`lambda=2.0` |
| 併用しない機能 | 承諾リース、参加集合保持、反復拒否待ち加点 |
| 診断ログ | 有効、checkpoint 60秒間隔 |
| Python | 3.15.1 |
| SUMO | 1.28.0 |
| OS・実行機 | Ubuntu、`sgnlab` |
| 並列数 | 各方式5、同時実行で最大10 SUMO |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | `codex/maneuver-deadline-5seed-validation` |
| 実行ソースcommit | 実行開始時manifestで確定 |
| 実行開始時dirty | cleanを必須とする |
| 結果commit | 未完了 |
| 記録commit | 未完了 |
| 実行コマンド | 実行開始後に記録 |

## 完了・完全性確認

- [ ] バッチmanifestが正常完了
- [ ] 予定した全case/seedが存在
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] runner/stdout/stderr/SUMOログを確認
- [ ] 必須artifactとhashを確認
- [ ] 固定入力prefix SHAが基準・方式間で一致
- [ ] 10秒前倒し以外の機能が無効
- [ ] 物理衝突と既知警告を確認
- [ ] 結果ディレクトリだけの専用commitをpush

## 結果

未実行。

## 結論

未実行。

## 限界・異常

- 10秒は2-seed診断後に選ばれた条件であり、時間幅の探索ではない。
- seed 6/8は既に結果を見ており、5 seedすべてが未使用ではない。

