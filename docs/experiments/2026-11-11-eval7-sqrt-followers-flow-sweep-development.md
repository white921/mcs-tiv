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
| 500 | 43–47 | 5 | `sum` / UTF / 山下TIVtep |
| 700 | 33–42 | 10 | `sum` / UTF / 山下TIVtep |
| 1000 | 33–42 | 10 | `sum` / UTF / 山下TIVtep |

各交通量で既存対照と同一seed・同一固定入力を使う。合計35 runは交通量順の
共有15-slot queueで実行し、初期15本は300の10本と500の5本とする。完了で空いた枠へ
700、1000を順次補充し、マシン全体のSUMO数が15を超えた場合は失敗とする。

## 実行ソース

- source commit: `4333b3fd401fff6b1e43483be01e63d5613b5ff9`
- source branch: `codex/eval7-sqrt-flow-sweep-development`
- runner: `scripts/run_thesis_sqrt_flow_queue.py`
- 事前テスト: 共有queue / global-slot / flow-queueのfocused test 10件成功
- 実行時は各result worktreeが上記の同一source commitでcleanであること、
  固定入力hash、Python/SUMO version、起動前SUMO数0をpreflightで監査する。

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

## 結果・監査・結論

実行完了後に追記する。
