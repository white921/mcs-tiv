# 正規化凸結合式 lambda 広域600秒スイープ

- 台帳ID: `2026-11-17-normalized-convex-lambda-wide-sweep-600s-development`
- 状態: `completed`
- 位置づけ: `development screening`
- 開始日時: 2026-11-17 20:56:23 JST
- 終了日時: 2026-11-19 11:53:05 JST
- 新規実験ディレクトリ:
  - `results/runs/normalized-convex-lambda000-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda010-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda020-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda030-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda040-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda050-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda060-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda070-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda080-eval7-r1000-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda100-eval7-r1000-a1000-seeds33-42-600s-20261117/`
- 既存再利用:
  - `lambda=0.90`: `results/runs/normalized-convex-lambda090-eval7-r1000-a1000-seeds33-42-600s-20261116/`
  - `lambda=0.95`: `results/runs/normalized-convex-lambda095-eval7-r1000-a1000-seeds33-42-600s-20261116/`
  - `lambda=80/81`: `results/runs/normalized-convex-600s-proposal-eval7-r1000-a1000-seeds33-42-20261115/`

## 目的

正規化凸結合式

`M = (1 - lambda) * Z_time + lambda * Z_follow`

について、定義域`[0, 1]`を広く探索し、1000/1000 veh/h・600秒条件で全車平均速度が
最大となる領域と、合流側・本線側の性能トレードオフを調べる。最終的なlambdaを一点だけ
選ぶ前に、交通性能のlambda依存曲線と破局的seedを確認する。

## 探索設計

- 粗い主グリッドを`0.0, 0.1, ..., 1.0`とする。
- 同一条件で実行済みの`0.90`は再実行しない。
- 既存の`0.95`と`80/81 = 0.987654...`も高lambda側の補助点として再利用する。
- 新規候補は`0.0`から`0.8`までの9候補と`1.0`の計10候補、100 runとする。
- 全runを「lambda昇順、その中でseed昇順」の単一キューへ並べ、機械全体15 slotを使う。
  最初はlambda 0.0を10件、次にlambda 0.1を5件投入し、1件終了するたびにキュー先頭の
  1件を補充する。あるlambdaの全10件終了を待ってから次へ進む方式にはしない。
- 粗いスイープ完了後、最良領域の両隣を細かく追加する。追加点は粗い結果を見る前には
  固定せず、別のdevelopment記録として扱う。

## 候補選択規則

1. 異常終了、ソース変更、固定入力不一致、物理衝突がある候補を採用候補から除外する。
2. 10 seedの全車平均速度を主指標とする。
3. 合流側速度、本線側速度、停止時間、急減速時間、流出台数、未挿入・残留、Accept率、
   最悪seed、seed間標準偏差を併記し、一方の流入やtail riskの悪化を平均値で隠さない。
4. 平均1位だけでなく、seed対応差とbootstrap区間、Pareto関係を確認する。
5. 粗いグリッドで隣接候補との差が不明確なら一点に決めず、細密探索へ進める。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.7 |
| 方式 | 正規化減速伝播提案 |
| 新規lambda | `0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0` |
| 既存再利用lambda | `0.90, 0.95, 80/81` |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl` |
| 交通量・Bus比率 | 合流側1000 / 本線側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| screeningログ | diagnostic traceなし、checkpointなし。manifest、runner/stdout/stderr、評価指標、物理衝突、prediction auditは保存 |
| Python / SUMO | 3.15.1 / 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列 | lambda昇順の共有キュー、機械全体最大15 SUMO、終了ごとに1件補充 |

diagnostic traceとcheckpointは探索コストを抑えるため新規候補では無効にする。評価式、
SUMO挙動、固定入力、seedは変更しない。上位候補を最終候補へ進めるときは、診断traceと
checkpointを有効にした別バッチで完全性を確認する。

## Git情報

| 項目 | 値 |
| --- | --- |
| 実行ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 実行開始時dirty | `false`を必須とする |
| 記録branch | `codex/normalized-convex-lambda-wide-sweep-600s-development` |
| 結果commit | lambdaごとの専用commitを後述 |

`lambda=0.90/0.95`の既存600秒結果も実行ソースは`e0f36fc...`である。`80/81`の既存結果は
`1125fb122...`だが、`1125fb122...`から`e0f36fc...`までの差分はAGENTSと実験台帳だけで、
シミュレーションコードと固定入力は同一である。

各新規lambdaは開始時Git cleanを独立に保証するため、`e0f36fc...`から作成したlambda別の
detached worktreeで実行する。結果ディレクトリは各worktreeの`results/runs/`に保存する。

## 実行コマンド

各runの実行条件は次のbatch runner相当とし、実際の投入は
`scripts/run_lambda_shared_queue.py`がlambda昇順・seed昇順に行う。

```text
scripts/run_thesis_batch.py
  --cases eval7
  --seeds 33 34 35 36 37 38 39 40 41 42
  --duration 600
  --eval7-flows 1000 1000
  --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl
  --bus-allocation fixed
  --workers 10
  --deceleration-active
  --deceleration-convex-lambda <lambda>
  --no-diagnostic-traces
  --checkpoint-interval 0
  --run-name normalized-convex-lambda<tag>-eval7-r1000-a1000-seeds33-42-600s-20261117
```

## 起動

### 端点smoke

2026-11-17 20:54 JSTにlambda 0.0と1.0をseed 33・10秒で実行し、両方で
`exit_code: 0`、`source_unchanged: true`、Python 3.15.1、SUMO 1.28.0を確認した。
stderrは空で、smokeは正式結果と分けてUbuntu上のquarantineへ保存した。

### 正式実行

初回unitはsystemd-runがshell配列の変数を起動前に展開し、lambdaが空文字となって
runnerの引数検証で`exit status 2`になった。SUMO、実験ディレクトリ、run manifestは
生成されておらず、正式runの失敗には数えない。

- 初回unit: `mcs-normalized-convex-lambda-wide-sweep-600s-20261117.service`
- invocation ID: `3b84f40d824f49a091c0c29c69bf8cc1`

`--expand-environment=no`を付けたattempt 2を2026-11-17 20:56:23 JSTに起動した。
lambda 0.0のexperiment manifest、10 run manifest、実行ソース、開始時Git clean、固定条件、
lambda 0.0、10 SUMOを読み取り確認した。後続lambdaは独立worktreeで小さい順に実行する。

- lambda 0.0 unit: `mcs-normalized-convex-lambda-wide-sweep-600s-20261117-attempt2.service`
  - invocation ID: `b2bec7f0bd124140ac4fc00038f9dc4f`
- lambda 0.1以降の継続unit:
  `mcs-normalized-convex-lambda-wide-sweep-600s-20261117-continuation.service`
  - invocation ID: `caabdee08715439f86ee9a53cfb7e1c9`

当初はlambda 0.0完了後に候補単位で次を始める継続unitを用意したが、ユーザー指定により
2026-11-17 21時台に、15 slotの共有キュー方式へ変更した。継続unitはlambda 0.1を始める前に
停止しており、重複runや条件変更はない。lambda 0.0の10件はそのまま継続し、空き5 slotから
lambda 0.1を投入する。以後は1件終了ごとにlambda昇順・seed昇順の次runを補充する。

共有キューはlambda別のclean worktreeからrunnerの`run_task`を呼び、lambda別に通常の
experiment manifest、run manifest、summary、runner logを生成する。機械全体のSUMO数が
15を超えた場合またはrunが失敗した場合は、新規投入を停止し、自動再実行やseed差し替えを
行わない。

- 共有キューunit: `mcs-normalized-convex-lambda-shared-queue-600s-20261117.service`
  - invocation ID: `58c09b13e4d34f96919c5be6a0f91a8b`
  - scheduler commit: `6b28b81a4`
  - scheduler SHA-256: `0e7b7a8051e7682408372c1f2cb7bf71fe9e2313bb8227f8493c22429305e4ab`

2026-11-17 21:06:48 JSTに共有キューを起動した。開始時はlambda 0.0が10件実行中で、
lambda 0.1のseed 33–37を5件投入した。約10秒後に実SUMO 15 process、lambda 0.1の
run manifest 5件、lambda 0.2のrun manifest 0件を読み取り、指定どおりlambda昇順に
15 slotが埋まったことを確認した。

- heartbeat: `mcs-2`（`MCS λ広域スイープ監視`、queue実行中は30分間隔）

## 完了・完全性確認

- [x] 新規10バッチ・100 runが正常完了
- [x] 全runが`exit_code: 0`、`source_unchanged: true`
- [x] 実行開始時Git clean、source SHA、固定入力SHAを確認
- [x] lambda以外の条件が全候補で一致
- [x] Python/SUMO版、manifest、runner/stdout/stderr、評価指標を確認
- [x] 物理衝突と致命的ログを確認
- [x] lambda別・seed別集計と既存3候補を統合
- [x] 正常結果だけをlambdaごとの専用commitで保存・push

## 結果

### 正常終了と完全性

2026-11-19 11:53:05 JSTに新規100 runが完了した。全100 runで
`exit_code: 0`、`source_unchanged: true`、実行開始時Git clean、実行ソース
`e0f36fc...`、同一seedの固定入力SHA一致、Python 3.15.1、SUMO 1.28.0を確認した。
各runのmanifest、runner/stdout/stderr、evaluation metrics、prediction audit、物理衝突を
監査し、致命的ログ0、物理衝突0だった。diagnostic traceとcheckpointがないことは
screening設計どおりである。共有queueの`slot_filled`と`simulation_started`はともに
queue index 0–89の昇順・重複なしで、実SUMO数の最大は15だった。

流出台数はFCDへ1回以上現れ、最終時刻599.9秒に残っていない固定入力車両数とした。
未挿入は予定332台からFCD挿入台数を引いた値、残留は599.9秒にFCDへ残る車両数である。
Accept率は10 seedの判定回数を合算した。速度と時間指標はseed単位値の平均である。

### lambda別の主要指標

| lambda | 全車速度 [m/s] | 合流側 [m/s] | 本線側 [m/s] | 停止 [s] | 急減速 [s] | 流出 | 未挿入 | 残留 | Accept率 | 最悪seed | 衝突 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 4.5159 ± 0.3447 | 2.6255 | 7.8041 | 3352.88 | 8.89 | 232.1 | 59.1 | 40.8 | 52.35% | 3.9830 | 0 |
| 0.10 | 4.4164 ± 0.4267 | 2.4742 | 7.8518 | 4123.50 | 6.36 | 227.8 | 62.5 | 41.7 | 48.55% | 3.6405 | 0 |
| 0.20 | 4.4932 ± 0.3286 | 2.5251 | 8.0109 | 3867.75 | 6.47 | 231.0 | 60.4 | 40.6 | 48.76% | 3.9985 | 0 |
| 0.30 | 4.4723 ± 0.3797 | 2.4989 | 8.0533 | 3842.82 | 4.79 | 227.8 | 62.6 | 41.6 | 47.90% | 3.5894 | 0 |
| 0.40 | 4.4431 ± 0.3424 | 2.4526 | 8.0042 | 3984.97 | 5.04 | 227.8 | 63.6 | 40.6 | 44.28% | 3.9321 | 0 |
| 0.50 | 4.6273 ± 0.3512 | 2.5834 | 8.5729 | 3642.46 | 7.30 | 230.2 | 59.4 | 42.4 | 43.01% | 3.6557 | 0 |
| **0.60** | **4.6835 ± 0.2465** | 2.5949 | 8.7130 | 3438.13 | 5.49 | **232.3** | **59.0** | 40.7 | 38.44% | **4.2077** | 0 |
| 0.70 | 4.6707 ± 0.2456 | 2.5285 | 8.8670 | 3968.26 | 4.98 | 227.8 | 62.0 | 42.2 | 34.20% | 4.1699 | 0 |
| 0.80 | 4.6635 ± 0.2210 | 2.4290 | 9.1383 | 4406.47 | 5.99 | 228.2 | 65.0 | 38.8 | 28.45% | 4.1855 | 0 |
| 0.90※ | 4.5829 ± 0.2811 | 2.2115 | 9.6059 | 5214.93 | 4.26 | 222.0 | 72.0 | 38.0 | 21.81% | 3.7997 | 0 |
| 0.95※ | 4.4961 ± 0.1347 | 1.9901 | 10.0514 | 5757.18 | 4.27 | 215.5 | 79.8 | 36.7 | 14.17% | 4.3202 | 0 |
| 80/81※ | 4.1878 ± 0.2225 | 1.5818 | 10.1169 | 7458.53 | 3.85 | 202.1 | 92.5 | 37.4 | 9.92% | 3.6821 | 0 |
| 1.00 | 4.1423 ± 0.1728 | 1.4404 | **10.5400** | 8216.43 | **3.56** | 196.6 | 97.5 | 37.9 | 7.70% | 3.8603 | 0 |

※は同一条件の既存完了結果を再集計した値。`0.90/0.95`の合流側速度は各runの
`stderr.log`を再読みした値で、既存記録の`2.1210/1.9091`はそれぞれ
`2.2115/1.9901`の誤記と確認した。

### seed対応差と不確実性

新規候補の平均1位は`lambda=0.60`だった。seed対応percentile bootstrapを200,000回行い、
固定乱数seedは`20261119`とした。

| 比較 | 全車速度差 [m/s] | 0.60より高いseed | 95% bootstrap区間 [m/s] |
| --- | ---: | ---: | ---: |
| 0.50 − 0.60 | -0.0562 | 6/10 | [-0.3880, +0.1821] |
| 0.70 − 0.60 | -0.0128 | 6/10 | [-0.1755, +0.1340] |
| 0.80 − 0.60 | -0.0200 | 6/10 | [-0.2087, +0.1583] |
| 1.00 − 0.60 | -0.5411 | 0/10 | [-0.6257, -0.4304] |
| 0.60 − 0.90 | +0.1006 | 7/10 | [-0.0787, +0.2751] |
| 0.60 − 0.95 | +0.1874 | 9/10 | [+0.0623, +0.3062] |
| 0.60 − 80/81 | +0.4956 | 9/10 | [+0.3217, +0.6456] |

`0.60`は平均速度、流出台数、未挿入、最悪seedを同時に良好に保ち、粗いグリッドの
中では最もバランスが良かった。ただし`0.50–0.80`の対応区間は重なり、`0.60`の
一般的優越性は確立していない。`0.60`からlambdaを増やすと本線側速度と急減速時間は
改善する一方、合流側速度、停止時間、流出台数、未挿入が悪化する。`1.00`は本線保護に
極端に偏り、全車速度と合流側処理性能が明確に低下した。

全車・合流側・本線側速度と流出を最大化、停止・急減速・未挿入・残留を最小化する
集計値のPareto監査では、`0.10`と`0.50`は`0.60`に支配された。その他は少なくとも1指標の
トレードオフが残った。

### 次の細密探索

次のdevelopmentでは既存の`0.50, 0.60, 0.70, 0.80`を再利用し、中間点`0.55, 0.65, 0.75`を
同一seedで追加する。最終的なlambda選択はこの既使用seed集合で完結させず、診断traceと
checkpointを有効にした候補確認後、未使用seedで行う。

### 結果保存

prediction JSONLとSUMO FCD XMLを`gzip -n -6`で可逆圧縮し、復元SHA-256、サイズ、行数を
全200 artifactで照合した。圧縮対象は31,359,963,651 bytesから9,656,445,874 bytesになった。
100 MB以上の圧縮ファイルは80,000,000 byte単位へ分割し、連結SHAを照合した。

| lambda | 結果branch | 結果commit |
| ---: | --- | --- |
| 0.00 | `codex/normalized-convex-lambda000-600s-20261117` | `e4d333df0c88460b0531cf9c94d20536dbed0ae7` |
| 0.10 | `codex/normalized-convex-lambda010-600s-20261117` | `cc1239097cc5a6e7c36d2edb60a31ef1055f0dcc` |
| 0.20 | `codex/normalized-convex-lambda020-600s-20261117` | `9e2fc87ec42730324aff67a6e34a942aef9c851b` |
| 0.30 | `codex/normalized-convex-lambda030-600s-20261117` | `361b7f6cd973f804d67acecc1309ab4b0db6a9d2` |
| 0.40 | `codex/normalized-convex-lambda040-600s-20261117` | `65be901d0c0b673e22233d98f3c176a3f8b2ae0d` |
| 0.50 | `codex/normalized-convex-lambda050-600s-20261117` | `3cc9a7b34aec909295c329e0b7ffb892412e5945` |
| 0.60 | `codex/normalized-convex-lambda060-600s-20261117` | `0a99095a946f466784996d3f2fed442f3b42bc2f` |
| 0.70 | `codex/normalized-convex-lambda070-600s-20261117` | `87578b6cfbfbc54ee7b21ff1780acfe9360adad0` |
| 0.80 | `codex/normalized-convex-lambda080-600s-20261117` | `27474dacd87e0469620c9e0f1622247e1a26ec3c` |
| 1.00 | `codex/normalized-convex-lambda100-600s-20261117` | `acdff18005d7ce11bf6437097ebec2824dea54e2` |

各実験ディレクトリの`post-run-audit.json`、`compression-audit.json`、
`storage-split-audit.json`はすべて`all_verified/ok: true`である。lambda 0.00の結果に
`lambda-wide-sweep-summary.json`としてseed別・候補別集計も保存した。

## 限界

seed 33–42は過去の候補選択と比較に使用済みであり、本実験は独立holdoutではない。
本実験はlambda曲線の探索用developmentであり、細密探索後にlambdaを固定し、未使用seedで
最終評価する。新規候補と既存再利用候補で診断ログの有無は異なるが、交通条件、入力、
評価式とシミュレーション挙動は同一である。
