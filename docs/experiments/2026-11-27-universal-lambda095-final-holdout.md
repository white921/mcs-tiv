# 3シナリオ共通λ=0.95の最終holdout

- 台帳ID `2026-11-27-universal-lambda095-final-holdout`
- 状態 `preregistered`
- 分類 `formal`

## 目的

合流、T字路、十字路を共通の式とパラメータで扱うため、development
screeningで事前固定した正規化凸結合式の `lambda=0.95`を、選定に使って
いないseedで山下TIVtepと比較する。主指標は各形状の全車平均速度とし、
形状別の対応seed差、3形状の等重み相対差平均、および最悪形状の相対差を
報告する。結果を見てlambdaを再調整しない。

## 条件

| 形状 | 条件（台/時） | 方式 | seed | 本数 |
| --- | --- | --- | --- | ---: |
| Eval.3 T字路 | 500 / 500 / 500 | 提案λ=0.95、山下TIVtep | 23–32 | 20 |
| Eval.5 十字路 | 300 / 300 / 300 / 300 | 提案λ=0.95、山下TIVtep | 23–32 | 20 |
| Eval.7 合流 | 合流1000 / 本線1000 | 提案λ=0.95、山下TIVtep | 23–32 | 20 |

- 各600秒、Bus比率25%固定、Python 3.15.1、SUMO 1.28.0。新規60 run。
- 診断トレースを有効、60秒間隔のcheckpointを保存する。
- 方式以外の条件は対応seed内で一致させる。提案手法は
  `M=(1-lambda)Z_time+lambda Z_follow`、`lambda=0.95`、山下TIVtepは減速伝播を無効にする。
- 固定入力は
  `fixed_inputs/thesis/universal-lambda095-holdout/<condition>/seed-<seed>.jsonl`。
  seed 23–32は既存のλ選定development（Eval.3/5は13–22、Eval.7は33–42）で
  使用していない。
- 実行キューは `condition -> method -> seed`。条件順は
  `Eval.3 500 -> Eval.5 300 -> Eval.7 1000`、方式順は`提案 -> 山下`。
  実行機全体で15 SUMOを上限とする。

## 比較対象と選定の系譜

- 共通λの選定根拠は
  [3シナリオ共通λの高λ域スイープ](2026-11-25-universal-lambda-high-sweep-development.md)。
- 本holdoutでは同じ新規固定入力を使い、現行の同一実行ソースから提案と山下
  TIVtepを実行する。既存の山下結果は旧ソースとの交絡を避けるため再利用しない。
- 実行ソースbranchは `codex/universal-lambda095-holdout`。source commitは起動前に
  本記録へ追記する。

## 実行・保存予定

- 実行機 `sgnlab`。systemd user unit、invocation ID、実行開始時刻は起動時に追記する。
- schedulerは `scripts/run_universal_lambda095_holdout.py`。定数・キュー順・固定入力ハッシュ・
  Python/SUMO版・開始時Git clean・既存SUMO 0をpreflightで検査する。
- 完了後はmanifest、metrics、物理衝突、固定入力hash、診断artifact、checkpoint、
  ログを監査する。診断JSONLとcheckpointは可逆圧縮を復元検査する。
- Gitには実験記録、manifest、compact metrics、比較summary、選定図を保存する。
  大容量生artifactの外部保存先は未決定のため、検証済みコピができるまでUbuntu上に保持する。

## 制約と判定

- 本holdoutはλ=0.95の独立性能評価であり、追加のλ選定には使わない。
- 3形状で山下TIVtepをすべて上回らない場合も、不都合な形状を除外せず結果として保持する。
- 実行結果と結論は未検証。
