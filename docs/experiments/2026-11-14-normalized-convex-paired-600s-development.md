# 正規化凸結合式・山下手法ペア10-seed・600秒開発比較

- 台帳ID: `2026-11-14-normalized-convex-paired-600s-development`
- 状態: `running`
- 位置づけ: `development`
- 開始日時: 2026-11-14 JST
- 終了日時: 実行中
- 実験ディレクトリ:
  - `results/runs/normalized-convex-600s-proposal-eval7-r1000-a1000-seeds1-2-3-6-7-8-9-10-11-12-v2-20261114/`
  - `results/runs/normalized-convex-600s-yamashita-eval7-r1000-a1000-seeds1-2-3-6-7-8-9-10-11-12-v2-20261114/`

## 目的

軌道競合領域、交渉対象、全員一致規則、軌道生成を共通化し、
Accept/Reject評価式だけを山下TIVtepと正規化減速伝播式で変更したときの
Eval.7交通性能と安全性を、同一固定入力10 seed・600秒で比較する。

## 仮説と比較対象

- 仮説: 正規化式は山下方式と異なる個別判断を生じ、600秒内の交通指標へ影響する。
- 基準実験: 同一ソースの山下TIVtep。
- 基準から変更するもの: Accept/Reject評価式のみ。
- 固定するもの: 固定入力、seed、交通量、Bus比率、軌道生成、競合検出、交渉プロトコル。
- 採否基準: 20/20 runの正常終了、ソース不変、物理衝突0、必須監査ファイルの生成。
- 結果を見た後に変更しないもの: seed、duration、交通量、Bus比率、`T_pred`、`N_max`、`lambda`、判定式。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep / 正規化渟速伝播提案 |
| ケース | Eval.7 |
| seed | `1, 2, 3, 6, 7, 8, 9, 10, 11, 12` |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7/seed-{seed}.jsonl` |
| 交通量・Bus比率 | 要求側1000 / 受入側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40`, `lambda=80/81` |
| 診断ログ | FCD、交渉、車両状態、軌道競合、予測、物理衝突、60秒checkpoint |
| Python | 3.15.1 |
| SUMO | 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | 機械全体最大15、提案10 + 山下5 |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | `codex/conflict-region-arrival` |
| 実行ソースcommit | `78ce283ab` |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | 未定 |
| 記録commit | 未定 |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 1 2 3 6 7 8 9 10 11 12 --duration 600 --eval7-flows 1000 1000 --bus-allocation fixed --diagnostic-traces --checkpoint-interval 60`（提案は`--deceleration-active --deceleration-convex-lambda 0.9876543209876543`を追加） |

## 完了・完全性確認

- [ ] 両バッチmanifestが正常完了
- [ ] 予定した20 runが存在
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] runner/stdout/stderr/SUMOログを確認
- [ ] 必須artifactとhashを確認
- [ ] 物理衝突と既知警告を確認
- [ ] 結果ディレクトリだけの専用commitをpush

## 結果

実行中。

## 結論

- 確認できたこと: 実行中。
- 確認できなかったこと: 実行中。
- 採否・次の判断: 実行中。
- 既存の研究判断から変わったこと: 実行中。

## 限界・異常

同じseed群は過去の開発・評価で使用済みであり、本実験は独立holdoutではない。
式の採用後に実施する同条件開発比較として扱い、一般的優越性は主張しない。

### 初回実行の失敗と修正

`04f4542be`の初回実行は、提案3 seed、山下2 seedが終了コード1で停止した。
軌道の安全領域同士が重なっても車両中心が受信車両側の衝突点に入るとは
限らないのに、競合領域を受信車両側の点だけから作っていたことが原因だった。
検出時刻の両車位置の中点を中心とし、両車位置を含むよう半径を拡張する
修正を`78ce283ab`に入れた。初回ディレクトリは失敗証拠としてUbuntu上に保持し、
比較結果へは使用せずpushしない。
