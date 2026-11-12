# Eval.7 lane2削除の等価性確認

- 台帳ID: `2026-11-12-lane2-removal-equivalence`
- 状態: `completed`
- 位置づけ: `diagnostic`
- 開始日: 2026-11-12 JST

## 目的と仮説

Eval.7の合流ネットワークから通常の流入に使われない`main_2`
を削除しても、lane 0/1だけを使う現行Eval.7の制御・交渉・交通指標は
変化しないことを確認する。主要判定・交通指標の完全一致を確認し、
JSONのキー順や集計の浮動小数点丸め差は正規化した意味内容で判定する。

## 変更点

- `merge/threeLane.net.xml`と同一内容のルート直下`threeLane.net.xml`から
  `main_2` lane定義を削除。
- 終端junction `J1`の`incLanes`から`main_2`を削除。
- `main_0` / `main_1`のID、index、中心座標、速度、長さは変更しない。
- 制御コード、固定入力、判定式は変更しない。

## 実行条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.7 |
| 方式 | integrated lambda=2 |
| 交通量 | 合流側1000 / 本線側1000台/時 |
| seed | `6` |
| 入力 | `fixed_inputs/thesis/eval7/seed-6.jsonl` |
| Bus比率 | 25% fixed allocation |
| 時間 | 60秒smoke、600秒完走比較 |
| 診断 | 速度、TIV audit、後続損失audit、prediction events、物理衝突 |
| 診断trace | 完全一致確認を軽量に行うためFCD/replay trace/checkpointは無効 |
| 環境 | macOS arm64、Python 3.15.1、SUMO 1.27.1 |
| 並列 | 削除前後の2 runを同時実行 |

## Gitと結果位置

| 項目 | 値 |
| --- | --- |
| 削除前source | `55ca81999d21d43e8fb0930309d58e34bf9e5f66` |
| 削除後branch | `codex/lane2-removal-equivalence` |
| 削除後source | `6fafc9d2e` |
| 60秒削除前 | `baseline/results/runs/lane2-equivalence-smoke3-baseline-integrated-r1000-a1000-seed6-60s-20261112/` |
| 60秒削除後 | `without-lane2/results/runs/lane2-equivalence-smoke3-without-lane2-integrated-r1000-a1000-seed6-60s-20261112/` |
| 600秒削除前 | `baseline/results/runs/lane2-equivalence-full-baseline-integrated-r1000-a1000-seed6-600s-20261112/` |
| 600秒削除後 | `without-lane2/results/runs/lane2-equivalence-full-without-lane2-integrated-r1000-a1000-seed6-600s-20261112/` |
| 結果commit | 未作成 |

上記の相対パスは比較用worktree親ディレクトリ
`mcs-tiv-lane2-equivalence/`を基準とする。

## 事前の静的確認

- `fixed_inputs/thesis/eval7/`とflow sweepの全固定入力65ファイル・
  18,260車の`depart_lane`はlane 0が7,470車、lane 1が10,790車で、
  lane 2は0車。
- 現行の希望軌道生成はlane 0の車両に限定され、実車線変更命令の
  目標は`laneIndex=1`である。
- SUMO 1.27.1はlane2削除後のネットワークをエラーなく読み込んだ。

## 60秒smoke結果

- 削除前後とも`exit_code: 0`、`source_unchanged: true`。
- 全車平均速度は両方`9.787487194111787 m/s`。
- `evaluation-metrics.json`、`tiv-audit.json`、`deceleration-audit.json`、
  `prediction-events.jsonl`、`physical-collisions.jsonl`、`stdout.log`は
  SHA-256を含め完全一致。
- `stderr.log`の差は20/40/60秒時点の壁時計タイムスタンプだけで、
  速度・車種数・シミュレーション値は一致。
- 物理衝突は両方0。

## 起動前・準備中の失敗

次の試行は比較結果に使わない。失敗ディレクトリはpushしない。

1. 1000/1000・seed 37は、使用したsourceの固定入力path解決が
   `fixed_inputs/thesis/eval7/seed-37.jsonl`を参照し、ファイル不在で
   SUMO起動前に停止した。
2. seed 6の初回起動は、比較用Python環境に`numpy`がなく
   SUMO起動前に停止した。
3. 依存関係導入後の初回起動は、Mac版SUMOの配置に合わせた
   互換`SUMO_HOME`に`sumolib`がなく停止した。

いずれも削除前後で同じ理由で停止し、シミュレーション結果は
生成していない。依存関係と互換pathを固定後、新規ディレクトリで
60秒smokeと600秒完走比較を開始した。

## 600秒結果

- 削除前後とも`exit_code: 0`、`source_unchanged: true`。
- Bus 83台、Car 249台で一致。
- 合流側平均速度は両方`2.1768520333036023 m/s`、本線側は
  `9.853069422125662 m/s`、全車は`4.659534002499595 m/s`で完全一致。
- `tiv-audit.json`と`deceleration-audit.json`はバイト単位で完全一致。
  交渉比較3,491回、Accept 530回、Reject 2,961回の判定系列は同じ。
- `prediction-events.jsonl`は3,491行・302,612,464 byteで両方同じ。
  Python processごとの辞書キー列挙順により86行のテキスト順が異なったが、
  各行をJSONとして読んだ値はすべて同一だった。`sort_keys=True`で正規化した
  SHA-256は両方`923a7e855bee27c73522897dcfbeab94280f2a23374d436095ee0cf684fafc7e`。
- `evaluation-metrics.json`の差は予測誤差集計の2値だけで、最大絶対差
  `5.820766091346741e-11`、最大相対差`2.4235881611609705e-16`。
  これは同一データの加算順による最下位ビットの丸め差で、交通指標や
  判定の差ではない。
- `physical-collisions.jsonl`は両方空で、6,000 stepすべて物理衝突0。
- `stderr.log`は壁時計タイムスタンプを正規化するとSHA-256が
  `a8494ce29af51dd43b480ff519ff08ce760ce693f1b89800b8f832c2556dd397`で一致。

## 限界と結論

lane2削除は、静的にはlane 0/1だけを使う現行Eval.7の到達可能な制御経路を
変更しない。60秒smokeと600秒完走では、車両運動、Accept/Reject、
後続損失、主要交通指標、物理衝突が一致した。したがって、現行モデルで
`main_2`を削除しても、検証したEval.7結果は変わらない。

ただし動的比較はintegrated lambda=2、1000/1000、seed 6の1条件である。
全方式・全seedを再実行した証明ではない。それでも、全固定入力でlane 2使用0、
希望軌道生成がlane 0限定、実車線変更先がlane 1固定であるため、
別方式・別seedだけでlane 2が結果に影響する経路は現行コードに見当たらない。

FCD、vehicle-state trace、checkpointは記録していない。軌跡自体の別artifact比較ではないが、
完走時の交通指標と判定系列は一致している。結果は手元のMac環境での
診断であり、Ubuntu正式結果の再実行や結果コミット、pushは行っていない。
