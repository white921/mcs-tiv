# 正規化凸結合式・山下手法・旧実験同一seed 600秒比較

- 台帳ID: `2026-11-15-normalized-convex-seeds33-42-600s-development`
- 状態: `completed`
- 位置づけ: `development`
- 開始日時: 2026-11-15 14:57:49 JST
- 終了日時: 2026-11-15 23:44:49 JST
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
| 結果commit | 提案: `c2baa5156596f0a008b4aca573c31acc6cbc3e41`（`codex/normalized-convex-seeds33-42-proposal-results-20261115`） / 山下: `8297d943a83ba88494447e0abd34b7df6ae599af`（`codex/normalized-convex-seeds33-42-yamashita-results-20261115`） |
| 記録commit | 本記録を完了更新したcommit |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 600 --eval7-flows 1000 1000 --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl --bus-allocation fixed --diagnostic-traces --checkpoint-interval 60`（提案は`--deceleration-active --deceleration-convex-lambda 0.9876543209876543`を追加） |

## 完了・完全性確認

- [x] 両バッチmanifestが正常完了
- [x] 予定した20 runが存在
- [x] 全Runが`exit_code: 0`
- [x] 全Runが`source_unchanged: true`
- [x] runner/stdout/stderr/SUMOログを確認
- [x] 必須artifactとhashを確認
- [x] 物理衝突と既知警告を確認
- [x] 結果ディレクトリだけの専用commitをpush

## 結果

全車平均速度をseed別に示す。単位はm/sである。旧2方式は2026-11-09実験の
参照値であり、現行2方式とは実行ソースが異なる。

| seed | 新・正規化提案 | 新・山下 | 旧integrated lambda=2 | 旧・山下 | 新提案−新山下 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 33 | 4.2158 | 4.1868 | 4.6346 | 4.3333 | +0.0291 |
| 34 | 4.3303 | 4.2149 | 4.4860 | 4.7230 | +0.1154 |
| 35 | 3.6821 | 4.2070 | 4.3804 | 0.4416 | -0.5250 |
| 36 | 4.1529 | 4.0546 | 4.3173 | 4.1264 | +0.0984 |
| 37 | 4.4213 | 4.2902 | 4.1350 | 3.4243 | +0.1311 |
| 38 | 4.2068 | 4.0421 | 4.4991 | 4.7581 | +0.1647 |
| 39 | 4.3512 | 4.1248 | 3.9650 | 4.7560 | +0.2264 |
| 40 | 3.9343 | 4.1147 | 4.2634 | 3.9389 | -0.1804 |
| 41 | 4.2926 | 4.3592 | 4.5588 | 4.7322 | -0.0666 |
| 42 | 4.2910 | 4.1682 | 4.5144 | 4.8108 | +0.1227 |
| **平均** | **4.1878** | **4.1762** | **4.3754** | **4.0045** | **+0.0116** |

- 新提案は新山下より7/10 seedで高かったが、平均差は`+0.0115919 m/s`
  （`+0.28%`）に留まった。
- seed対応bootstrap 200,000回（固定乱数seed `20261115`）による平均差の95%区間は
  `[-0.1342, +0.1241] m/s`で、0をまたいだ。
- 新提案は旧integrated lambda=2より平均`-0.1876 m/s`（`-4.29%`）だった。
  ただし両者は実行ソースが異なるため、この差を正規化だけに帰属できない。
- 20/20 runで物理衝突は0件だった。全runに10個のcheckpointがあり、必須artifact、
  runner/stdout/stderr、Python 3.15.1、SUMO 1.28.0を確認した。
- 固定入力の全体SHA-256と600秒prefix SHA-256は、新提案・新山下・2026-11-09旧実験で
  seedごとに一致した。
- `post-run-audit.json`は両方式とも`ok: true`である。

保存前に30 JSONLと100 checkpoint pickleを方式ごとに可逆圧縮し、全130項目について
展開後SHA-256・サイズ（JSONLは行数も）を照合した。提案は約22 GBから2.3 GB、山下は
約6.9 GBから673 MBへ縮小した。100 MB未満に収めるため提案の9ファイルを80,000,000 byte
単位に分割し、連結後SHA-256も照合した。監査結果は`compression-audit.json`と
`storage-split-audit.json`に保存した。

## 結論

- 確認できたこと: 同一ソース・同一seed・同一固定入力では、正規化凸結合式と山下方式の
  全車平均速度はほぼ同じであり、点推定上の差は`+0.0116 m/s`だった。
- 確認できなかったこと: 区間が0をまたぐため、正規化提案が山下方式より全車平均速度を
  改善するとは確認できなかった。物理衝突0も本条件内の観測であり一般安全性の証明ではない。
- 採否・次の判断: 正規化式の実装・再現性は採用できるが、交通性能の優位性を示す結果としては
  採用しない。次に式を変更する場合は本seed集合を再び独立holdoutとして扱わない。
- 既存の研究判断から変わったこと: 旧integrated lambda=2より単純に良いとはいえず、
  正規化によって係数の解釈可能性を得ることと、交通性能を改善することを分けて記述する。

## 限界・異常

seed 33–42は2026-11-09のconfirmatory実験で使用済みであり、本実験は独立holdoutではない。
旧結果との比較ではseedと固定入力は一致するが、実行ソースが異なるため、ソース差と評価式差を
完全には分離できない。現行2方式間は同一ソース・同一条件の直接比較である。
