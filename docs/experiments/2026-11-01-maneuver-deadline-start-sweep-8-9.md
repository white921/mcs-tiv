# 合流交渉開始8秒・9秒の探索比較

- 台帳ID: `2026-11-01-maneuver-deadline-start-sweep-8-9`
- 状態: `running`
- 位置づけ: `exploratory`
- 開始日時: `2026-11-01T21:23:53+09:00`
- 終了日時: 未完了
- 実験ディレクトリ:
  - `results/runs/maneuver-deadline8-sweep5-eval7-r300-a1000-yamashita-seeds6-8-9-10-12-300s-20261101T`
  - `results/runs/maneuver-deadline8-sweep5-eval7-r300-a1000-proposal-lambda2-seeds6-8-9-10-12-300s-20261101T`
  - `results/runs/maneuver-deadline9-sweep5-eval7-r300-a1000-yamashita-seeds6-8-9-10-12-300s-20261101T`
  - `results/runs/maneuver-deadline9-sweep5-eval7-r300-a1000-proposal-lambda2-seeds6-8-9-10-12-300s-20261101T`

## 目的

10秒前開始では提案方式の停止・速度・流出は改善した一方、急減速が全5 seedで増え、
別車両の車線端停止も発生した。開始時期を8秒・9秒へ短くしたとき、停止改善を残しながら
急減速を抑えられるかを探索する。

## 仮説と比較対象

- 比較対象: 固定200 m開始（既存基準）、8秒、9秒、10秒の全条件。
- 新規実行: 8秒・9秒について山下方式と提案方式`lambda=2`を各5 seed、計20 run。
- 基準から変更するもの: 希望経路を作り始める位置だけ。
- 固定するもの: 判断式、参加車両、承諾寿命、軌道生成、安全判定、固定入力、交通量、
  seed、シミュレーション時間、Python/SUMO環境。
- 併用しないもの: 承諾リース、参加集合保持、反復拒否待ち加点、2段階交渉。
- 採否基準:
  - 全20 runが正常完了し、TraCI物理衝突が0であること。
  - 候補時間は各方式の5-seed平均急減速が自身の固定200 m基準より増えないこと。
  - 提案方式の停止・最大列・流出台数を合わせて評価し、平均速度だけで選ばないこと。
  - 10秒以上の合流車線端停止をseed・車両別に報告すること。
  - 0/8/9/10秒を全て報告し、良い時間だけを結論に使わないこと。
- 結果を見た後に変更しないもの: 8.0秒、9.0秒、seed `6, 8, 9, 10, 12`、
  提案`lambda=2`、300/1000台/時、300秒、上記採否基準。

8秒・9秒は10秒結果を見た後に選んだ探索条件である。良い条件が見つかっても本実験だけで
採用せず、未使用seedによる独立確認を必要とする。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep、提案方式`lambda=2` |
| ケース | Eval.7 |
| seed | `6, 8, 9, 10, 12` |
| シミュレーション時間 | 300秒 |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-300-accepting-1000/` |
| 交通量・Bus比率 | 合流側300、本線側1000台/時、Bus 25%固定 |
| 開始時間 | 8.0秒、9.0秒 |
| 診断ログ | 有効、checkpoint 60秒間隔 |
| Python / SUMO | 3.15.1 / 1.28.0 |
| OS・実行機 | Ubuntu、`sgnlab` |
| 並列数 | 同一時間について各方式5、最大10 SUMO。8秒終了後に9秒を開始 |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | `codex/maneuver-deadline-start-sweep-8-9` |
| 実行ソースcommit | `10593e21c4de6db10c7722dfdf5446639cb47313` |
| 実行開始時dirty | cleanを必須とする |
| 結果commit | 未完了 |
| 記録commit | 未完了 |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --workers 5 --seeds 6 8 9 10 12 --duration 300 --eval7-flows 300 1000 --bus-allocation fixed --merge-negotiation-lead-seconds {8,9} --diagnostic-traces --checkpoint-interval 60`（提案方式は加えて`--deceleration-active --deceleration-time-half-life 0 --deceleration-loss-lambda 2`） |

Ubuntu上で山下方式・提案方式ごとにsystemd user serviceを1本ずつ起動した。
各serviceは8秒batchが正常終了した場合にだけ9秒batchへ進む。これにより同時SUMO数を
最大10に固定し、8秒で失敗した方式を勝手に再実行・続行しない。

## 完了・完全性確認

- [ ] 4 batch manifestが正常完了
- [ ] 全20 runが`exit_code: 0`、`source_unchanged: true`
- [ ] runner/stdout/stderr/SUMOログ、必須artifact、checkpointを確認
- [ ] 固定入力prefix SHAが方式・時間・既存基準で一致
- [ ] 開始時間以外の機能が無効
- [ ] 物理衝突と重大警告を確認
- [ ] 正常結果だけの専用commitをpush

## 結果

実行中。開始時に両worktreeのsource commit一致、Git clean、固定入力20ファイルの
SHA-256、Python 3.15.1、SUMO 1.28.0、135 tests成功、未使用の4出力先を確認した。
起動直後は8秒の両batchが`running`、各`workers=5`、実SUMOは計10プロセスである。

## 結論

未実行。

## 限界

- 10秒結果を確認した後の時間幅探索であり、確認実験ではない。
- 同じ5 seedを再利用するため、良い条件が見つかっても一般化できない。

