# 正規化凸結合式・山下手法・旧実験同一seed 600秒比較

- 台帳ID: `2026-11-15-normalized-convex-seeds33-42-600s-development`
- 状態: `running`
- 位置づけ: `development`
- 開始日時: 2026-11-15 JST
- 終了日時: 実行中
- 実験ディレクトリ:
  - `results/runs/normalized-convex-600s-proposal-eval7-r1000-a1000-seeds33-42-20261115/`
  - `results/runs/normalized-convex-600s-yamashita-eval7-r1000-a1000-seeds33-42-20261115/`

## 目的

2026-11-09のEval.7・1000/1000・600秒実験と同じseed 33–42および固定入力を使い、
現行ソースの山下TIVtepと正規化凸結合式を比較する。誤って異なるseedで実行した
2026-11-14開発比較はこの比較の正本に使用しない。

## 仮説と比較対象

- 仮説: 正規化式は同じseedの山下方式と異なる交通性能を生じる。
- 基準実験: 現行ソースの山下TIVtep、および2026-11-09の旧integrated lambda=2結果。
- 基準から変更するもの: Accept/Reject評価式のみ。
- 固定するもの: seed、固定入力、交通量、Bus比率、軌道生成、競合検出、交渉プロトコル。
- 採否基準: 20/20 runの正常終了、ソース不変、物理衝突0、必須監査ファイルの生成。
- 結果を見た後に変更しないもの: seed、duration、交通量、Bus比率、`T_pred`、`N_max`、`lambda`、判定式。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep / 正規化減速伝播提案 |
| ケース | Eval.7 |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl` |
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
| 実行ソースcommit | `1125fb122d6fcfb56e3219f5b1c98d820a798a52` |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | 未定 |
| 記録commit | 未定 |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 600 --eval7-flows 1000 1000 --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl --bus-allocation fixed --diagnostic-traces --checkpoint-interval 60`（提案は`--deceleration-active --deceleration-convex-lambda 0.9876543209876543`を追加） |

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

seed 33–42は2026-11-09のconfirmatory実験で使用済みであり、本実験は独立holdoutではない。
旧結果との比較ではseedと固定入力は一致するが、実行ソースが異なるため、ソース差と評価式差を
完全には分離できない。現行2方式間は同一ソース・同一条件の直接比較である。
