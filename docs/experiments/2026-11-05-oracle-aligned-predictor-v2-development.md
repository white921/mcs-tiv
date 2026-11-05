# オラクル整合距離予測v2の保存済み960場面開発再採点

- 台帳ID: `2026-11-05-oracle-aligned-predictor-v2-development`
- 状態: `planned`
- 位置づけ: `post-hoc development rescore`
- 実装branch: `codex/oracle-aligned-predictor-v2`
- 実装commit: `8398d57ea44922a945c62593689cd0b4ddcbe964`
- 予定結果: `results/runs/oracle-aligned-v2-development-rescore-20261105/`

## 目的

時間層別holdoutで、旧の後続車損失差と実現したAccept/Reject走行距離差が
整合しなかった原因候補を分析する。次の2変更を含むv2予測を、保存済み
960場面の実現Accept/Reject分岐に対して再採点する。

1. 根車両基準のgapを後続車列全体に再利用せず、直前車との隣接gapを再計算する。
2. 到着時間差と制限速度正規化損失の合成ではなく、交溉2台と検出後続車の
   10秒間の予測総走行距離差をオラクルと同じm単位で直接比較する。

## 条件

- 対象: `2026-11-03-follower-impact-time-stratified-holdout`の固定済960場面。
- ケース: Eval.3、Eval.5、Eval.7。
- 自然走行origin: 山下方式、旧提案方式lambda=2。
- seed: 13–22。
- 時間帯: `[0,100)`, `[100,160)`, `[160,220)`, `[220,290]`秒。
- 各場面の保存済み`t-0.1`チェックポイントを再開し、判断境界まで0.1秒だけ
  再実行してv2予測を取得する。
- Accept/Rejectの10秒分岐は再実行せず、完了済みの物理走行ログを数値の正本とする。
- 主cohort: 交溉2台とv2が予測時に検出したAccept/Reject後続車の和集合。
- v2判断: 予測`Accept距離 - Reject距離 > 1 m`でAccept、`< -1 m`でReject、
  ±1 m以内は到着時間項の判断へフォールバックする。
- 比較: 到着時間項のみ、隣接gap修正後の旧lambda=2式、v2、山下方式。
- 実行並列数: 10 worker。
- 集約: case×時間帯等重みmacro平均、origin×seed cluster bootstrap 100,000回。
- bootstrap乱数seed: `20261105`。

## 予定監査

- [ ] 960場面すべてで保存fingerprintとv2再開fingerprintが一致する。
- [ ] 960場面すべてでv2予測と旧Accept/Reject実現距離を対応付ける。
- [ ] 予測距離差と実現距離差の相関、正解率、後悔量、最大誤差を記録する。
- [ ] `exit_code: 0`、`source_unchanged: true`、必須manifestと全stdout/stderrを確認する。

## 位置づけと限界

本960場面のオラクル結果はv2設計前に確認済みである。したがって、ここでの改善は
開発結果であり、提案方式v2の優位性の確認証拠には使わない。結果が改善した場合は、
判断規則を固定した後に未使用seedの新しい時間層別holdoutで別途確認する。

## 結果

未実行。
