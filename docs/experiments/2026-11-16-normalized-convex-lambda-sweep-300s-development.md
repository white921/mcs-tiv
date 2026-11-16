# 正規化凸結合式 lambda 300秒スイープ

- 台帳ID: `2026-11-16-normalized-convex-lambda-sweep-300s-development`
- 状態: `completed`
- 位置づけ: `development`
- 開始日時: 2026-11-16 02:00:07 JST
- 終了日時: 2026-11-16 10:40:42 JST
- 実験ディレクトリ:
  - `results/runs/normalized-convex-lambda090-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda093-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda095-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda40over41-eval7-r1000-a1000-seeds33-42-300s-20261116/`
  - `results/runs/normalized-convex-lambda80over81-eval7-r1000-a1000-seeds33-42-300s-20261116/`

## 目的

正規化凸結合式の`lambda=80/81`は旧式の生係数比を理論上の最大値で換算した値であり、
交通性能に対する最適値ではない。2026-11-15実験で提案方式のAccept率が山下方式より
低かったため、現行値近傍でlambdaを下げ、全車平均速度を改善できる候補を探索する。

## 仮説と比較対象

- 仮説: lambdaを`80/81`から適度に下げると到着時間差項の寄与が増え、過度なRejectが減り、
  全車平均速度が改善する。
- 比較対象: `lambda=80/81`を現行基準とし、`0.90`, `0.93`, `0.95`, `40/41`を比較する。
- 変更するもの: 正規化凸結合式のlambdaのみ。
- 固定するもの: 実行ソース、seed、固定入力、交通量、Bus比率、軌道生成、競合検出、
  交渉プロトコル、`T_pred=10 s`、`N_max=40`。
- 本seed集合は過去結果を確認済みであり、候補選択専用のdevelopmentデータとする。
  採用候補を固定した後の最終評価には再利用しない。

## 候補選択規則

1. 物理衝突、異常終了、ソース変更がある候補は除外する。
2. 10 seedの全車平均速度の平均が高い候補を優先する。
3. 上位候補間のseed対応差が明確でない場合は上位2候補を600秒developmentへ進める。
4. 減少車線・継続車線の速度、流出台数、停止時間、急減速時間、最悪seedを併記し、
   一方の車線の破局的悪化を平均値で隠さない。
5. 300秒結果を見た後に候補lambda、seed、固定入力、交通条件を差し替えない。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.7 |
| lambda | `0.90`, `0.93`, `0.95`, `40/41`, `80/81` |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 300 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl`の300秒prefix |
| 交通量・Bus比率 | 要求側1000 / 受入側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 記録方針 | screeningのためdiagnostic traceとcheckpointを無効化。実際にはruntimeは生成されず、prediction-event auditは生成されたため、終了後に可逆圧縮して保存 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | 機械全体最大15（5候補×3 worker） |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| 元ブランチ | `codex/conflict-region-arrival` |
| 実行ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | `codex/normalized-convex-lambda090-sweep-20261116` @ `b918343bc665cabbcf3f4a0c950897b70021f11d`<br>`codex/normalized-convex-lambda093-sweep-20261116` @ `cb2ea78ea5086c7957af7398b227225410dd3025`<br>`codex/normalized-convex-lambda095-sweep-20261116` @ `17d94c17b7d87a1a3e69b3ae8a7918f99f906fbe`<br>`codex/normalized-convex-lambda40over41-sweep-20261116` @ `fe96fb7adc71b163b353f6ac496c120e4f9a8ad3`<br>`codex/normalized-convex-lambda80over81-sweep-20261116` @ `bddd06fe94c31de371f985cd7e8d2d0428238250` |
| 記録commit | 完了更新commitを作成後に記録する |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 300 --eval7-flows 1000 1000 --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl --bus-allocation fixed --workers 3 --deceleration-active --deceleration-convex-lambda <lambda> --no-diagnostic-traces --checkpoint-interval 0` |

実行unitは`mcs-normalized-convex-lambda{090,093,095,40over41,80over81}-300s-20261116.service`。
各候補を同一commitから作ったsparse worktreeで実行し、候補ごとに3 worker、機械全体で
実SUMO 15並列とする。正式実行前にλ=0.95・seed 33・10秒smokeがPython 3.15.1、
SUMO 1.28.0、`exit_code=0`、`source_unchanged=true`で完了した。

## 完了・完全性確認

- [x] 5バッチ・50 runが正常完了
- [x] 全Runが`exit_code: 0`
- [x] 全Runが`source_unchanged: true`
- [x] 固定入力hashと300秒prefix hashが候補間で一致
- [x] runner/stdout/stderr、評価指標を確認（runtimeは未生成）
- [x] 物理衝突と致命的ログを確認
- [x] 候補選択規則に従って上位候補を決定
- [x] 正常結果だけを専用commitへ保存・push

## 結果

全50 runが正常終了し、`post-run-audit.json`は5候補とも`ok: true`だった。全runで
`exit_code=0`、`source_unchanged=true`、実行開始時Git clean、Python 3.15.1、
SUMO 1.28.0、FCD終端299.9秒を確認した。固定入力全体SHA-256と300秒prefix SHA-256、
実行ソースhashは、同じseedについて5候補間で一致した。物理衝突は50 run合計0件で、
stderrにTraceback、fatal、atexit errorはなかった。

進入路別速度は、各車両がFCDで最初に現れたlaneにより減少車線`main_0`、継続車線
`main_1`へ分類した。停止は速度0.1 m/s未満、急減速は加速度-3.0 m/s2以下の車両時間、
流出台数はFCDへ現れた固定入力車両のうち最終時刻299.9秒に残っていない台数である。
表は10 seedの平均で、最悪seedだけ速度を併記する。

| lambda | 全車速度 [m/s] | 減少車線速度 [m/s] | 継続車線速度 [m/s] | 停止時間 [s] | 急減速時間 [s] | 流出台数 | Accept率 | 最悪seed（速度） | 衝突 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 0.90 | 5.1116 | **2.8122** | 9.3536 | 2128.7 | 3.05 | **102.6** | 23.68% | 35（3.5929） | 0 |
| 0.93 | 5.0760 | 2.7045 | 9.5428 | 2180.9 | 4.16 | 102.1 | 19.78% | 40（3.9036） | 0 |
| 0.95 | **5.1339** | 2.6969 | 9.8466 | **2117.1** | 3.50 | 102.5 | 16.38% | 36（**4.8332**） | 0 |
| 40/41 | 4.9249 | 2.4084 | 9.8496 | 2674.9 | 3.36 | 99.2 | 11.72% | 35（4.0629） | 0 |
| 80/81 | 4.8779 | 2.3280 | **9.9591** | 2777.8 | 3.33 | 97.5 | 11.26% | 35（3.8255） | 0 |

### seed別全車平均速度

| seed | 0.90 | 0.93 | 0.95 | 40/41 | 80/81 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 33 | 4.9988 | 5.1465 | 5.1952 | 5.1804 | 4.7311 |
| 34 | 5.1236 | 5.1622 | 4.9977 | 4.9102 | 4.8470 |
| 35 | 3.5929 | 4.8900 | 4.9223 | 4.0629 | 3.8255 |
| 36 | 5.2785 | 5.1286 | 4.8332 | 5.1153 | 4.5719 |
| 37 | 5.2379 | 5.2867 | 4.9232 | 5.1634 | 5.2144 |
| 38 | 5.5025 | 5.2830 | 5.2216 | 4.2603 | 4.8943 |
| 39 | 5.1280 | 4.9108 | 5.0955 | 5.0241 | 4.9592 |
| 40 | 5.1962 | 3.9036 | 5.1036 | 4.8542 | 5.3871 |
| 41 | 5.6193 | 5.6193 | 5.6117 | 5.5047 | 5.4693 |
| 42 | 5.4387 | 5.4295 | 5.4347 | 5.1740 | 4.8790 |
| **平均** | **5.1116** | **5.0760** | **5.1339** | **4.9249** | **4.8779** |

### 現行値80/81との差

seed対応percentile bootstrapを200,000回行い、固定乱数seedは`20261116`とした。

| lambda | 80/81との差 [m/s] | 高かったseed | 95% bootstrap区間 [m/s] |
| ---: | ---: | ---: | ---: |
| 0.90 | +0.2338 | 8/10 | [+0.0456, +0.4223] |
| 0.93 | +0.1982 | 8/10 | [-0.2395, +0.5347] |
| 0.95 | **+0.2560** | 8/10 | [+0.0291, +0.5031] |
| 40/41 | +0.0471 | 7/10 | [-0.1888, +0.2586] |

平均速度1位の0.95と2位の0.90の直接差は`+0.0222 m/s`（0.95−0.90）だが、
0.95が高かったのは2/10 seedで、bootstrap 95%区間は`[-0.2088, +0.3522] m/s`だった。
0.95の平均はseed 35の大きな改善に強く影響される一方、0.90は8/10 seedで0.95より
高かった。ただし0.90はseed 35で3.5929 m/sまで低下した。

### 保存監査

`--no-diagnostic-traces`によりruntime、vehicle-state、conflict、negotiation、FCDの専用traceは
生成されず、checkpointも0秒指定で無効だった。一方、prediction-event auditは実装上
常時有効で、50ファイル合計7,348,521,897 byteを生成した。終了後にgzipへ可逆圧縮し、
全ファイルで展開後SHA-256、サイズ、行数を照合した。保存後は2,363,441,404 byte、
5結果ツリー全体は3,566,094,122 byteとなった。最大ファイルは69,313,870 byteで、分割は
不要だった。監査結果は各実験ディレクトリの`compression-audit.json`、
`storage-split-audit.json`、`post-run-audit.json`、`lambda-sweep-summary.json`に保存した。

## 結論

- 確認できたこと: 300秒・既知seedでは、lambdaを80/81から下げた0.90と0.95が、
  全車平均速度をそれぞれ`+0.2338 m/s`、`+0.2560 m/s`改善した。両比較のbootstrap区間は
  0より大きく、物理衝突は全候補で0件だった。
- 確認できなかったこと: 0.95と0.90の差は不明確であり、300秒だけでは長時間渋滞と
  600秒交通性能を判断できない。0.95の平均優位はseed 35の影響が大きい。
- 採否・次の判断: 候補選択規則3に従い、**0.95と0.90の2候補を600秒developmentへ進める**。
  0.93、40/41、80/81は次段階の候補から外す。600秒でも同じseedと固定入力を使い、
  候補を固定した後に未使用seedで最終評価する。
- 既存の研究判断から変わったこと: 理論上の係数比80/81を交通性能上の既定値として
  固定せず、交通性能候補として0.90と0.95を追加確認する。

## 限界・異常

seed 33–42は2026-11-09および2026-11-15に使用済みであり、本実験は独立holdoutではない。
300秒screeningは600秒で現れる長時間渋滞を捉えない可能性があり、候補選択後に600秒確認と
未使用seedによる最終評価を別バッチとして実施する。

また、計画時には軽量runtimeを残して大容量diagnostic traceを切る想定だったが、現行runnerでは
`--no-diagnostic-traces`がruntimeを無効にする一方、prediction-event auditは無効にしない。
そのため実行中の正確なsimulation timeをruntimeから取得できず、screeningとして想定以上の容量を
使用した。ログ方針の修正は本実験中には行わず、別セッションで検討する。
