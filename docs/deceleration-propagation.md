# 減速伝播判断: 第1段階（shadow）

このブランチは、承諾・拒否それぞれを10秒先まで予測して比較する
減速伝播判断を追加する。`--deceleration-shadow`は既存TIVtepを変えずに
結果だけ記録し、`--deceleration-active`は評価済みの提案判断を実行する。
通常（OFF）は既存のTIVtepと同じ経路・判断・速度指示を使う。

## 実装済み

- 速度差を区間積分して、単位mの符号付き距離損失を得る純粋関数。
- 距離損失を各車両の交渉時点の許容速度で割り、秒相当へ換算する。
- 判断値は `M = (t_request - t_receiver) + lambda *
  (T_loss_accept - T_loss_reject)`。`M <= 0`なら承諾、`M > 0`なら拒否する。
  初期値は`lambda=1.0`。到着時間項と距離損失換算後の項はともに秒である。
- MCMの終端速度保持（既存`extendPath`と同じ速度側の規則）で、0.1秒刻み
  101点の評価窓を構成する。
- 地図定義の道路ID・車線ID・車線番号・車線内進行位置を車両状態とMCM軌道に保持する。
- 要求車・受入判断車を根として、同一車線上または将来同じ下流回廊へ収束する後続車列を安全車間
  `5 m + 1.5 s × 速度`、加速上限3 m/s²、減速上限5 m/s²で伝播予測する。
  後続車の仮想候補速度は既存CAVと同じ1秒周期で再計画し、SUMOと同じ
  0.1秒刻みで状態遷移・距離損失積分を行う。
- 承諾と拒否で後続車列が異なる場合は、両ケースの後続車IDの和集合を
  共通の比較対象とする。片方で影響を受けない車は、そのケースでは
  MCMの通常計画速度を使う。和集合外の車は両ケースで差がないため比較から相殺される。
- 物理的に実行可能な既存の`alternative`が生成された後に、承諾／拒否の
  2ケースを評価するフック。
- JSON監査ログ（`MCS_DECELERATION_AUDIT`）と、未対応理由のカウンタ。監査ログには
  `accept_follower_ids`、`reject_follower_ids`、`union_follower_ids`も残す。

`shadow`は実車状態、TraCI、経路、乱数、TIVtepの判定を変更しない。
拒否ケースは両車の交渉前`planned`を維持する。

`active`は評価が成功した交渉だけ上記の時間換算判断を使う。要求軌道が
衝突点へ到達不能なら拒否する。許容速度が欠落、非有限、または0以下なら
既存TIVtepへ安全にフォールバック
する。したがって、提案手法を使ったSUMO評価と、影響を隔離した比較評価の
両方を同じランナーで行える。

## 意図的な境界

後続車予測はライブCAVをコピーしてTraCIを仮想実行するのではなく、受信MCM
の軌道を入力とする純粋な運動学アダプタである。従って、交差点内での経路変更・
車線変更・複数の競合を含む厳密な再計画は次の精密化対象となる。現時点の比較
対象は、交渉時点でMCMから検出できる同一車線の後続連鎖と、向きを保って同じ
下流回廊へ収束する合流後続候補である。停止中の向きはMCMのyawを使う。

## 隔離スモーク例

```sh
MCS_DECELERATION_AUDIT=/tmp/deceleration-audit.json \
python3 junction/junction_three_agree.py 7 1 400 400 400 \
  --nogui --quiet --duration 600 --stop-time 40 --no-save \
  --bus-allocation paper-random25 --deceleration-shadow
```

提案判断で走らせる場合は、末尾を`--deceleration-active`に置き換える。

## 再現可能な評価バッチ

T字路Eval.3は、隔離コピー・seedごとの監査ログ・実行manifestを残す
`scripts/run_thesis_batch.py`で実行できる。以下は提案手法の5 seed本実験である。

```sh
python3 scripts/run_thesis_batch.py \
  --sumo-home /path/to/sumo --python python3 \
  --run-name eval3-proposal-600s --cases eval3 --workers 1 \
  --deceleration-active --deceleration-loss-lambda 1
```

各`seed-*`の`manifest.json`に平均速度、`deceleration-audit.json`に各交渉の
損失・判断・後続車数が残る。active実装と標準診断ログはT字路Eval.3、
十字路Eval.5、合流Eval.7に対応している。ケース間の結果は別の実験フォルダーか、
同じバッチ内の別Evalフォルダーとして保存する。

振る舞い調査用の300秒実験では`--diagnostic-traces`を付ける。

```sh
python3 scripts/run_thesis_batch.py \
  --sumo-home /path/to/sumo --python python3 \
  --run-name eval3-proposal-diagnostic-300s \
  --cases eval3 --workers 1 --duration 300 \
  --deceleration-active --diagnostic-traces
```

各`seed-*`に次の追加ログが残る。車両状態は0.1秒ごとの1行に、
その時点で走行中の全車両をまとめるため、300秒で約3,000フレームになる。

- `vehicle-states.jsonl`: 座標、速度、加速度、走行車線、前方車、車間、軌道ID、交渉待ち状態
- `conflicts.jsonl`: 競合2台の実位置、経路、競合点、予測通過時刻、PET、判定理由
- `negotiations.jsonl`: 開始、判断、合意待ち、適用、取消とその理由
- `runtime.jsonl`: SUMOステップ、経路更新、競合判定、車両制御などのステップ別実時間
- `manifest.json`: Gitコミット・ブランチ・dirty状態、Python/SUMO/OS、seed、条件、各ログの生成結果

上記は観測フックのみで、交渉判断、軌道生成、速度制御を変更しない。
論文の最終評価では`--duration 600`を使う。出力は
`results/runs/<実験ID>/<Eval>/seed-<seed>/`へまとまり、論文再現用の別実験や
統計CSVと同居させない。`--run-name`も`--output`も省略した場合は、条件を含む
一意な実験IDを自動生成する。
