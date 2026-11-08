# Eval.7・500/1000の3方式600秒holdout

- 台帳ID: `2026-11-09-eval7-500-three-method-600s-holdout`
- 状態: `planned`
- 位置づけ: `confirmatory`
- 開始日: 2026-11-09
- 実験ディレクトリ:
  - `results/runs/eval7-500-1000-integrated-lambda2-seeds43-47-600s-20261109T/`
  - `results/runs/eval7-500-1000-utf-seeds43-47-600s-20261109T/`
  - `results/runs/eval7-500-1000-yamashita-seeds43-47-600s-20261109T/`

## 目的

300秒の開発seed探索で山下TIVtepを5/5 seedで上回った500/1000台/時について、
積算lambda=2の改善が600秒・未使用seedで再現し、UTFと比べても競争的か確認する。

## 仮説と比較対象

- 仮説: 積算lambda=2は、山下TIVtepとUTFの両方に対して全車平均速度を低下させない。
- 比較対象: 山下TIVtep / integrated lambda=2 / UTF alpha=5。
- 主要指標: 全車平均速度。
- 副指標: 合流側／本線側速度、停止時間、急減速時間、流出台数、承諾率、物理衝突。
- 採否基準: 積算−山下および積算−UTFのseed対応平均速度差が正で、流出と安全指標に重大な悪化がないこと。
- 95%区間は併記するが、5 seedのため不確実性が大きいことを限界とする。
- 結果後にseed、duration、方式、lambdaを変更せず、失敗seedを差し替えない。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep / integrated lambda=2 / UTF alpha=5 |
| ケース | Eval.7車線減少型合流 |
| seed | `43, 44, 45, 46, 47` |
| シミュレーション時間 | 600秒 |
| 入力 | 新規固定入力。全3方式でseedごとに同一hash |
| 交通量・Bus比率 | 合流側500 / 本線側1000台/時、Bus 25% |
| 提案方式 | 10秒一様積算、lambda=2、Reject待ち加点なし |
| 診断 | FCD・交渉・車両状態・衝突・60秒checkpoint |
| 環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |
| 並列数 | 提案とUTFを各5 workerで先行、完了後に山下5 worker。最大10 SUMO |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | `codex/eval7-500-three-method-600s` |
| 実行ソースcommit | 実行前に記録 |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | 方式ごとに正常結果だけを専用branchへ保存 |

## 完了・完全性確認

- [ ] 3バッチのmanifestが正常完了
- [ ] 予定した15 runが存在
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] 方式・seedごとの固定入力hashが一致
- [ ] runner/stdout/stderr/SUMOログ、必須artifact、物理衝突を監査
- [ ] 結果ディレクトリだけの専用commitをpush

## 限界

- 500/1000は開発用交通量探索で良好だった条件を選んでいる。
- 朝9時までの中間結果を優先して5 seedとした。10 seedの700/1000 holdoutより区間推定は不安定である。
- 一般的優越性ではなく、500/1000条件の独立検証として解釈する。
