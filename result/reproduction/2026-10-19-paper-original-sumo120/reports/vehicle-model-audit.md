# 車両モデル適用経路の監査

更新日: 2026-10-19

## 結論

論文Table 5.1のBus性能を再現するには、Busクラス上部の定数だけでなく、
Busが呼び出すFrenet経路計画器の制約も`maxSpeed=11.11`、`maxAccel=1.0`、
`maxDecel=-3.0`へ揃える必要がある。原本実装はこの条件を満たしていない。

## SUMO側

T字路・十字路・合流のroute XMLは、CarとBusの両方を共通の`CAV_0`または`CAV_1`へ追加し、
vTypeを`maxSpeed=20.0`、`accel=3.0`、`decel=5.0`としている。
各CAVクラスは生成時に`traci.vehicle.setSpeedMode(..., 0b100000)`を設定する。
同梱SUMO 1.20.0の説明ではspeed modeのbit 0/1/2がそれぞれsafe speed、maximum acceleration、
maximum decelerationの考慮を表すため、値32ではこれら3ビットがすべて0である。
その後、CAVクラスは計画軌道から求めた速度を`traci.vehicle.setSpeed`で直接設定する。

したがって、この実装で車種別性能を実際に決める主経路はSUMO vTypeではなく、
CAVクラスとFrenet経路計画器である。

## 原本実装の不一致

| 場面 | Busクラス定数 | Busが実際にimportする計画器 | 計画器制約 | 論文一致 |
| --- | --- | --- | --- | --- |
| T字路 | 11.11 / 1.5 / -3.0 | `frenet_three_junction` | 13.89 / 3.0 / -5.0 | 不一致 |
| 十字路 | 11.11 / 1.0 / -3.0 | `frenet_four_junction` | 13.89 / 3.0 / -5.0 | 不一致 |
| 合流 | 11.11 / 1.5 / -3.0 | `frenet_merge_car` | 13.89 / 3.0 / -5.0 | 不一致 |

原本には`frenet_merge_bus.py`も存在するが、Busクラスからimportされていない。
また、その未使用ファイルの制約は11.11 / 1.5 / -3.0で、加速度が論文値と異なる。

経路計画器の制約は、少なくとも次へ直接使われる。

- 自由走行・追従・譲歩軌道の速度目標とコスト
- 軌道候補の最大速度・最大加速度・最大減速度検査
- 緊急停止軌道の停止時間、位置、速度、加速度

## 論文条件版

`sumo-mcs-11-paper-model/`では次を行う。

1. T字路・十字路の原本計画器をBus用として分離する。
2. 合流Busクラスを原本同梱の`frenet_merge_bus.py`へ接続する。
3. 3つのBus計画器を11.11 / 1.0 / -3.0へ統一する。
4. T字路・合流Busクラスの`maxAccel`も1.0へ変更する。
5. Busを含むEval.3、Eval.5、Eval.7を各5 seed再実行する。

Busを含まないEval.4とEval.6は原本実装版を論文条件版でも採用できる。
変更の機械可読な差分は`paper-vehicle-model.diff`に保存する。
