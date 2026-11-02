# 後続車影響項の寄与を確認する独立holdout

- 台帳ID: `2026-11-02-follower-impact-attribution-holdout`
- 状態: `running`
- 位置づけ: `confirmatory independent holdout`
- 比較対象: 到着時間項のみ、提案方式`lambda=2`、山下方式
- 使用seed: `13, 14, 15, 16, 17, 18, 19, 20, 21, 22`
- 予定出力: `results/runs/follower-impact-attribution-holdout-*`

## 実行状況

- source commit: `f56fd4bcfd68330399a9b0e6c870b9126f4447ed`
- Ubuntu test: Python 3.15.1 / SUMO 1.28.0で120件すべて成功。
- smoke: Eval.3 seed 13、20秒で山下方式・提案方式とも`exit_code: 0`。先行smoke出力により
  提案方式smokeの開始時Gitがdirtyになったため、smoke結果は正式結果に使用しない。
- 自然走行開始: `2026-11-02T14:27:21+09:00`
- 山下方式出力:
  `results/runs/follower-impact-attribution-yamashita-300s-seeds13-22-f56fd4bc`
- 提案方式出力:
  `results/runs/follower-impact-attribution-proposal-harm-lambda2-300s-seeds13-22-f56fd4bc`

正式自然走行は方式ごとのclean detached worktreeで各30 run、各4 workerとして同時に
開始した。結果完了後に全manifestとログを検証し、正常な場合だけ場面計画へ進む。
本バッチは開始済みworker poolを変更できないため合計8並列のまま完走させる。以後の
MCS/SUMOバッチは原則10並列とし、本実験の反実仮corpusも10 workerで実行する。

自然走行は提案方式が`2026-11-02T23:33:11+09:00`、山下方式が
`2026-11-02T23:47:32+09:00`に完了した。全60 runで`exit_code: 0`、
`source_unchanged: true`、必須artifactあり、3000 step観測、物理衝突0、
Traceback等の重大ログ0を確認した。

反実仮計画は次の2群に固定した。各群120場面で、各ケース40、各origin 60、
各ケース×origin×seedから4場面である。

- seed 13〜17 plan SHA-256:
  `96d221ae82a25108e057fee4c27b959ee677a47ce4509e87e3b5a0f56e3f8189`
- seed 18〜22 plan SHA-256:
  `4242aa3437c5e07977778ca07aa128cb1d737fb3b659d76150977e8ae1a08159`

`2026-11-03T00:48+09:00`にseed 13〜17の120場面を10 workerで開始した。
正常終了した場合だけ、seed 18〜22の120場面を同じ10 workerで逐次実行する。

## 目的

既存holdoutでは提案方式全体の山下方式に対する判断後悔量低減は頑健だったが、正式な
10秒評価窓で提案方式と到着時間項のみの差の95%区間が0をまたいだ。未使用seedを用いて、
到着時間項に後続車影響項を加えること自体が10秒判断後悔量を低減するか確認する。

## 事前固定する条件

- ケース: Eval.3、Eval.5、Eval.7。
- 自然走行方式: 山下方式、提案方式`lambda=2`。
- seed: `13`〜`22`の10個。結果確認後に追加・除外しない。
- 自然走行時間: 300秒。
- 場面選択: 各ケース×自然走行方式×seedについて、強制分岐可能な異なる交渉の先頭4件。
- 反実仮分岐: 各場面でAcceptとRejectを10秒ずつ再生する。
- 評価cohort: requester、receiver、判断境界時点の両者の後続影響車。
- 判断器: 到着時間項のみ、提案方式`lambda=2`、山下方式を保存済み同一場面に採点する。
- 実行環境: sgnlab Ubuntu、Python 3.15.1、SUMO 1.28。

合計は`3ケース × 2自然走行方式 × 10 seed × 4場面 = 240場面`とする。既存runnerの
1回120場面という固定単位に合わせ、seed 13〜17と18〜22の2 corpusに分けるが、解析時は
240場面を統合する。

## 主評価

- 指標: 判断後10秒におけるcohort総移動距離の判断後悔量。
- 主比較: `提案lambda=2 − 到着時間項のみ`。
- 集約: 場面平均ではなくケース等重みのmacro平均。
- 不確実性: case内の自然走行方式×seedをclusterとして100,000回bootstrapする。
- bootstrap乱数seed: `20261102`。
- 確認基準: 主比較の点推定が0未満、かつ両側95%区間の上限が0未満。

## 副評価

- 提案方式と山下方式の10秒判断後悔量差。
- ケース別、自然走行方式別の差。
- 3秒、5秒prefixでの方向。
- 正規化遅延、損失距離、停止時間、急減速時間による方向確認。
- 場面選択順別の差。

副評価は主評価を置き換えない。lambda、seed、場面数、評価窓、確認基準は結果を見て
変更しない。

## 実行順

1. seed 13〜22の固定入力を生成・検証してsource commitに含める。
2. テストと短時間smokeを通す。
3. 山下方式と提案方式の300秒自然走行を完了する。
4. 2 corpusの場面計画を固定し、計画SHA-256を記録する。
5. Accept/Reject 240場面を実行し、manifest、ログ、traceを検証する。
6. 事前固定した主評価を1回解析し、結果を本記録へ追記する。

## 完了条件

- [x] 全自然走行runが`exit_code: 0`かつ`source_unchanged: true`。
- [ ] 240場面のAccept/Reject両分岐が正常終了している。
- [ ] 計画と結果のevent IDが一致している。
- [ ] 必須artifact、ログ、trace、物理衝突を検証している。
- [ ] 主比較と95%区間を記録している。
- [ ] 結論を後続車影響項の寄与範囲に限定している。
