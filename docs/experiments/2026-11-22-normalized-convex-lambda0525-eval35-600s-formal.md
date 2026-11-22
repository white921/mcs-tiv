# 正規化凸結合式 lambda 0.525・Eval.3/5 600秒正式比較

- 台帳ID: `2026-11-22-normalized-convex-lambda0525-eval35-600s-formal`
- 状態: `planned`
- 位置づけ: `formal`

## 目的

Eval.7のdevelopmentで固定した正規化凸結合式`lambda=0.525`を再調整せず、
山下修士論文でTIVtepが最良だったEval.3/5の論文条件へ適用する。同一source、
同一固定入力、同一seedで山下TIVtepと直接比較し、交差点形状でも交通性能と
物理安全性を維持または改善できるかを確認する。

## 事前固定条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep / 正規化減速伝播提案`lambda=0.525` |
| Eval.3 | T字路、400/400/400および500/500/500 veh/h |
| Eval.5 | 十字路、300/300/300/300 veh/h |
| Bus比率 | 25% fixed-nearest |
| seed | 未使用の`13–22`、各条件10 seed |
| 時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval35-paper-comparison/<condition>/seed-<seed>.jsonl` |
| 提案条件 | `T_pred=10 s`、`N_max=40`、lambdaは結果後も変更しない |
| 実行環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |
| 総run | 3条件 × 2方式 × 10 seed = 60 |
| 並列 | machine-wide 15 SUMO、work-conserving共有キュー |
| 診断 | FCD、交渉、車両状態、競合、予測、物理衝突、60秒checkpoint |

Eval.3の600/600/600は論文で条件定義されているが平均速度結果表がないため、
本比較には含めない。固定入力は論文の流入量、経路分布、Bus比率に合わせて生成し、
到着時刻、経路、車種を2方式間で完全に共有する。

## 実行と後処理

キューはEval.3-400、Eval.3-500、Eval.5-300の順とし、各seed内で山下TIVtepと
提案方式を並べる。完了runが出るたび次のrunを投入し、残りが15未満になる終端を除いて
空きslotを作らない。失敗を検出した場合は新規投入を止め、実行中runを保全して自動再実行しない。

Eval.3の40 runが完了した時点で、Eval.5のシミュレーションと並行してEval.3の
完全性監査、集計、可逆圧縮、100 MB超artifactの分割検証、再生成可能なsource snapshotの
除外、結果commit/pushを低優先度で開始する。Eval.5も完了後に同じ後処理を行う。

監視は別Codexセッションで`docs/experiments/monitoring.md`に従う。各確認ではUbuntuの
実状態を読み、unit、完了/60、失敗、最遅・中央値・最速simulation time、SUMO実数、
15 slot補充、runtime停滞、traceback、disk、並行後処理状態を報告する。

## 評価

- 主指標: 全車平均速度の対応seed差`提案 − 山下TIVtep`
- 併記: 平均値から計算した改善率、提案が高いseed数、対応bootstrap 95%区間
- 副指標: Car/Bus別速度、停止時間、急減速時間、物理衝突、seed間ばらつき
- 判定: 完全性と物理衝突を先に確認し、その後に交通性能を解釈する
- 主張範囲: TIVtepに対する同条件の差。未実行の他方式を現環境で上回ったとは表現しない

## 再現用Git情報

起動commit、結果branch/commit、systemd unit、invocation ID、開始・終了日時は正式起動時と
完了時に追記する。不完全または失敗した結果はcommit/pushしない。

