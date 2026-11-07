# Eval.7・700/1000積算方式の独立holdout

- 台帳ID: `2026-11-07-eval7-integrated-700-independent-holdout`
- 状態: `planned`
- 位置づけ: `confirmatory`
- 開始日時: 2026-11-07
- 終了日時:
- 実験ディレクトリ:
  - `results/runs/eval7-700-1000-yamashita-seeds33-42-600s-20261107T/`
  - `results/runs/eval7-700-1000-terminal-held-lambda2-seeds33-42-600s-20261107T/`
  - `results/runs/eval7-700-1000-integrated-lambda2-seeds33-42-600s-20261107T/`

## 目的

開発用seed 6/8/9/10/12の700/1000台/時で観測した積算方式の交通性能改善が、
方式・係数・交通量を再調整しない未使用seed 33–42の600秒走行でも再現するか確認する。
山下TIVtepに対する提案全体の差と、終端値方式に対する10秒積算そのものの差を分離する。

## 仮説と比較対象

- 仮説: 一時的な減速と回復が発生する700/1000台/時では、10秒間の損失積算が
  10秒後の終端値より途中の減速波を識別し、山下方式と終端値方式の両方に対して
  全車平均速度と流出台数を改善する。
- 基準実験: 山下TIVtep、および同じAccept/Reject予測を使う`terminal-held`アブレーション。
- 基準から変更するもの: 提案2方式は`arrival_margin + 2 * max(accept_loss - reject_loss, 0)`を
  使用し、損失表現だけを`integrated` / `terminal-held`で切り替える。
- 固定するもの: 交通量、Bus比率、10秒一様予測、lambda=2、合流開始位置、固定入力、
  SUMO/Python環境、診断設定。
- 採否基準:
  1. 積算方式−山下方式、および積算方式−終端値方式のseed対応平均速度差がともに0より大きい。
  2. 両比較のseed対応bootstrap 95%区間の下限が0より大きい。
  3. 積算方式の600秒までの平均流出台数が両基準を下回らない。
  4. 物理衝突0で、停止時間と急減速時間に実質的な悪化がない。
- 結果を見た後に変更しないもの: seed、交通量、duration、lambda、予測窓、採否基準、
  評価対象。失敗seedや評価不能runを別seedへ差し替えない。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 山下TIVtep / terminal-held lambda=2 / integrated lambda=2 |
| ケース | Eval.7車線減少型合流 |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600秒 |
| 入力 | 新規固定入力。3方式でseedごとに同一hashを使用 |
| 交通量・Bus比率 | 合流側700 / 本線側1000台/時、Bus 25% |
| 主要パラメータ | 一様10秒、lambda=2、固定200 m開始、追加機能なし |
| 診断ログ | 有効、checkpoint 60秒 |
| Python | Ubuntu Python 3.15.1 |
| SUMO | 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | 最大10 SUMO。1方式10 workerを順次実行 |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | `codex/integrated-holdout-700` |
| 実行ソースcommit | 実行前に記録 |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | 方式ごとに正常終了後記録 |
| 記録commit | 完了後記録 |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --workers 10 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 600 --eval7-flows 700 1000 --bus-allocation fixed --diagnostic-traces --checkpoint-interval 60`。提案2方式は`--deceleration-active --deceleration-time-half-life 0 --deceleration-loss-lambda 2 --deceleration-loss-mode {terminal-held,integrated}`を追加する。 |

## 完了・完全性確認

- [ ] 3バッチのmanifestが正常完了
- [ ] 予定した30 Runが存在
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] 全方式・seedの固定入力hashが一致
- [ ] runner/stdout/stderr/SUMOログを確認
- [ ] 必須artifactとhashを確認
- [ ] 物理衝突と既知警告を確認
- [ ] 方式ごとの正常結果だけを専用commitへ保存

## 結果

実験完了後に、方式別・seed別の平均速度、合流側／本線側速度、停止時間、急減速、
流出台数、承諾率、物理衝突とseed対応不確実性区間を記録する。

## 結論

未実行。

## 限界・異常

- 700/1000は開発実験で良好だった結果を見て選択した適用領域である。したがって、
  本実験が成功しても全合流条件への一般的優越性は主張しない。
- seed 33–42が過去の方式選択・係数選択に使われていないことを実行前に確認する。
- UTFは現行の同条件runnerに切替がないため本実験には含めず、積算効果が再現した場合の
  追加対照として分離する。

## 次の作業

1. seed 33–42の600秒固定入力を生成し、hash・台数・Bus比率・過去未使用を監査する。
2. Ubuntu正式環境でテストと単一seed smokeを実行する。
3. 3方式を順次実行し、各バッチ正常終了後に完全性監査・専用結果commitを行う。
