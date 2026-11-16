# 正規化凸結合式 lambda 0.90・交通量比600秒比較

- 台帳ID: `2026-11-17-normalized-convex-lambda090-flow-sweep-600s-development`
- 状態: `running`
- 位置づけ: `development`
- 開始日時: 2026-11-17 01:56:51 JST
- 終了日時:
- 実験ディレクトリ:
  - `results/runs/normalized-convex-lambda090-eval7-r300-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda090-eval7-r500-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda090-eval7-r700-a1000-seeds33-42-600s-20261117/`
  - `results/runs/normalized-convex-lambda090-eval7-r1200-a1000-seeds33-42-600s-20261117/`
- 既存参照:
  - `results/runs/normalized-convex-lambda090-eval7-r1000-a1000-seeds33-42-600s-20261116/`

## 目的

1000/1000・600秒で山下TIVtepより高い全車平均速度を示した正規化凸結合式
`lambda=0.90`について、本線側を1000 veh/hに固定し、合流側交通量を
300、500、700、1200 veh/hへ変えたときの交通性能を調べる。既存1000/1000結果と
合わせ、交通量に対する平均速度、進入路別速度、停止、急減速、流出量、承諾率、
最悪seed、安全性の変化を確認する。

## 仮説と比較対象

- 仮説: lambda 0.90の効果は交通量に依存し、低負荷・中負荷・飽和条件で
  合流側と本線側のトレードオフが変化する。
- 比較対象: 各交通量の既存山下TIVtep、UTF、旧integrated lambda=2結果。
- 直接の系列: 同一seed・同一固定入力で実行するlambda 0.90の
  300/500/700/1000/1200対1000。
- 結果を見た後に変更しないもの: lambda、seed、duration、入力、交通量、Bus比率、
  予測時間、後続車上限、失敗run。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.7 |
| 方式 | 正規化減速伝播提案 |
| lambda | `0.90` |
| 合流側 / 本線側 | `300/1000`, `500/1000`, `700/1000`, `1200/1000` veh/h |
| 既存参照 | `1000/1000` veh/h |
| seed | `33, 34, 35, 36, 37, 38, 39, 40, 41, 42` |
| シミュレーション時間 | 600 s |
| Bus比率 | 25% fixed |
| 主要パラメータ | `T_pred=10 s`, `N_max=40` |
| 診断ログ | FCD、交渉、車両状態、軌道競合、予測、物理衝突、60秒checkpoint |
| Python / SUMO | 3.15.1 / 1.28.0 |
| OS・実行機 | Ubuntu `sgnlab` |
| 機械全体の最大並列 | 10 |

## 固定入力

- 300/700/1000は既存のseed 33–42を使用する。
- 500のseed 33–42は同じnested flow-sweep生成規則でPython 3.15.1から追加した。
- 1200のseed 33–42は既存stress testの固定入力と同じファイルを取り込んだ。
- 全入力を`SHA256SUMS`で検証し、生成器の`--check`と固定入力テストを
  UbuntuのPython 3.15.1で通過させる。

## Git情報

| 項目 | 値 |
| --- | --- |
| 元ソースcommit | `e0f36fc461a37e179bf831121ef01b982c5121db` |
| 入力追加commit | `9d56e25d18cafe929c3383ecae116d15d451e481` |
| 実行ソースcommit | `36b50544997eb020e45426b5956e394cb6068742` |
| source変更 | 固定入力、対応交通量・seedの宣言、固定入力テストのみ。評価式は不変 |
| 記録ブランチ | `codex/normalized-convex-lambda090-flow-sweep-600s-development` |
| 結果commit | 完了後に交通量ごとに記録 |

## 起動

2026-11-17 01:56:51 JSTに4バッチを同時起動した。起動後に全unitが`active/running`、
4つのexperiment manifestが`running`、実行ソースcommit一致、開始時Git clean、
lambda 0.90、各交通量、合計10 SUMO processを確認した。

| 交通量 | workers | systemd unit | invocation ID |
| --- | ---: | --- | --- |
| 300/1000 | 2 | `mcs-l090-flow-r300-600s-20261117.service` | `80c4e22e8b584a748a33f8bb6b627114` |
| 500/1000 | 2 | `mcs-l090-flow-r500-600s-20261117.service` | `d1549db060744d67b12527b4bdc5e340` |
| 700/1000 | 3 | `mcs-l090-flow-r700-600s-20261117.service` | `cfb2e6d55a84463b9f07162cf98cf5a5` |
| 1200/1000 | 3 | `mcs-l090-flow-r1200-600s-20261117.service` | `f8289ada74dd418da913e9d6e3ea2e53` |

## 実行コマンド

交通量ごとに次を実行し、`<requesting>`を300、500、700、1200へ置き換える。

```text
scripts/run_thesis_batch.py --cases eval7 --seeds 33 34 35 36 37 38 39 40 41 42
  --duration 600 --eval7-flows <requesting> 1000
  --fixed-input-override fixed_inputs/thesis/eval7-flow-sweep/requesting-<requesting>-accepting-1000/seed-{seed}.jsonl
  --bus-allocation fixed --deceleration-active --deceleration-convex-lambda 0.90
  --diagnostic-traces --checkpoint-interval 60
```

## 完了・完全性確認

- [ ] 4バッチ・40 runが正常完了
- [ ] 全runが`exit_code: 0`、`source_unchanged: true`
- [ ] 実行開始時Git cleanとsource SHAを確認
- [ ] 固定入力SHA、Python/SUMO版、lambda、duration、交通量を確認
- [ ] runner/stdout/stderr、必須artifact、10 checkpoint/run、FCD終端を確認
- [ ] 物理衝突と致命的ログを確認
- [ ] 交通量ごとの結果ディレクトリだけを専用commitでpush

## 結果

完了後に交通量別・seed別の指標と既存1000/1000、山下、UTF、旧integratedの比較を記録する。

## 結論

完了後に記録する。

## 限界

seed 33–42は1000/1000のlambda選択と既存の交通量比較に使用済みであり、本実験は
独立holdoutではない。交通量依存のdevelopmentとして扱い、最終主張は方式・交通量を
固定した後の未使用seed評価に委ねる。

## 後続実験

交通量比較の後、1000/1000でlambdaを横軸、seed平均速度を縦軸とする感度曲線を作る。
既存300秒sweepと600秒のlambda 0.90/0.95を再利用し、不足するlambdaだけを追加する。
探索用seedと最終評価seedを分離し、平均速度だけでなく進入路別速度、停止、流出量、
急減速、最悪seedを同時に確認する。
