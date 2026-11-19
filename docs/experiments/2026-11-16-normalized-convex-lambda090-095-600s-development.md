# 正規化凸結合式 lambda 0.90/0.95・600秒対応比較

- 台帳ID: `2026-11-16-normalized-convex-lambda090-095-600s-development`
- 状態: `completed`
- 位置づけ: `development`
- 開始日時: 2026-11-16 11:33:39 JST
- 終了日時: 2026-11-17 00:23 JST
- 実験ディレクトリ:
  - `results/runs/normalized-convex-lambda090-eval7-r1000-a1000-seeds33-42-600s-20261116/`
  - `results/runs/normalized-convex-lambda095-eval7-r1000-a1000-seeds33-42-600s-20261116/`

## 目的

300秒スイープで上位だった`lambda=0.90`と`lambda=0.95`を、同一seed・同一固定入力の
600秒Eval.7で対応比較する。長時間渋滞での速度、停止、流出量、最悪seed、安全性を確認し、
次の未使用seed最終評価に進めるlambdaを選ぶ。

## 仮説と比較対象

- 仮説: 300秒で平均値が近かった2候補は、600秒の長時間渋滞で車線別トレードオフと最悪seedに差が出る。
- 基準実験: `2026-11-16-normalized-convex-lambda-sweep-300s-development`、
  `2026-11-15-normalized-convex-seeds33-42-600s-development`の`lambda=80/81`。
- 基準から変更するもの: 正規化凸結合式のlambdaのみ。
- 固定するもの: 実行ソース、seed、固定入力、交通量、Bus比率、軌道生成、競合検出、
  交渉プロトコル、`T_pred=10 s`、`N_max=40`、診断trace、60秒checkpoint。
- 採否基準: 20/20正常終了、ソース不変、入力SHA一致、物理衝突0、必須artifactが揃うこと。
- 結果を見た後に変更しないもの: lambda、seed、duration、入力、交通条件、失敗run。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 正規化減速伝播提案のみ |
| ケース | Eval.7 |
| lambda | `0.90`, `0.95` |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl` |
| 交通量・Bus比率 | 要求側1000 / 受入側1000 veh/h、Bus 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 診断ログ | FCD、交渉、車両状態、軌道競合、予測、物理衝突、60秒checkpoint |
| Python | 3.15.1 |
| SUMO | 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列数 | 候補ごと5、機械全体最大10 |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| 元ブランチ | `codex/conflict-region-arrival` |
| 実行ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 実行開始時dirty | `false`を必須とする |
| 結果commit | lambda 0.90: `88f363e5244529e9d2acae3fcbf54bf483cb7a29`、lambda 0.95: `63165a4bdd1b25cf711a946fee89224af7b4935b` |
| 記録commit | 本記録のcommit |
| 実行コマンド | `scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42 --duration 600 --eval7-flows 1000 1000 --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-1000-accepting-1000/seed-{seed}.jsonl --bus-allocation fixed --workers 5 --deceleration-active --deceleration-convex-lambda <lambda> --diagnostic-traces --checkpoint-interval 60` |

## 完了・完全性確認

- [x] 2バッチ・20 runが正常完了
- [x] 全Runが`exit_code: 0`
- [x] 全Runが`source_unchanged: true`
- [x] 実行開始時Git cleanとsource SHAを確認
- [x] 同一seedの固定入力SHAが2候補・300秒sweep・既存600秒比較で一致
- [x] Python/SUMO版、runner/stdout/stderr、必須artifact、終了時刻を確認
- [x] 物理衝突0、致命的ログ0を確認
- [x] 結果ディレクトリとrunner logだけを専用commitでpush

## 結果

### 起動・実行前失敗

2026-11-16 11:33:39 JSTに2候補を同時起動したが、両systemd unitともrunnerの
引数検証で`exit status 2`となった。指定した`--sumo-home`:

`/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128`

には`bin/sumo`はあるが`tools/traci`がなく、runnerが
`--sumo-home must contain bin/sumo and tools/traci`で停止した。SUMOは起動せず、
seed manifest、runner log、実験ディレクトリは生成されていない。このためシミュレーション
runの失敗や条件差は発生していないが、バッチ起動は失敗として扱う。

- lambda 0.90 unit: `mcs-normalized-convex-lambda090-600s-20261116.service`
  - invocation ID: `b52b927e52984d6694c58ae7e2da026a`
- lambda 0.95 unit: `mcs-normalized-convex-lambda095-600s-20261116.service`
  - invocation ID: `6d0cc281ff534b3f8ba05012c5042ada`

正しいSUMO home候補は次であり、`bin/sumo`と`tools/traci`、SUMO 1.28.0、
Python 3.15.1からの`traci`/`sumolib` importを読み取り確認した。この時点では再起動は未実施。

`/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv/.venv-py315-sumo128/lib/python3.15/site-packages/sumo`

### attempt 2

ユーザーの明示承認後、2026-11-16 11:43:23 JSTに上記SUMO homeで同一条件の
attempt 2を起動した。両バッチは`running`、各5 manifest、各5 worker、合計10 SUMOを確認し、
manifestのsource commit、開始時Git clean、lambda 0.90/0.95の一致を確認した。

- lambda 0.90 unit: `mcs-normalized-convex-lambda090-600s-20261116-attempt2.service`
  - invocation ID: `6e1cbd990dd341efaad2162037f261b6`
- lambda 0.95 unit: `mcs-normalized-convex-lambda095-600s-20261116-attempt2.service`
  - invocation ID: `6944c10aa37e49e3bcd84fa219fd1651`
- heartbeat: `mcs-0-90-0-95-600`（30分周期で開始）

### 正常終了と完全性監査

attempt 2はlambda 0.95が2026-11-16 20:09:18 JST、lambda 0.90が
2026-11-16 21:06:35 JSTに正常終了した。20/20 runで`exit_code: 0`、
`source_unchanged: true`、実行開始時Git clean、実行ソースcommit一致を確認した。
全runにrunner/stdout/stderr、trace、FCD、10個の60秒checkpointがあり、FCD終端は
599.9秒だった。致命的ログと物理衝突はいずれも0である。

固定入力は同一seedの2候補間で完全一致した。300秒sweepとは入力全体のSHAが一致し、
既存600秒比較とは300秒までのprefix差が想定どおりで、600秒入力全体が一致した。
両バッチの`post-run-audit.json`は`ok: true`である。

### 主要指標

| lambda | 全車速度 (m/s) | 合流側`main_0` (m/s) | 本線側`main_1` (m/s) | 停止時間 (s) | 急減速時間 (s) | 流出台数 | Accept率 | 物理衝突 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.90 | 4.5829 | 2.2115 | 9.6058 | 5214.93 | 4.26 | 222.0 | 21.82% | 0 |
| 0.95 | 4.4961 | 1.9901 | 10.0513 | 5757.18 | 4.27 | 215.5 | 14.17% | 0 |

合流側速度は2026-11-19の広域スイープ統合時に各runの`stderr.log`を再読みし、
初回記録の`2.1210/1.9091`から`2.2115/1.9901`へ訂正した。他の指標に変更はない。

seed対応の全車平均速度差`lambda 0.90 - lambda 0.95`は平均`+0.0868 m/s`で、
0.90が10 seed中9 seedで高かった。200,000回の対応percentile bootstrap
（乱数seed `20261116`）の95%区間は`[-0.0690, +0.1998] m/s`で0をまたいだ。

| seed | lambda 0.90 (m/s) | lambda 0.95 (m/s) | 0.90 - 0.95 (m/s) |
| ---: | ---: | ---: | ---: |
| 33 | 4.6136 | 4.5506 | +0.0630 |
| 34 | 4.6700 | 4.4559 | +0.2141 |
| 35 | 3.7997 | 4.3202 | -0.5204 |
| 36 | 4.6932 | 4.3559 | +0.3373 |
| 37 | 4.5860 | 4.3616 | +0.2244 |
| 38 | 4.7369 | 4.5740 | +0.1628 |
| 39 | 4.6093 | 4.5256 | +0.0838 |
| 40 | 4.6467 | 4.4352 | +0.2116 |
| 41 | 4.7628 | 4.7317 | +0.0311 |
| 42 | 4.7107 | 4.6505 | +0.0602 |

300秒では0.95が0.90を平均`+0.0222 m/s`上回ったが、600秒では順位が逆転した。
既存lambda 80/81の600秒平均`4.1878 m/s`に対し、0.90は`+0.3951 m/s`
（`+9.43%`）、0.95は`+0.3083 m/s`（`+7.36%`）だった。

### 結果保存

高容量の診断artifactは可逆圧縮し、復元SHA・サイズ・JSONL行数を照合した。
100 MB以上の圧縮ファイルは80 MB単位へ分割し、連結後SHAも照合した。

| lambda | 圧縮前 | 圧縮後 | 分割対象 | 結果commit |
| --- | ---: | ---: | ---: | --- |
| 0.90 | 20,651,437,899 bytes | 2,147,868,794 bytes | 8 files | `88f363e5244529e9d2acae3fcbf54bf483cb7a29` |
| 0.95 | 21,850,307,555 bytes | 2,249,975,405 bytes | 10 files | `63165a4bdd1b25cf711a946fee89224af7b4935b` |

GitHubへの約2 GB packの直接pushはHTTP 500になったため、carrier branchでblobを送信し、
Git Database APIで同一treeを再構築した。remote commitのtree、parent、messageとbranch
SHAを照合し、一時carrier branchは削除した。

## 結論

次の未使用seed最終評価には`lambda=0.90`を進める。600秒では0.90が9/10 seedで高く、
全車・合流側速度、停止時間、流出台数で0.95より良く、急減速と物理衝突は同等だった。
一方、0.95は本線側速度と最悪seedで良く、seed 35では0.90を`0.5204 m/s`上回った。
また対応bootstrap区間は0をまたぐため、0.90の一般的優越性が確立したとは扱わない。
未使用seedでは平均性能に加えてseed 35型のtail riskと本線側トレードオフを確認する。

## 限界・異常

seed 33–42は既実験と候補選択に使用済みであり、本実験は独立holdoutではない。
初回failed unitはSUMO homeの指定誤りによるrunner起動前失敗であり、attempt 2と別unitで
識別した。圧縮・分割された診断artifactは監査済みだが、利用時には同梱の監査情報に
従って復元する必要がある。

