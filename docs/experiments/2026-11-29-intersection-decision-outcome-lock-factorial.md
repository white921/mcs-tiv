# 交差点のAccept/Reject別判断ロック2×2要因診断

- 台帳ID: `2026-11-29-intersection-decision-outcome-lock-factorial`
- 状態: `running`
- 位置づけ: `diagnostic development factorial ablation`

## 目的

[判断ロック周期アブレーション](2026-11-29-intersection-decision-lock-cadence-ablation.md)で、
1.0秒から0.1秒への共通変更はEval.3 T字路を悪化させ、Eval.5十字路の一部seedを改善した。
lockは判断だけでなく、lock中のalternative path再生成も抑止する。そのため、共通周期だけでは
次の2要因を分離できない。

1. Accept後にalternative pathを短周期で更新・再評価する効果。
2. Reject後に早く再評価し、拒否状態から抜ける効果。

既存の`Accept=1.0/Reject=1.0`と`Accept=0.1/Reject=0.1`は再実行せず、欠けている2条件を追加して
2×2要因診断とする。

## 事前証拠

- Eval.3の0.1秒化は、Accept `+390`、Reject `+508`、適用`+354`、判断`+898`、
  停止時間`+94.12 s`、速度`-0.3468 m/s`。
- Eval.5の0.1秒化は、Accept `+720`、Reject `-767`、判断`-47`、停止時間`-84.52 s`、
  速度`+0.3094 m/s`。
- Eval.5 seed 15/20のRejectは`-421/-402`、Acceptは`-40/+1`。改善は単純なAccept回数増加ではない。
- Eval.5 seed 15の個別traceでは、desired path、conflict point、participantが不変のまま、
  0.1秒条件のalternative path IDだけが更新された。

## 条件

| 追加arm | Accept後lock | Reject後lock | 形状・seed | run |
| --- | ---: | ---: | --- | ---: |
| accept-short / reject-long | `0.1 s` | `1.0 s` | Eval.3 seed 13–17 + Eval.5 seed 13–22 | 15 |
| accept-long / reject-short | `1.0 s` | `0.1 s` | Eval.3 seed 13–17 + Eval.5 seed 13–22 | 15 |

- Eval.3 `500/500/500 veh/h`、Eval.5 `300/300/300/300 veh/h`、各300 s。
- `lambda=0.95`、Bus比25% fixed-nearest、lane metadata heading fallback有効を固定。
- 既存1.0/1.0秒と15/15、0.1/0.1秒と15/15を同一seed対照とする。
- 新規30 run。15 SUMOの2波で実行し、第1波の子batchに失敗があれば第2波を自動起動しない。
- 失敗runは自動再実行しない。

## 評価と判断

- 形状別に速度、停止時間、急減速、Accept/Reject、applied/waiting、cancelled、deferred、
  suppressedを同一seedで比較する。
- Accept側のみ短縮で改善すれば、alternative path更新またはAccept再評価を主要因候補とする。
- Reject側のみ短縮で改善すれば、RejectからAcceptへの状態遷移遅延を主要因候補とする。
- 両方短縮だけが改善する場合は相互作用、どの固定条件も形状間で逆方向なら、
  形状固有の交渉状態を持つ設計が必要とする。
- 安全gateは30/30正常終了、完全性監査、物理衝突0。development seedのため一般的優越性は主張しない。

## 実行・保存

- scheduler: `scripts/run_intersection_decision_outcome_lock_factorial.py`
- finalizer: `scripts/finalize_intersection_decision_outcome_lock_factorial.py`
- source branch: `codex/intersection-heading-diagnostic`
- raw output: UbuntuData上の`mcs-tiv-diagnostic-artifacts/`。
- 完了後はmanifest、metrics、固定入力hash、checkpoint、物理衝突、致命ログを監査し、
  4条件の対応比較summaryを作成する。

## 2026-11-29 起動

- 実行sourceは`26edd1f07c113c2c61002c362358e9381978039e`。sgnlabのUbuntuData上にあるcleanな
  detached worktreeを同commitへ更新し、関連92テスと実験台帳監査を通過した。
- schedulerのpreflightは、既存の1.0/1.0秒と15 run、0.1/0.1秒と15 run、物理衝突0、
  共通cadence仮説不成立を起動gateとして検証した。
- user systemd unitは
  `mcs-intersection-decision-outcome-lock-factorial-20261129.service`、invocation IDは
  `c14b3f8416924807ab52ba640ed2d826`。
- raw rootは
  `/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-diagnostic-artifacts/intersection-decision-outcome-lock-factorial-20261129/`。
- 起動後readbackでunit `active/running`、第1波run manifest 15、SUMO 15/15、runner 3を確認。
  全manifestでsource commit、開始時clean、共通lock 1.0秒、Accept lock 0.1秒、Reject lock 1.0秒が
  一致した。失敗は0。
- heartbeat `mcs-heading`は30分間隔でACTIVE。最遅active runが180/300秒以上なら15分へ変更し、
  第2波開始で180秒未満へ戻れば30分へ戻す。
