# 正規化凸結合式 lambda 0.525・Eval.3/5 600秒正式比較

- 台帳ID: `2026-11-22-normalized-convex-lambda0525-eval35-600s-formal`
- 状態: `completed`
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

- 実行source commit: `a64786756f33ccd983ca6a60fde2ff4ae68f1f36`
- 起動日時: 2026-11-22 15:09 JST
- systemd user unit: `mcs-eval35-l0525-vs-yamashita-600s-20261122.service`
- invocation ID: `4e87c83b255249a7b6e373e8d12525e4`
- 監視Codex thread: `01a201e0-b418-7da3-924c-b0d57d85255d`
- スモーク: 6条件すべてseed 13を10 simulation secondsまで実行し、exit 0、同一固定入力SHA、
  clean source、指定flowを確認した。formal成功後にスモークraw outputを削除する。

起動直後のreadbackではunit `active/running`、SUMO `15/15`、6 manifest `running`、
source clean、各flowおよび提案条件`lambda=0.525`を確認した。不完全または失敗した結果は
commit/pushしない。終了日時、結果branch/commit、完全性監査と結論は完了時に追記する。

## シミュレーション結果と後処理状態

60/60 runはすべて`exit_code: 0`、`source_unchanged: true`、実行source一致、
物理衝突0を確認した。主指標の10 seed平均は次のとおり。

| 条件 | 山下 (m/s) | 提案lambda=0.525 (m/s) | 差 (m/s) | 改善率 | 提案勝利seed | 対応差95% bootstrap (m/s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Eval.3 400/400/400 | 7.1478 | 7.2965 | +0.1487 | +2.08% | 7/10 | [-0.0654, 0.3667] |
| Eval.3 500/500/500 | 5.7409 | 5.3255 | -0.4154 | -7.24% | 3/10 | [-0.7139, -0.1252] |
| Eval.5 300/300/300/300 | 7.2834 | 7.1584 | -0.1250 | -1.72% | 3/10 | [-0.4205, 0.0805] |

- Eval.3の4 cohortは監査・圧縮・結果push済み。結果commitは
  `a1d6843fe328c132a4ed4eedd38f37c6cca32738`、
  `64d26e2f5c334f90cc139fce467d5db8e6ded210`、
  `5fbedab73eb0746bbc5636e9bd1cb92bda962faa`、
  `ee872c05a203e610202b9518971a7823498eb91b`。
- Eval.5の2 cohortも2026-11-28に完全性監査、可逆圧縮、復元hash検証、storage split
  検証を完了した。最初のfinalizerは圧縮rawまで結果branchへstageする旧仕様だったため、
  commit前に停止した。その後、manifest、metrics、method audit、比較summary、checkpoint
  metadata、圧縮・retention auditだけを選択するcompact保存へ切り替えた。
- Eval.5提案結果commitは`afe2910991d04d0865aa031f3ab38b9cf8281b5d`、山下結果commitは
  `abea2f4bf44aceea136a5dcd576c111b88caaa67`。どちらも対応する専用結果branchへpush済みで、
  今回の出力配下にFCD、runtime、交渉・競合・車両状態・予測stream、checkpoint stateは
  trackingしていない。
- 圧縮rawはUbuntuData上に保持しており、提案230,382,381 bytes、山下172,411,247 bytes。
  外部保存先は`pending`であり、検証済みコピーができるまで削除しない。
- 以上により60/60 runの数値、完全性、物理衝突0、retention、結果pushを確認し、
  本台帳を`completed`とする。lambda=0.525はEval.3 500とEval.5 300で山下法を下回り、
  交差点へ一様に改善を移せるという結論は支持されなかった。

