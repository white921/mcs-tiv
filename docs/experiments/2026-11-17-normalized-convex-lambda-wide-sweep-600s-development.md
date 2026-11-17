# 正規化凸結合式 lambda 広域600秒スイープ

- 台帳ID: `2026-11-17-normalized-convex-lambda-wide-sweep-600s-development`
- 状態: `running`
- 位置づけ: `development screening`
- 開始日時: 2026-11-17 20:56:23 JST
- 終了日時:
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
| 結果commit | 正常終了後、lambdaごとに専用commitを作成する |

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

## 完了・完全性確認

- [ ] 新規10バッチ・100 runが正常完了
- [ ] 全runが`exit_code: 0`、`source_unchanged: true`
- [ ] 実行開始時Git clean、source SHA、固定入力SHAを確認
- [ ] lambda以外の条件が全候補で一致
- [ ] Python/SUMO版、manifest、runner/stdout/stderr、評価指標を確認
- [ ] 物理衝突と致命的ログを確認
- [ ] lambda別・seed別集計と既存3候補を統合
- [ ] 正常結果だけをlambdaごとの専用commitで保存・push

## 結果

完了後に記録する。

## 限界

seed 33–42は過去の候補選択と比較に使用済みであり、本実験は独立holdoutではない。
本実験はlambda曲線の探索用developmentであり、細密探索後にlambdaを固定し、未使用seedで
最終評価する。新規候補と既存再利用候補で診断ログの有無は異なるが、交通条件、入力、
評価式とシミュレーション挙動は同一である。
