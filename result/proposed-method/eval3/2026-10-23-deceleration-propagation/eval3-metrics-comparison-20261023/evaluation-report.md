# Eval.3: TIVtep と減速伝播提案法の比較

Eval.3, alpha=7, inflow=400/400/400, paper-random25, 600 s, paired seeds 1-5

## 平均速度

| 指標 | TIVtep | 提案法 | 差 |
|---|---:|---:|---:|
| 平均速度 [m/s] | 7.5843 | 7.3724 | -0.2120 |

## Seed別

| seed | TIVtep | 提案法 | 差 |
|---:|---:|---:|---:|
| 1 | 7.3867 | 7.3797 | -0.0070 |
| 2 | 7.9353 | 7.2308 | -0.7045 |
| 3 | 7.5424 | 7.6833 | +0.1408 |
| 4 | 7.4352 | 7.5017 | +0.0665 |
| 5 | 7.6220 | 7.0665 | -0.5555 |

## 提案法の10秒予測と実測

選択された承諾または拒否後の実測との比較であり、逆判断の反実仮想ではない。

| 予測窓 | 速度サンプル | 速度MAE [m/s] | 速度RMSE [m/s] | 10秒累積距離の絶対誤差 [m] | 平均後続車数 |
|---:|---:|---:|---:|---:|---:|
| 3743 | 2084236 | 1.8047 | 2.6822 | 42.4529 | 3.5132 |

## 急減速・停止・全車両shortfall

強い減速は加速度 -3.0 m/s² 以下、停止は速度 0.1 m/s 未満。shortfall は自由流13.89 m/sとの差を積分した代理指標。

| 車種 | 指標 | TIVtep | 提案法 |
|---|---|---:|---:|
| 乗用車 | 強い減速時間率 | 0.5356% | 0.6555% |
| 乗用車 | 停止時間率 | 2.3388% | 2.8173% |
| 乗用車 | shortfall 中央値 [m] | 216.40 | 225.73 |
| 乗用車 | shortfall p95 [m] | 454.99 | 489.18 |
| バス | 強い減速時間率 | 0.0743% | 0.0932% |
| バス | 停止時間率 | 1.8433% | 1.8404% |
| バス | shortfall 中央値 [m] | 259.20 | 266.68 |
| バス | shortfall p95 [m] | 507.79 | 551.60 |

## 後続車のshortfall分布

ライブ制御中に前方車を持った車両だけを抽出した分布。反実仮想の距離損失ではない。

| 車種 | 指標 | TIVtep | 提案法 |
|---|---|---:|---:|
| 乗用車 | 車両数 | 742 | 744 |
| 乗用車 | 平均 [m] | 209.43 | 221.71 |
| 乗用車 | 中央値 [m] | 199.41 | 214.03 |
| 乗用車 | p95 [m] | 446.62 | 477.75 |
| バス | 車両数 | 228 | 230 |
| バス | 平均 [m] | 223.13 | 246.59 |
| バス | 中央値 [m] | 221.63 | 236.72 |
| バス | p95 [m] | 459.19 | 486.94 |

## 同一イベントでの判断差（簡易比較）

| 指標 | 件数 |
|---|---:|
| 提案法の承諾 | 2207 |
| 提案法の拒否 | 1133 |
| 同一イベントでTIVtepと一致 | 2278 |
| 同一イベントでTIVtepと不一致 | 1062 |
| TIVtep比較不能 | 468 |

## 限界

- Prediction accuracy is observed only for the proposal-selected action; it is not a counterfactual outcome test.
- The same-event TIV comparison counts decision disagreements, but cannot establish which alternative would have been better without branch replay.
- Free-flow shortfall is a distributional proxy, not the proposal's counterfactual distance-loss definition.
