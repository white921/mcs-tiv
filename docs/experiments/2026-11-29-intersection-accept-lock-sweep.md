# 交差点のAccept後判断ロック中間周期スイープ

- 台帳ID: `2026-11-29-intersection-accept-lock-sweep`
- 状態: `running`
- 分類: `diagnostic development timing sweep`

## 目的

Accept/Reject別診断で、Reject後lockはRejectしたpath IDが`yetJudgedList`に入るため
実行経路上到達不能で、共通lock 0.1秒化の性能差はAccept後の更新で生じていた。
Accept 0.1秒はEval.5を改善したがEval.3を悪化させたため、両者を悪化させない
形状共通の中間周期が存在するかを調べる。

## 条件

| Accept後lock | Reject後lock | 形状・seed | run |
| ---: | ---: | --- | ---: |
| `0.3 s` | `1.0 s` | Eval.3 seed 13–17 + Eval.5 seed 13–22 | 15 |
| `0.5 s` | `1.0 s` | Eval.3 seed 13–17 + Eval.5 seed 13–22 | 15 |
| `0.7 s` | `1.0 s` | Eval.3 seed 13–17 + Eval.5 seed 13–22 | 15 |

- Eval.3 `500/500/500 veh/h`、Eval.5 `300/300/300/300 veh/h`、各300 s。
- `lambda=0.95`、Bus比25% fixed-nearest、lane metadata heading fallback有効を固定。
- 既存のAccept 0.1秒と15 run、Accept 1.0秒と15 runをendpoint対照として再利用する。
- 新規45 run。15 SUMOの3波で実行し、各波の子batchに失敗があれば次波は自動起動しない。
- 失敗runは自動再実行しない。

## 事前固定した判定

1. 45/45正常終了、完全性監査、物理衝突0を必須とする。
2. 各候補について、1.0秒対照との対応seed差を速度、停止時間、急減速、判断、
   Accept/Reject、適用、取消で比較する。
3. Eval.3とEval.5の両方で、平均速度が1.0秒より低くならず、平均停止時間が増えない
   新規候補だけを適格とする。
4. 適格候補のうち、形状別相対速度差の最悪値を最大化し、次に2形状等重み平均を
   最大化する候補を選ぶ。
5. 適格候補がなければ、固定周期調整では両形状を共通改善できないとし、
   判断再評価とAccept済み経路更新を分離するevent-driven設計へ進む。

development seedであるため、選定された場合も一般的優越性を主張せず、未使用seedの
事前固定比較が必要とする。

## 実行・保存

- scheduler: `scripts/run_intersection_accept_lock_sweep.py`
- finalizer: `scripts/finalize_intersection_accept_lock_sweep.py`
- source branch: `codex/intersection-heading-diagnostic`
- raw output: UbuntuData上の`mcs-tiv-diagnostic-artifacts/`。
- 起動gateはAccept/Reject別第1波の15/15監査、既存対照との15/15完全一致、
  Reject後同一key再登場0件、物理衝突0とする。

## 2026-11-29 起動

- 退化診断summaryは45 runを検証し、新規15 runと既存0.1/0.1秒の15/15完全一致、
  Reject後同一key再登場0、物理衝突0を確認した。
- 実行sourceは`44b220c35ec4b7e97af5f72899cc4631c06f6864`。sgnlabのUbuntuData上の
  cleanなdetached worktree `mcs-tiv-intersection-accept-lock-control`を使用し、preflightは成功した。
- user systemd unitは`mcs-intersection-accept-lock-sweep-20261129.service`、invocation IDは
  `698791cc688c4b0991a36956e81a81cd`。raw rootはUbuntuData上の
  `mcs-tiv-diagnostic-artifacts/intersection-accept-lock-sweep-20261129/`。
- 起動後readbackでunit `active/running`、Accept 0.3秒の第1波run manifest 15、SUMO 15、
  runner 3を確認。全15 manifestでsource、開始時clean、generic lock 1.0秒、
  Accept lock 0.3秒、Reject lock 1.0秒、heading fallback有効が一致し、失敗は0。
- 各波は子batchがすべてreturn code 0の場合だけ次へ進み、失敗は自動再実行しない。
