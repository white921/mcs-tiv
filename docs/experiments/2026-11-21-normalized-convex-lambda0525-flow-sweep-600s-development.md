# 正規化凸結合式 lambda 0.525・交通量比600秒比較

- 台帳ID: `2026-11-21-normalized-convex-lambda0525-flow-sweep-600s-development`
- 状態: `planned`
- 位置づけ: `development`
- 開始日時:
- 終了日時:
- 新規実験ディレクトリ:
  - `results/runs/normalized-convex-lambda0525-eval7-r300-a1000-seeds33-42-600s-20261121/`
  - `results/runs/normalized-convex-lambda0525-eval7-r500-a1000-seeds43-47-600s-20261121/`
  - `results/runs/normalized-convex-lambda0525-eval7-r700-a1000-seeds33-42-600s-20261121/`
  - `results/runs/normalized-convex-lambda0525-eval7-r1200-a1000-seeds33-42-600s-20261121/`
- 既存再利用:
  - `results/runs/normalized-convex-lambda0525-eval7-r1000-a1000-seeds33-42-600s-20261119/`

## 目的

1000/1000 veh/hのdevelopment screeningで固定した正規化凸結合式`lambda=0.525`を、
山下TIVtepとUTFの正常完了結果が既にある300/500/700/1200対1000 veh/hへ追加する。
対照方式の再実行を抑えながら、全車・合流側・本線側の交通性能、安全指標、tail riskが
合流側交通量によってどう変化するかを確認する。

## 仮説と比較対象

- 仮説: `lambda=0.525`は1000/1000以外でも極端な本線側保護へ偏らず、交通量に応じた
  合流側・本線側のトレードオフを示す。
- 基準実験: 各交通量・同一固定入力・同一seedで実行済みの山下TIVtepとUTF。
- 基準から変更するもの: 判断方式だけを固定済み正規化凸結合式`lambda=0.525`へ変更する。
- 固定するもの: Eval.7ネットワーク、交通量、seed、固定入力、600秒、Bus 25%、
  `T_pred=10 s`、`N_max=40`、Python/SUMO、診断条件。
- 採否基準: 全runの完全性と物理衝突を確認した上で、全車平均速度を主指標とし、
  合流側・本線側速度、停止、急減速、流出、未挿入、残留、最悪seed、seed間ばらつき、
  既存対照との差を併記する。
- 結果を見た後に変更しないもの: lambda、交通量、seed、固定入力、duration、Bus比率、
  予測条件、失敗run。結果に応じたlambda再調整やseed差し替えは行わない。

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | 正規化減速伝播提案 `M=(1-lambda)Z_time+lambda Z_follow` |
| lambda | `0.525`（本実験前に固定済み） |
| ケース | Eval.7 |
| 交通量・seed | 300/1000: 33–42、500/1000: 43–47、700/1000: 33–42、1200/1000: 33–42 |
| 既存参照 | 1000/1000: seed 33–42 |
| シミュレーション時間 | 600 s |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/requesting-<flow>-accepting-1000/seed-{seed}.jsonl` |
| Bus比率 | 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 診断ログ | FCD、交渉、車両状態、軌道競合、予測、物理衝突、60秒checkpoint |
| Python / SUMO | 3.15.1 / 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 並列・順序 | 300(10 workers) → 500(5) → 700(10) → 1200(10)。前の比率完了後に次を開始 |

## 既存対照

| 交通量 | seed | 山下TIVtep | UTF |
| --- | --- | --- | --- |
| 300/1000 | 33–42 | `7b48a0048` | `98504479a` |
| 500/1000 | 43–47 | `262b049bb` | `831aa145c` |
| 700/1000 | 33–42 | `b2d7afdc2` | `708f3e985` |
| 1000/1000 | 33–42 | 現行競合領域版 `8297d943a`を主参照、旧版`e68fc3e1c` | `30acd3eda` |
| 1200/1000 | 33–42 | `cb3157005` | `c17f9d89d` |

300/500/700/1200の既存対照は現行競合領域方式導入前の実行ソースであり、現行提案との
差には方式差とsource差が含まれる。まず同一固定入力・seedの既存対照として再利用し、
卒論の主張に用いる交通量を絞った後、必要な対照だけ現行sourceで最小再実行する。

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| 記録branch | `codex/normalized-convex-lambda0525-flow-sweep-600s` |
| 実行ソースcommit | 起動前に確定 |
| 実行開始時dirty | `false`を必須とする |
| 結果branch | 交通量ごとの専用branchを起動前に作成 |
| 結果commit | 完了後に交通量ごとに記録 |
| scheduler | `scripts/run_lambda0525_flow_sweep_20261121.sh` |

## 監視

- systemd unit: 起動時に記録する。
- slowest runが60%未満は30分、60%以上は15分ごとにUbuntuの実状態を確認する。
- 各heartbeatで完了/35、失敗数、現在の交通量、最遅simulation time、実SUMO数、
  runtime停滞、traceback、ディスクを報告する。
- 失敗時は後続交通量を開始せず、不完全結果を保全し、自動再実行しない。

## 完了・完全性確認

- [ ] 新規4バッチ・35 runが正常完了
- [ ] 全runが`exit_code: 0`、`source_unchanged: true`
- [ ] 実行開始時Git clean、source SHA、固定入力SHAを確認
- [ ] lambda以外の条件が既存対照と一致
- [ ] Python/SUMO版、manifest、runner/stdout/stderr、必須artifactを確認
- [ ] 各runに10 checkpoint、FCD終端、診断traceが存在
- [ ] 物理衝突と致命的ログを確認
- [ ] 正常結果だけを交通量ごとの専用commitで保存・push

## 結果

完了後に交通量別・seed別の指標と既存1000/1000、山下TIVtep、UTFを集計する。

## 結論

完了後に記録する。

## 限界・異常

本実験のseedと交通量は既存対照およびlambda選択に使用済みであり、独立holdoutではない。
交通量依存性と既存対照への追加比較を行うdevelopmentとして扱う。source差のある既存対照を
同一sourceの直接比較と表現せず、必要な最小対照再実行は本結果後に別記録で扱う。
