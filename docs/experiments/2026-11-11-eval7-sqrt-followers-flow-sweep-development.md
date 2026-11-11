# Eval.7・sqrt-followersの交通量development sweep

## 状態

`running`
- 開始日: 2026-11-11
- 区分: development

## 目的と仮説

1200/1000の後続車損失正規化developmentでは、線形和`sum`を後続車数の
平方根で除す`sqrt-followers`が、合流側速度・停止時間・流出台数を改善しつつ、
本線側と急減速の利点を残す有力候補になった。一方、`mean-followers`は本線側の
利点を大きく失い、`sqrt-followers + half-signed`はseed 39で大渋滞を生じた。

次のdevelopmentとして、負の損失差を加点しない通常の`sqrt-followers`を、
合流側300・500・700・1000台/時で評価する。仮説は、低負荷300・500で既存`sum`の
合流側改善を壊さず、700・1000では本線保護と合流側負担の偏りを弱めることである。

## 固定条件

- case: Eval.7
- 合流側交通量: 300 / 500 / 700 / 1000台/時
- 本線側交通量: 1000台/時
- duration: 600秒
- Bus: 25%、fixed allocation
- integrated loss、lambda=2、half-life=0
- loss normalization: `sqrt-followers`
- negative loss credit weight: `0`
- diagnostic tracesと60秒checkpointを有効化
- Python 3.15.1 / SUMO 1.28.0

## seedと比較対象

| 合流側交通量 | seed | run数 | 既存の対応比較 |
| ---: | --- | ---: | --- |
| 300 | 33–42 | 10 | `sum` / UTF / 山下TIVtep |
| 500 | 43–47 + 6, 8, 9, 10, 12 | 10 | `sum` / UTF / 山下TIVtep |
| 700 | 33–42 | 10 | `sum` / UTF / 山下TIVtep |
| 1000 | 33–42 | 10 | `sum` / UTF / 山下TIVtep |

各交通量で既存対照と同一seed・同一固定入力を使う。合計40 runは交通量順の
共有15-slot queueで実行し、初期15本は300の10本と500の43–47の5本とする。
完了で空いた枠へ500の6, 8, 9, 10, 12、700、1000の順で補充し、マシン全体の
SUMO数が15を超えた場合は失敗とする。

## 実行ソース

- source commit: `7fbf77dbc193183a69ed041446d2a36a6771135c`
- source branch: `codex/eval7-sqrt-flow-sweep-development`
- runner: `scripts/run_thesis_sqrt_flow_queue.py`
- 事前テスト: 共有queue / global-slot / flow-queueのfocused test 10件成功
- 実行環境のPython 3.15.1で全166 test成功
- 300・500・700・1000の各交通量で代表seedの10秒smokeを実行し、4/4 runが
  `exit_code: 0`、`source_unchanged: true`、`sqrt-followers`、負側係数0で完了
- 500の追加開発seed 6は同一source commitで10秒smokeを追加実行し、
  `exit_code: 0`、`source_unchanged: true`で完了
- 実行時は各result worktreeが上記の同一source commitでcleanであること、
  固定入力hash、Python/SUMO version、起動前SUMO数0をpreflightで監査する。
- 初回起動: 2026-11-11 22:06 JST、300の10本 + 500の43–47の5本
- 初回は約5%の時点で500を10本に増やす方針変更のため正常停止。中間出力は
  `20261111T2206-incomplete-35run`として隔離し、正式結果には使用しない。
- 40 runの再開始: 2026-11-11 22:13:37 JST、orchestrator PID `2957086`
- 再開始時にqueue 40 task、各交通量10 task、SUMO 15 process、全4 worktreeの
  source commit一致を確認

## 予定結果ディレクトリ

- `results/runs/eval7-300-1000-integrated-lambda2-sqrt-followers-600s-development-20261111/`
- `results/runs/eval7-500-1000-integrated-lambda2-sqrt-followers-600s-development-20261111/`
- `results/runs/eval7-700-1000-integrated-lambda2-sqrt-followers-600s-development-20261111/`
- `results/runs/eval7-1000-1000-integrated-lambda2-sqrt-followers-600s-development-20261111/`

各結果は交通量ごとの専用result branchに正常完了後のみcommit・pushする。

## 評価と限界

全車・合流側・本線側速度、停止時間、急減速時間、流出台数、承諾率、物理衝突を
seed対応で比較する。300・500では既存`sum`の合流側改善、700・1000では本線側と
合流側のトレードオフを主に評価する。

本バッチは1200/1000の結果で選択した方式を、既存対照と同じ固定入力で交通量展開する
developmentである。ここで良い範囲を選ぶため、一般的優越性や独立した効果確認とは
解釈しない。採用範囲を固定後、未使用seedで全方式を再実行する独立検証が必要である。

500のseed 43–47は既存の600秒holdout入力、seed 6, 8, 9, 10, 12は先行development入力である。
この10本は同質な未使用10-seed holdoutではないため、主分析で5本ずつを層別し、10本合算は
記述的な参考値としてのみ示す。

## 結果・監査・結論

実行完了後に追記する。
