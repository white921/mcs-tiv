# Eval.7・1200/1000の3方式600秒stress test

- 台帳ID: `2026-11-10-eval7-1200-three-method-600s-holdout`
- 状態: `planned`
- 位置づけ: `confirmatory stress test`
- 計画日: 2026-11-10
- 予定実験ディレクトリ:
  - `results/runs/eval7-1200-1000-integrated-lambda2-seeds33-42-600s-20261110T1200/`
  - `results/runs/eval7-1200-1000-utf-seeds33-42-600s-20261110T1200/`
  - `results/runs/eval7-1200-1000-yamashita-seeds33-42-600s-20261110T1200/`

## 目的

合流側1200・本線側1000台/時の飽和側stress testとして、integrated lambda=2を
UTF alpha=5と山下TIVtepに対してseed 33–42・600秒・同一固定入力で比較する。
1000/1000で観測した本線側保護と合流側・流出台数のトレードオフがさらに強まるか、
または方式ごとの交通崩壊が起きるかを確認する。一般的な交通量閾値の推定とは扱わない。

## 事前固定条件

| 項目 | 値 |
| --- | --- |
| 方式 | integrated lambda=2 / UTF alpha=5 / 山下TIVtep |
| ケース | Eval.7車線減少型合流 |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600秒 |
| 交通量 | 合流側1200 / 本線側1000台/時 |
| Bus比率・入力 | 25%、3方式でseedごとに同一の固定入力 |
| integrated | 半減期0、一様積算、lambda=2、loss mode integrated |
| UTF / 山下 | `decision_method=utf, alpha=5` / `decision_method=tivtep` |
| 環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |
| 並列 | 3方式共有15 slot、起動待ち順 integrated → UTF → 山下 |

結果を見た後にseed、duration、交通量、Bus比率、lambda、alpha、固定入力、方式設定を
変更せず、失敗seedの差し替えや条件変更rerunを行わない。

## 実行ソースと固定入力

| 項目 | 値 |
| --- | --- |
| source branch | `codex/eval7-1200-fixed-input-source` |
| 実行予定source commit | `22e50431fd4a758e49b432bfce5860e05cd0036e` |
| 直接の基点 | 1000/1000 source `766f1f8c95f52cabf7cc86e06006e327852e28b8` |
| 固定入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1200-accepting-1000/seed-{33..42}.jsonl` |

1200/1000の固定入力はPython 3.15.1で生成した。各seedは合流側200台、本線側166台、
Bus 92台で、前半300秒は合流側100台、本線側83台、Bus 46台である。既存55入力は
生成時Python版metadataだけを既存値へ合わせた比較で車両イベントが完全一致した。
固定入力15 test、共有queue 3 test、全固定入力SHA256SUMSを事前検証した。

## 事前仮説と主要評価

- integratedの全車平均速度が点推定で最高でも、1000/1000と同様に本線側改善と
  合流側速度・流出台数低下の交換になり得る。
- 飽和条件では未挿入車両や600秒時点の残留車両が平均速度を歪め得るため、速度だけで
  判定せず、流出台数、残留車両、停止、急減速、物理衝突を同時に扱う。
- 前半300秒と後半300秒を分け、時間経過による交通崩壊を確認する。
- integrated−UTF、integrated−山下について、固定乱数seedを記録した20万回の
  対応percentile bootstrap 95%区間を算出する。

## 完了条件

- [ ] 10秒smokeを正式結果と分離し、最大15、補充、起動順、方式別manifest完了を確認
- [ ] 3方式のexperiment manifestが`completed`
- [ ] 30 runが存在し、全runが`exit_code: 0`かつ`source_unchanged: true`
- [ ] source commit、開始時clean、固定入力hash、環境、方式パラメータが一致
- [ ] 必須artifact、checkpoint、runner/stdout/stderr/SUMOログを監査
- [ ] 物理衝突、warning/error/traceback、共有15枠を監査
- [ ] 正常結果だけを方式別result branchへ保存しpush
- [ ] seed対応集計、20万回bootstrap、時間分割、300–1200比較を記録

## 結果

未実行。

## 失敗・隔離履歴と制約

正式実行前。smokeおよび正式実行の異常は発生時に追記し、不完全結果はpushしない。
