# Eval.7・300/1000の3方式600秒holdout

- 台帳ID: `2026-11-09-eval7-300-three-method-600s-holdout`
- 状態: `planned`
- 位置づけ: `confirmatory`
- 開始日: 2026-11-09
- 実験ディレクトリ:
  - `results/runs/eval7-300-1000-integrated-lambda2-seeds33-42-600s-20261109T/`
  - `results/runs/eval7-300-1000-utf-seeds33-42-600s-20261109T/`
  - `results/runs/eval7-300-1000-yamashita-seeds33-42-600s-20261109T/`

## 目的

300/1000台/時で、integrated lambda=2をUTF alpha=5と山下TIVtepに対して
未使用seed 33–42・600秒・同一固定入力で比較し、低合流側負荷での
交通性能と安全性を確認する。

## 仮説と比較対象

- 仮説: integratedの効果は交通量に依存し、300/1000では中負荷条件と同じ改善を示さない可能性がある。
- 比較対象: UTF alpha=5、山下TIVtep。
- 固定するもの: seed、duration、交通量、Bus 25%、固定入力、lambda/alpha、方式設定、Python/SUMO環境。
- 結果後に変更しないもの: 上記全固定条件と評価指標。失敗seedは差し替えない。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | integrated lambda=2 / UTF alpha=5 / 山下TIVtep |
| ケース | Eval.7車線減少型合流 |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600秒 |
| 入力 | 3方式でseedごとに同一の固定入力 |
| 交通量・Bus比率 | 合流側300 / 本線側1000台/時、Bus 25% |
| 診断 | FCD・交渉・車両状態・衝突・60秒checkpoint |
| 環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |
| 並列数 | 3方式共有15 slot、起動順 integrated → UTF → 山下 |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| source branch | `codex/eval7-300-1000-three-method-source` |
| 実行ソースcommit | 正式実行前に単一commitへ固定 |
| 実行開始時dirty | `false`を必須とする |
| 結果branch | `codex/eval7-300-{integrated,utf,yamashita}-results` |

## 完了・完全性確認

- [ ] 3方式のexperiment manifestが`completed`
- [ ] 30 runが存在し、全runが`exit_code: 0`かつ`source_unchanged: true`
- [ ] 実行ソースcommit、固定入力hash、環境、方式パラメータが一致
- [ ] 必須artifact、checkpoint、各種ログ、物理衝突、warning/error/tracebackを監査
- [ ] 正常結果のみを方式別commitへ保存しpush

## 結果

未実行。

## 結論

未実行。一般的優越性ではなく、300/1000条件の10-seed検証として解釈する。

## 限界・異常

失敗や隔離履歴は完了時に追記する。300/1000に未解決の失敗がある場合は
1000/1000を開始しない。
