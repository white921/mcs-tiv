# 論文→SUMO対応表

## 1. シナリオ概要
- 論文名:
  Cooperative Ramp Merging Design and Field Implementation: A Digital Twin Approach Based on Vehicle-to-Cloud Communication
- 再現対象:
  3台協調ランプ合流シナリオ
- 再現段階:
  まずは論文の3台条件をSUMO上で再現する

## 2. 道路構造
| 項目 | 論文での記述 | SUMOでの対応 | 仮置き値 | 備考 |
|---|---|---|---|---|
| 本線車線数 | 図では複数車線だが、再現対象は協調に関与する1車線を抽出して扱えばよさそう | mainline edge/lane数 | 1 lane（再現簡略化案） | 実道路は複数車線。まず3台再現を優先して1車線化する方針が妥当 |
| 流入路車線数 | ランプ1車線として扱われている | ramp edge数 | 1 lane | 図・記述ベース |
| 合流区間長 | merging zone は 89 m | merge部の長さ | 89 m | 論文本文に明記 |
| 本線長 | mainline の track 長は 780 m | edge長 | 780 m | Riverside 実験区間 |
| 流入路長 | ramp 長は 322 m | edge長 | 322 m | 2020年版の同系統論文に明記。TITS本論文でも同一実験系とみられる |
| 制限速度 | 45 mph（約20 m/s） | lane speed | 20 m/s | 両 lane 共通 |

## 3. 車両条件
| 車両ID | 役割 | 初期位置 | 初期速度 | 車線 | ルート | 備考 |
|---|---|---|---|---|---|---|
| veh0 | 本線先行車（MV1） | 未確定 | 未確定 | mainline | mainline straight | 論文中の leader |
| veh1 | 本線後続車（MV2） | 未確定 | 未確定 | mainline | mainline straight | 途中で leader を MV1 から RV に切替 |
| veh2 | 流入車（RV） | 未確定 | 未確定 | ramp | ramp -> mainline merge | advisory speed に従って加速し gap に入る |

## 4. 制御・協調条件
| 項目 | 論文での記述 | SUMOでの対応 | 実装方法 | 備考 |
|---|---|---|---|---|
| 協調対象 | 3台 | 3 vehicle IDs | TraCI等 |  |
| 通信方式 | Vehicle-to-Cloud | 情報共有遅延の模擬 | スクリプト側で表現 |  |
| 制御周期 | HMI update frequency は 3 Hz（333 ms） | step-length / 更新周期 | TraCI で 0.1 s 刻み + 0.333 s ごと advisory 更新など | 論文では通信評価と HMI 更新頻度が結びついている |
| 合流順序 | 初期は MV1 が leader。RV が MV1 に追従し、条件成立後に MV2 が RV を leader として gap を生成 | 車両の優先関係 | leader 切替ロジックを TraCI 側で実装 | 4 stage 構成 |
| 車速調整 | RV は advisory speed に従って加速、MV2 は減速して gap 生成、その後3台が速度収束 | speed control | TraCI setSpeed / setAcceleration 等 | lane change 前に縦方向調整を完了させるのが肝 |
| 車間制御 | consensus-based longitudinal control | gap control | まずベースラインでは簡略化、次に論文ロジックへ | lookup table + consensus algorithm |

## 5. シミュレーション条件
| 項目 | 論文での記述 | SUMOでの対応 | 仮置き値 | 備考 |
|---|---|---|---|---|
| シミュレーション時間 | 典型 trip の説明では 0-20 s で協調縦制御が概ね完了 | begin/end | 0-30 s 程度 | 合流後の安定化確認分を少し持たせる |
| 時間刻み | 本文に直接の明記は未確認 | step-length | 0.1 s（仮） | TraCI 制御には扱いやすい |
| 車両モデル | 実車実験ベースなので SUMO 側は近似モデルが必要 | carFollowModel | Krauss もしくは IDM | まず baseline は Krauss でよい |
| 車線変更モデル | lane change 自体は最終段で1回 | laneChangeModel | default + 必要なら TraCI 強制 | 協調制御前は自動任せでも可 |
| 乱数seed | 明記未確認 | seed | 固定値を設定 | 再現性確保のため固定 |
| GUI使用有無 | 論文は実車。SUMO 再現では確認用 GUI が有効 | sumo / sumo-gui | 初期は sumo-gui | 条件固定後は CLI 実行へ |

## 6. 評価指標
| 指標 | 論文での意味 | SUMOでの取得方法 | 計算方法 | 備考 |
|---|---|---|---|---|
| 合流完了時間 | lane change 完了および3台速度収束の確認 | vehicle position / route | merge edge 進入時刻など | 論文では lane change 前に縦制御完了 |
| 旅行時間 |  | tripinfo.xml |  |  |
| 平均速度 |  | TraCI / output |  |  |
| 加減速の大きさ |  | speed series | 差分計算 |  |
| 最小車間距離 |  | vehicle gap |  |  |
| 安全性指標 | 論文では MV2 の speed variance を安全性代替指標として利用 | TraCI speed series | 速度分散を計算 | baseline 2.163、cooperative 0.705、67.41%減 |

## 7. 再現できたとみなす条件
- 3台が論文と同じ役割で走行する
- 合流の順序が論文と整合する
- 主要指標が論文の傾向と大きく矛盾しない
- 制御なしケースと制御ありケースで差が観測できる

## 8. 不明点
- Table I の厳密な初期位置・初期速度の数値
- 実道路の複数車線構成を SUMO 再現でどこまで簡略化するか
- 2022年TITS論文本体で ramp 長 322 m の明記位置
- 合流完了条件を「lane change 完了」と「速度収束完了」のどちらに置くか

## 9. 論文から拾えた3台条件メモ
- 実験場所は Riverside, California の Columbia Ave. - Iowa Ave. 区間
- mainline は overpass 上、ramp はその下で、互いの視界が遮られる
- observable point は merging point の 100 m 手前
- baseline 用 deactivate point は observable point の 85 m 手前
  - したがって deactivate point は merge point の 185 m 手前
- 3台の典型挙動
  - 0-8 s: RV が加速して本線列へ近づく。MV1/MV2 はほぼ一定速
  - 8 s: MV2 の leader が MV1 から RV に切り替わる
  - 8-15 s: MV2 が減速して RV 用ギャップを生成
  - 15-20 s: RV と MV2 が MV1 の速度へ収束
- 論文の狙いは、lane change 前に3台の縦方向調整をほぼ終えておくこと

---

# セッション引き継ぎメモ

## 現在の到達点
- 研究テーマの進め方は `A: 再現 → 多車両化 → 改良提案` で一旦合意
- 先行研究の再現対象は
  `Cooperative Ramp Merging Design and Field Implementation: A Digital Twin Approach Based on Vehicle-to-Cloud Communication`
- 当面の主目標は `SUMO 上で論文の 3 台シナリオを再現` すること
- Ubuntu 側では `SUMO` 導入済み
- Python は `.venv` 作成済み
- `~/sumo-ramp-merge` に以下の構成を作成済み
  - `net/`
  - `routes/`
  - `cfg/`
  - `scripts/`
  - `outputs/`
- `sumo-gui` で本線2台 + ランプ1台が走る最小シナリオは確認済み
- ただし現状は `SUMO標準挙動` のみで、論文の協調制御はまだ未実装
- 合流車が少し止まる挙動は、SUMO の標準的な安全側挙動として把握済み

## 重要な認識
- 今はまだ `再現環境の土台作り` の段階
- 改良案や多車両化の議論は、まず 3 台再現が通ってから進める
- 現在のシミュレーションも `ベースライン` として価値がある

## 次にやること
1. このメモのうち、論文から次の項目を埋める
   - 道路構造
   - 車両条件
   - 初期位置
   - 初期速度
   - 合流完了条件
2. Ubuntu 側の SUMO ネットワークを、T字ではなく `より合流らしい斜め流入形状` に微調整する
3. 3台シナリオのベースライン条件を固定する
4. その後 `TraCI` を使って論文の協調制御ロジック再現に入る

## 次セッション開始時に確認するもの
- Ubuntu 側の `ramp.nod.xml` と `ramp.edg.xml` の現在内容
- 論文の図・本文から読み取れた 3 台条件
- この `notes.md` にどこまで転記できたか
