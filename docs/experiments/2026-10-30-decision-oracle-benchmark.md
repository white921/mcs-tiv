# 交渉単位Accept/Reject反実仮ベンチマーク

- 台帳ID: `2026-10-30-decision-oracle-benchmark`
- 状態: `completed`
- 開始日: 2026-10-30
- 完了日: 2026-10-31
- 実験ディレクトリ:
  `results/runs/decision-oracle-formal-120-events-v2-20261031T`
- 交渉収集ディレクトリ:
  `decision-oracle-discovery-yamashita-300s-all-seeds-20261031T`、
  `decision-oracle-discovery-proposal-lambda1-300s-all-seeds-20261031T`

## 目的

同一の交渉直前状態からAcceptとRejectをそれぞれ10秒間強制実行し、
実現した交通結果を正解として山下方式と提案方式の判断妥当性を測る。

## 設計

- 対象: Eval.3、Eval.5、Eval.7。
- 交渉前状態の由来: 山下方式の自然走行と提案方式の自然走行を両方含め、由来別と統合を報告する。
- 一次正解: 要求車、受入車、Accept/Rejectのいずれかで影響を受ける後続車の集合`S`について、`Delta D = sum_i integral(v_i^Accept - v_i^Reject)dt`。
- `Delta D > 1.0 m`はAccept、`Delta D < -1.0 m`はReject、`|Delta D| <= 1.0 m`はtieとする。
- 二次指標: 後続車のみの移動距離差、正規化遅延、停止時間、hard brake、物理衝突。
- 比較方式: 山下方式、到着時間項のみ、提案方式`lambda=0.25/0.5/0.75/1.0`。
- 指標: Accuracy、Regret [m]、fallback/評価不能率。
- 各分岐は同一SUMO/MCS checkpoint、固定入力、RNG、後続方策から開始する。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.3 / Eval.5 / Eval.7 |
| seed | Eval.3/5=`1,2,3,4,5`、Eval.7=`1,2,3,7,11` |
| オラクル時間 | 交渉直後10秒、0.1秒刻み |
| サンプル数 | 3ケース × 2由来 × 5 seed × 各4件の強制可能な方策判断 = 120件（代替経路なしの物理的Rejectは除外） |
| 入力 | コミット済み固定車両入力 |
| Python / SUMO | Python 3.15.1 / SUMO 1.28.0 |
| 実装ブランチ | `codex/decision-oracle-benchmark` |
| 自然走行source | `f5c417589bee0f6ba2a808c587ca876b7aa517a3` |
| 反実仮評価source | `0c337d2cd1cc01ffb4d3e286ca2a228d74cc19c1` |
| plan SHA-256 | `b9a6f438beb32865c6e0ce31f9471506a027d1a1b574165e84991428f3aa1753` |

## 実行と完全性

- 各自然走行の決定論的なログ順から、同じ`(receiver_id, sender_id, desired_path_id)`交渉で0.1秒ごとに繰り返されるdecisionを1件にまとめ、結果を見る前に先頭4交渉を固定する。選択済みイベントが評価不能でも別イベントへ差し替えず、評価不能率へ含める。
- 一次集計はケースごと・由来ごとの平均Regretを報告し、ケースを等重みとしたmacro平均Regretを主指標にする。Accuracy、median/p95 Regret、評価不能率は補助指標とする。
- 主コホートはAccept／Rejectのいずれかで10秒窓内に観測された全車両の和集合とする。影響を受けない車両は両分岐で同量となり差分から相殺される。提案方式が予測した後続車集合は補助診断だけに用いる。
- 交渉収集30 runは全件`exit_code: 0`、`source_unchanged: true`、
  開始時Git clean。両由来の固定入力hashは一致し、物理衝突と
  stderr重大異常は0件。
- 正式120件は全件でplanの車両／path ID一致、Accept/Rejectの
  境界fingerprint一致、両分岐`exit_code: 0`、`completed: true`、
  `source_unchanged: true`、物理衝突0件を確認。オラクル無効は0/120。
- 最初の正式runは、planの`receiver_id/sender_id`を境界schemaの
  `receiver/sender`で照合していない検証コードの不具合で停止した。
  不完全結果は正式集計とcommitに含めず、`0c337d2`で修正、
  117 testsと単一交渉smoke後に同一plan・同一条件で再実行した。

## 結果

### 主指標: ケース等重み平均Regret [m]

| 方式 | macro Regret | coverage |
| --- | ---: | ---: |
| 山下方式 | 3.2603 | 117/120 |
| 到着時間項のみ | 3.0695 | 119/120 |
| 提案 `lambda=0.25` | **3.0617** | 119/120 |
| 提案 `lambda=0.5` | **3.0617** | 119/120 |
| 提案 `lambda=0.75` | 4.3418 | 119/120 |
| 提案 `lambda=1.0` | 4.3418 | 119/120 |

`lambda=0.25/0.5`の公称macro Regretは山下方式より0.1986 m
（6.1%）小さい。共通にscore可能な116件の対応比較では差は
-0.1526 mで、13件の不一致の内訳は提案勝ち5、山下勝ち4、tie 4。
探索的なcase内origin/seed cluster bootstrapの95%区間は
[-2.0935, 1.7188] mで0をまたぐ。

### ケース別平均Regret [m]

| ケース | 山下 | 提案 `lambda=0.25/0.5` | 提案 `lambda=1.0` |
| --- | ---: | ---: | ---: |
| Eval.3 | 2.7518 | **2.6142** | 2.6142 |
| Eval.5 | **1.7789** | 1.7933 | **1.7789** |
| Eval.7 | 5.2503 | **4.7777** | 8.6323 |

### origin別平均Regret [m]

| origin | 山下 | 提案 `lambda=0.25/0.5` | 提案 `lambda=1.0` |
| --- | ---: | ---: | ---: |
| 山下自然走行 | **2.7633** | 2.8926 | 4.4028 |
| 提案自然走行 | 3.8274 | **3.2492** | 4.3245 |

`lambda=0.25`と到着時間項の判断不一致は119件中1件だけで、
そのオラクルもtieだった。したがって、山下方式に対する公称差の
大部分は到着時間評価の差であり、後続車影響項自体の優位性は
この結果からは確立できない。`lambda=1.0`はEval.7の2組の
大きな誤判断でRegretが増えた。

## 結論

`lambda=0.25/0.5`に山下方式より小さい公称macro Regretは見られたが、
case/originをまたぐ頑健性と不確実性まで考慮すると、提案の後続車影響項の
優位性を主張できる結果ではない。今後この120件を用いて改善する場合、
これをdevelopment corpusとし、未使用seedの独立holdoutで最終評価する。

## 完了条件

- [x] Eval.3/5/7で両由来の状態を取得
- [x] 全分岐が`exit_code: 0`かつ`source_unchanged: true`
- [x] Accept/Rejectの境界fingerprint一致
- [x] 安全性・ログ・artifact完全性を確認
- [x] 由来別・ケース別・統合のAccuracy/Regretを集計
- [ ] 結果専用commitをpush

## 限界

独立した自由走行結果同士を時刻・車両IDで対応付けない。
各評価単位は1つの交渉前状態から生成した対の分岐とする。
1 seed/origin/caseから4交渉を取るため観測は完全に独立ではない。
オラクルは120/120有効だが、山下判断は3件、提案・到着時間判断は
1件で必要な予測値がなく、方策別coverageが異なる。bootstrap区間は
事前登録指標ではなく探索的診断である。
