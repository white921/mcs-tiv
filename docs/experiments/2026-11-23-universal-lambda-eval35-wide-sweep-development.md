# 全シナリオ共通lambda選定のためのEval.3/5広域スイープ

- 台帳ID: \`2026-11-23-universal-lambda-eval35-wide-sweep-development\`
- 状態: \`running\`
- 分類: \`development screening\`
- 実行対象: Ubuntu \`sgnlab\`

## 目的

MCSのシナリオ非依存性を保ち、T字路、十字路、合流で別々のlambdaを使わず、
正規化凸結合式\`M=(1-lambda)Z_time+lambda Z_follow\`の単一の共通lambdaを選定する。

合流Eval.7 1000/1000 veh/hでは、既存の600秒・10 seed広域スイープ
\`lambda=0.0, 0.1, ..., 1.0\`を再利用する。本実験では同じ候補点をT字路と十字路に追加し、
交差形状ごとではなく、全条件をまとめた事前固定の選定規則で候補を絞る。

## 条件

| 項目 | 値 |
| --- | --- |
| 追加ケース | Eval.3 T字路 500/500/500、Eval.5 十字路 300/300/300/300 veh/h |
| lambda | \`0.0, 0.1, ..., 1.0\`の11候補 |
| seed | \`13–22\`の10 seed |
| 時間 | 600 s |
| Bus比率 | 25% fixed-nearest |
| 入力 | \`fixed_inputs/thesis/eval35-paper-comparison/<condition>/seed-<seed>.jsonl\` |
| 提案条件 | \`T_pred=10 s\`、\`N_max=40\`、正規化凸結合式 |
| 環境 | Python 3.15.1、SUMO 1.28.0 |
| 新規run | 2条件 × 11 lambda × 10 seed = 220 |
| 分類 | lambda選定用development、diagnostic trace/checkpointなし |
| 並列 | machine-wide 15 SUMO |

実行キューは\`condition -> lambda -> seed\`とする。各lambdaの10 seedを1 cohortとし、
先頭cohortの10本を次cohortより先に投入する。各cohortの10本が成功した時点で、
独立に監査・集計・保存対象の縮約を開始する。

## 既存データの扱い

- Eval.7 1000/1000の広域lambdaスイープは既存結果を再利用し、再実行しない。
- Eval.3/5の\`lambda=0.525\`、seed 13–22の完了済み結果は、細密候補の比較で再利用できる。
- 完了済み\`lambda=0.525\`正式比較は、事前固定した\`0.525\`の性能評価としては保持する。
  一方、同じ値を今後の共通lambda選定に使った場合、そのseedは共通lambda選定に対しては
  development済みとし、最終holdoutには使わない。

## 共通lambdaの選定規則

1. 完全性監査、固定入力、実行ソース、物理衝突を先に確認する。
2. 各条件で、同一seedの山下TIVtepに対する全車平均速度の対応差と相対差を計算する。
3. T字路・十字路・合流の3形状を等重みにする
   topology-balanced macro averageを算出する。
4. 併せて、3条件中の最悪の相対差を算出し、一部条件の大きな悪化を平均で隠さない。
5. 広域グリッドでmacro averageと最悪条件のPareto前線を出し、その共通高性能域だけを
   別のdevelopment記録で細密化する。

広域結果を見る前に、特定形状専用のlambda、seed差し替え、再実行規則は導入しない。
全条件で山下方式を上回るlambdaがない場合は、その事実を結果として保持する。

## 実行・保存

- 計画・スケジューラブランチ: \`codex/universal-lambda-eval35-development\`
- 実行source commit: \`e0b7fac76f358335771bec8ab6d7cc48009208f7\`
- 結果branch:
  - \`codex/universal-lambda-eval3-r500-results\`
  - \`codex/universal-lambda-eval5-r300-results\`
- scheduler: \`scripts/run_eval35_universal_lambda_sweep.py\`
- cohort finalizer: \`scripts/finalize_eval35_lambda_screening.py\`

本バッチはdevelopment screeningなので、大きなprediction event streamとper-run source snapshotは
完全性・数値集計・SHA-256を確認した後に保存対象から外す。manifest、固定入力hash、
evaluation metrics、物理衝突、集約済み判断件数、ログ、retention auditは保存する。

## 2026-11-23 初回起動の失敗

- systemd unit: \`mcs-universal-lambda-eval35-wide-sweep-20261123.service\`
- invocation ID: \`ae0cc46579b043459df850474df98b5d\`
- 実行時間: 2026-11-23 11:22:56–11:23:05 JST
- 送出数: 15/330、成功0、失敗15、未送出315
- 失敗範囲: Eval.3 400/400/400の\`lambda=0.0\` 10 seedと\`lambda=0.1\` 5 seed
- 直接原因: \`SUMO_HOME\`にPython仮想環境のルートを渡し、
  \`<SUMO_HOME>/tools/traci\`が存在しなかったため\`ModuleNotFoundError: No module named 'traci'\`で終了した。
- 影響: 各プロセスは約3.3–3.6秒で終了し、600秒シミュレーションは完遂していない。
  結果branchのcommit・pushはない。条件や数値結果に関する結論は出せない。
- 対応: スケジューラに\`bin/sumo\`、\`tools/traci/__init__.py\`、および対象Pythonからの
  \`import traci\`を送出前に検証するpreflightと、送出せず検査だけを行う
  \`--preflight-only\`を追加する。
- 失敗証跡: 未追跡の33 cohortディレクトリは削除せず、
  \`/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-failed-launches/mcs-universal-lambda-eval35-wide-sweep-20261123/\`
  へ隔離した。結果worktreeは再びcleanである。
- 再検証: 2026-11-23 11:28 JSTに\`--preflight-only\`が成功した。source commitは
  \`0f446f0840f2f81e13644237b149a09ad3baecd2\`、Python 3.15.1、SUMO 1.28.0、既存SUMOプロセス0、
  3条件×10 seedの固定入力hashは全worktreeで一致した。
- 再実行: 失敗runを自動再実行しないルールに従い、修正後の別attemptは未起動。

## 2026-11-23 実行範囲の修正

山下修論のEval.3では400/400/400と500/500/500の両方が正式に評価されているが、
性能項の有効性に関する主な差は500/500/500で確認されている。ユーザとの合意により、
新規広域スイープはT字路500/500/500と十字路300/300/300/300の2条件、220 runに絞る。
合流1000/1000の既存110 runと各シナリオの山下TIVtep基準は再利用する。

2026-11-23 11:49 JSTに修正後のattempt 2を起動した。

- systemd unit: \`mcs-universal-lambda-eval35-wide-sweep-220run-20261123.service\`
- invocation ID: \`bba7f7d0ef434d0282385d0b3ca58b49\`
- 実行順: \`condition -> lambda -> seed\`
- 初期送出: Eval.3 500/500/500の\`lambda=0.0\` 10 seedを全て送出後、
  \`lambda=0.1\`の先5 seedを送出
- 初期確認: active 15、SUMO 15、machine slot超過なし
- 監視: Codex heartbeat \`mcs-220run\`を30分間隔で開始し、slowest active runが60%以上で
  15分間隔に短縮する。

## 最終holdout

広域・細密developmentで単一lambdaを事前固定した後、未使用seedでT字路、十字路、合流を
山下TIVtepと再比較する。最終holdoutの結果を見てlambdaを再調整しない。
