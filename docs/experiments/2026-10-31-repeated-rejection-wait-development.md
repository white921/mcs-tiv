# 反復拒否の実測待ち時間を加えた300秒交通性能試験

## 状態

`running`

- source: `1029f7fc28cd02891fd2039b3a1ad1961da4c924`
- Ubuntu worktree: `/home/yamada/UbuntuData/ドキュメント/卒論研究/mcs-tiv-rejection-wait-development-formal`
- systemd unit: `mcs-repeated-rejection-wait-development-15-20261031.service`
- output: `results/runs/repeated-rejection-wait-development-300s-15runs-20261031T`

UbuntuのPython 3.15.1 / SUMO 1.28.0環境で124 testsが成功した。
Eval.3 seed 6を80秒まで動かしたsmokeも正常終了し、`exit_code=0`、
`source_unchanged=true`、物理衝突0、重大ログ異常0を確認した。27判断のうち
反復拒否待ちは7回の拒否判断に適用され、監査記録上の最大値は2.0秒だった。
その後、同じsourceからclean worktreeを新設し、正式15 runを開始した。

## 目的

未使用seedによる最終確認では、改善提案lambda=2が交渉直後10秒の後悔量を
山下方式より小さくした一方、300秒の全車平均速度はEval.3/5/7の全ケースで
低下した。提案方式の承諾率も山下方式より低く、局所的には妥当な拒否でも、同じ
車両間で拒否を繰り返して待ち時間を蓄積することが交通全体を悪化させている可能性が
ある。本試験は、この仮説に対する最小変更を300秒自然走行で確認する。

本試験は改善用データであり、ここで良い結果が出ても最終的な優位性の根拠にはしない。

## 固定する変更

従来の改善式は次のとおりである。

`M = arrival_margin + 2 * max(accept_loss - reject_loss, 0)`

本試験では、同じ送信車・受信車間で拒否が継続している実測待ち時間を加える。

`M = arrival_margin + 2 * max(accept_loss - reject_loss, 0) - rejection_wait`

- `M <= 0`で承諾する。
- `rejection_wait`は最初の拒否では0秒で、同じ車両間の拒否が続く間だけ増える。
- 2秒を超えて交渉が途切れた場合は別の拒否列として0秒へ戻す。
- 上限は10秒とする。これは後続車影響予測と同じ時間幅であり、新しい倍率は導入しない。
- 承諾した時点でその車両間の待ち時間を0秒へ戻す。
- 到着不能判定と、物理的に拒否必須の判定は従来どおり優先する。
- 予測された負の後続車損失は、精度不足が確認済みのため承諾便益として使わない。

これは拒否が生む影響全体の完全な予測ではなく、「反復拒否による当事者の実測待ち」
だけを扱う第一段階である。後続待ち行列の長さやネットワーク全体の波及は含まない。

## 実行条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.3 / Eval.5 / Eval.7 |
| seed | 全ケース共通 `6, 8, 9, 10, 12` |
| run数 | 3ケース × 5 seed = 15 |
| duration | 300秒 |
| 固定入力 | 既存の最終確認用入力を再利用 |
| 後続車害係数 | `lambda=2.0` |
| 時間重み | uniform 10秒 |
| 反復拒否待ち上限 | 10秒 |
| 反復拒否の切断間隔 | 2秒 |
| Python / SUMO | 3.15.1 / 1.28.0 |

比較対象は同じ固定入力・seedで完了済みの山下方式と、反復拒否待ちを加える前の
改善提案lambda=2である。

- 山下方式: `results/runs/decision-oracle-holdout-yamashita-300s-20261031T`
- 従来改善提案: `results/runs/decision-oracle-holdout-proposal-harm-lambda2-300s-20261031T`
- 比較記録: `docs/experiments/2026-10-31-decision-oracle-harm-only-holdout.md`

## 評価指標

主に300秒の全車平均速度をケース別・seed別に比較する。併せて停止時間、急減速、
物理衝突、承諾率、反復拒否待ちが判定に使われた回数を確認する。平均速度だけでなく、
一部seedだけの改善でないか、Eval間で反転しないかも報告する。

## 完了条件

- [x] 実装とテストをcommit/push
- [x] Ubuntu正式環境で全テスト
- [x] 単一seedの短時間smokeで式・監査・正常終了を確認
- [ ] 15 runを正常完了
- [ ] 全件`exit_code=0`、`source_unchanged=true`、物理衝突と重大ログを確認
- [ ] 山下方式・従来改善提案とケース別／seed別に比較
- [ ] 正常結果のみ専用commitでpush

