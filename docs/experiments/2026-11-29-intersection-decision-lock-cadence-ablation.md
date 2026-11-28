# 交差点の判断ロック周期アブレーション

- 台帳ID: `2026-11-29-intersection-decision-lock-cadence-ablation`
- 状態: `completed`
- 位置づけ: `diagnostic development ablation`

## 目的

合流では提案法が山下TIVtepを上回る一方、T字路と十字路で安定して上回らない
原因候補として、提案法のみが使う1秒の重複判断ロックと交差点の0.1秒周期の
競合・合意更新の不整合を調べる。lane metadata heading fallbackは有効のまま固定し、
判断ロックだけを`1.0 s`からSUMO/MCS制御周期と同じ`0.1 s`へ短縮する。

## 事前証拠と起動gate

[lane metadata heading fallbackアブレーション](2026-11-28-intersection-lane-heading-fallback-ablation.md)
は15/15 run成功・物理衝突0で、unsupportedを0%へ下げたが、Eval.5の速度は
`-0.2994 m/s`、平均停止時間は`+78.30 s`悪化した。既存traceの事後解析では次を
確認した。

- Eval.5 seed 15は停止時間`+135.8 s`、seed 20は`+434.4 s`。
- 停止時間増加`+783.0 s`のうち、`BL/BR/TL/TR`の上下方向右左折が
  `+606.3 s` （77.4%）を占めた。
- seed 15はactive attemptが`425→713`、判断が`552→903`、合意取消が`68→128`。
  seed 20はそれぞれ`371→761`、`453→972`、`60→130`となった。
- seed 15では77.2 sに両方式が同じAcceptを選んだ後、提案評価成功側だけ78.3–79.1 sを
  `decision_locked`で抑止し、山下fallback側は0.1秒ごとにAcceptと経路更新を繰り返した。
  車両12の予定経路は78.3 sに分岐した。
- heading fallbackで完全評価できたEval.5の4,035判断は平均4.11台の後続車を
  捕捉したが、個別follower effectの68.4%は0で、重み付き後続車項は到着時刻項の
  約26%の大きさに留まった。

起動は元アブレーションの機序gate成立、性能gate不成立、15/15完全性監査成功、
物理衝突0を条件とする。

## 条件

| 形状 | 交通量 (veh/h) | seed | run |
| --- | --- | --- | ---: |
| Eval.3 T字路 | 500 / 500 / 500 | 13–17 | 5 |
| Eval.5 十字路 | 300 / 300 / 300 / 300 | 13–22 | 10 |

- 新規15 run、300 s、`lambda=0.95`、Bus比25% fixed-nearest。
- 既存のheading fallback有効・ロック1.0秒runを同一seed対照とし、対照は再実行しない。
- 変更は`--deceleration-decision-lock-seconds 0.1`だけ。heading fallback、予測式、
  `lambda`、固定入力、並列条件は変更しない。
- 3 cohort×5 workerでmachine-wide 15 SUMO。失敗は自動再実行しない。

## 評価と判断

- 主診断: 対応seedの停止時間、全車平均速度、active attempt、判断数、
  `decision_locked`抑止、合意取消数。
- 形状別に速度と停止時間が改善し、seed 15/20の交渉増幅が縮小すれば、
  1秒ロックと交差点制御周期の不整合を性能差の有力な原因とする。
- 安全gate: 15/15正常終了、完全性監査成功、物理衝突0。
- development seedのため一般的優越性は主張しない。結果の良否にかかわらず、
  未使用seedの正式検証は自動起動しない。

## 実行・保存

- scheduler: `scripts/run_intersection_decision_lock_cadence_ablation.py`
- finalizer: `scripts/finalize_intersection_decision_lock_cadence_ablation.py`
- source branch: `codex/intersection-heading-diagnostic`
- raw output: UbuntuData上の`mcs-tiv-diagnostic-artifacts/`。
- 完了後はmanifest、metrics、物理衝突、固定入力hash、診断artifact、checkpoint、
  致命ログを監査し、この記録へ対応比較を追記する。

## 2026-11-29 起動

- 実行sourceは`708f7334476068cc6cd8cbc942fc18e71e04e0e6`。sgnlabのUbuntuData上に
  cleanなdetached worktreeを作成し、関連47テストとpreflightを通過した。
- user systemd unit
  `mcs-intersection-decision-lock-cadence-ablation-20261129.service`で起動した。
  invocation IDは`435fd04859e4417fa3a9205331550c4d`。
- 起動後readbackはunit `active/running`、run manifest 15、SUMO 15/15。全manifestで
  source commit、開始時clean、`lambda=0.95`、heading fallback有効、decision lock `0.1 s`を
  確認した。失敗は0。
- raw rootは
  `/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-diagnostic-artifacts/intersection-decision-lock-cadence-ablation-20261129/`。
- heartbeat `mcs-heading`は30分間隔で有効。最遅active runが180/300 s以上になったら
  15分へ変更し、完了監査後に停止する。

## 完了後の分岐

1. 15/15正常終了、完全性監査、物理衝突0のいずれかを満たさない場合は停止する。
   失敗runを自動再実行せず、原因と再現条件だけを保存する。
2. `cadence_hypothesis.supported=true`の場合は、1秒ロックを交差点性能差の有力な
   原因とする。ただしdevelopment seedのため、そのまま方式採用や優越性を主張しない。
   seed 15/20のtraceで交渉増幅が縮小したことを確認したうえで、未使用seedによる
   山下法・1.0秒・0.1秒の正式な三者比較案を作る。正式runは自動起動しない。
3. 形状別の速度・停止時間またはseed 15/20の改善が一部だけ成立する場合は、
   cadenceを単独主因とせず、完成traceを用いてturn・競合点・判断種別ごとの差を先に
   解析する。追加計測が必要と判明するまで新規runを起動しない。
4. `cadence_hypothesis.supported=false`で改善信号も乏しい場合は、1秒ロック仮説を棄却し、
   後続車項の捕捉範囲と実効寄与の小ささを次の主対象とする。既存traceから測定可能な
   変更仮説を作り、回帰テストと15-run診断条件を用意してから次バッチを判断する。

## 実行中の先行監査

- 最初に完了したEval.5 seed 19はexit 0、source不変、必須成果物完備、物理衝突0だった。
- 305 active attemptのうち304件を評価し、1件だけ130.5 sに
  `trajectory does not enter the detected conflict region within the horizon`でunsupportedとなった。
  heading/yaw欠損の再発ではない。0.1秒化によって評価機会自体が変わるため、finalizerは
  unsupportedをrun失敗条件にせず、対照との差と理由をcadence outcomeとして集計する。
- 残りrunは自動再実行せず継続し、全15本の完全性とunsupported総数を完了後に監査する。
- Eval.3 seed 14にもunsupportedが1件あったが、578 attemptに対して監査recordsが500件で
  上限打ち切りされ、理由レコードは保持されていなかった。finalizerは総数カウンタを正本とし、
  理由を保持できなかった件数を`unsupported_reasons_unattributed`として別集計する。

### Eval.5先行完了結果

Eval.5の10/10 runが完了し、全runが完全性・物理衝突0の監査を通過した。1.0秒対照との
対応比較は、平均速度`+0.3094 m/s`、平均停止時間`-84.52 s`、速度勝利`6/10`、
速度差bootstrap 95% CI `[-0.0689, +0.7555] m/s`だった。点推定と停止時間は改善したが、
CIは0をまたぐため、この10 seedだけで安定改善とはしない。

- 問題が大きかったseed 15は速度`+1.7710 m/s`、停止時間`-341.2 s`、判断`-461`、
  合意取消`-88`。
- seed 20は速度`+1.1349 m/s`、停止時間`-417.0 s`、判断`-401`、合意取消`-74`。
- 10 seed平均で合意取消は`-14.5`、`decision_locked`抑止は`-152.9`だった。
- unsupported差はseed 19の1件だけ。全体のcadence gateはEval.3完了まで判定しない。

## 完了監査と最終結果

- 15/15 run正常終了、failed 0、unit `Result=success`、残存SUMO/runner 0。
- 全runでsource commit `708f7334476068cc6cd8cbc942fc18e71e04e0e6`、開始時clean、
  source不変、固定入力hash、`lambda=0.95`、heading fallback有効、decision lock `0.1 s`、
  checkpoint 5以上、必須artifactを確認した。
- 物理衝突0、致命ログ0。unsupportedは全15 runで2件だった。Eval.5 seed 19の1件は
  conflict regionが予測horizon内にないためで、Eval.3 seed 14の1件は500-record上限外だった。
- 比較summaryはUbuntuData上の
  `mcs-tiv-diagnostic-artifacts/intersection-decision-lock-cadence-ablation-summary-20261129.json`。
  byte sizeは`12,578`、SHA-256は
  `4296f73c8344de852a9bc8713369eff91b2369e3b1846ccc2f9e0f385304fcd0`。

| 条件 | 速度差 (0.1 s - 1.0 s) | 95% CI | 速度勝利 | 停止時間差 | 判断数差 | 取消数差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Eval.3 T字路 | `-0.3468 m/s` | `[-0.7507, +0.2386]` | 1/5 | `+94.12 s` | `+179.6` | `+7.4` |
| Eval.5 十字路 | `+0.3094 m/s` | `[-0.0689, +0.7555]` | 6/10 | `-84.52 s` | `-4.7` | `-14.5` |

事前定義した`cadence_hypothesis.supported`は`false`だった。Eval.5では点推定、停止時間、
特にseed 15/20の交渉増幅が改善したため、1秒ロックが一部の十字路渋滞を悪化させた証拠は
得られた。一方、Eval.3では0.1秒化により判断が平均179.6件増え、速度と停止時間が悪化した。
したがって、1秒ロックを「交差点が山下法を安定して上回らない」共通の単独原因とはしない。
ロックはT字路では再判断振動を抑える安定化要素、十字路の一部では古い判断を保持する要素として
逆向きに作用した可能性が高い。

次は新規runを起動せず、完成traceを用いてEval.3の増加した判断をturn・競合点・判断種別・
車両単位に分解し、Eval.5 seed 15/20で縮小した交渉増幅との違いを特定する。heartbeatは
完了監査後に停止した。development seedのため正式な優越性主張や未使用seed検証は行わない。

## 完了traceによるEval.3分解

1.0秒対照と0.1秒runの`vehicle-states.jsonl`を同一seedで対応させ、速度`<0.1 m/s`を
0.1秒刻みで経路別に再集計した。5 seedの停止時間差合計は`+470.6 s`で、正式metricsの
平均差`+94.12 s × 5`と一致した。

- `RB`は`+261.0 s`、`RL`は`+192.0 s`で、右側流入2経路がnet停止増加の96.3%を占めた。
- 一方、`BL`は`-44.3 s`、`LB`は`-9.2 s`であり、全方向が一様に悪化したのではない。
- 5 seed合計の判断数は`+898`、`decision_locked`抑止は`-568`、適用は`+354`だった。
- 増加した主な判断は`RB→LR Reject +211`、`BL→RB Accept +205`、
  `RB→LB Accept +161`、`BL→LR Reject +126`、`RB→BL Reject +113`、
  `RB→LB Reject +99`で、中央付近の右・下流入間の競合に集中した。
- `missing_sender_conflict_region`によるdeferredはnet`+110`、
  `desired_path_disappeared`による取消はnet`+29`増えた。

したがってEval.3では、0.1秒化が単に最新情報へ追従したのではなく、同じ中央競合を短周期で
再発火させ、経路生成・適用・消失を繰り返す判断churnを作った。1秒lockはここではdebounceとして
機能していた。一方、Eval.5 seed 15/20では1秒保持の解除が交渉増幅を縮小したため、固定の
`0.1 s`または`1.0 s`を全形状へ共通適用する方針は採らない。次の変更候補は、経過秒数ではなく
conflict region、desired path、agreement setなどの実質的状態変化があった場合だけ再評価する
state-aware hysteresisとする。実装・回帰テスト・15-run診断条件を用意するまでは追加runを起動しない。
