# 交渉単位Accept/Reject反実仮ベンチマーク

- 台帳ID: `2026-10-30-decision-oracle-benchmark`
- 状態: `running`
- 開始日: 2026-10-30
- 実験ディレクトリ: 本実験開始時に`results/runs/`下で固定する

## 目的

同一の交渉直前状態からAcceptとRejectをそれぞれ10秒間強制実行し、
実現した交通結果を正解として山下方式と提案方式の判断妥当性を測る。

## 設計

- 対象: Eval.3、Eval.5、Eval.7。
- 交渉前状態の由来: 山下方式の自然走行と提案方式の自然走行を両方含め、由来別と統合を報告する。
- 一次正解: 要求車、受入車、Accept/Rejectのいずれかで影響を受ける後続車の集合`S`について、`Delta D = sum_i integral(v_i^Accept - v_i^Reject)dt`。
- `Delta D > 0`はAccept、`Delta D < 0`はReject、予め固定した等価許容幅内はtieとする。
- 二次指標: 後続車のみの移動距離差、正規化遅延、停止時間、hard brake、物理衝突。
- 比較方式: 山下方式、到着時間項のみ、提案方式`lambda=0.25/0.5/0.75/1.0`。
- 指標: Accuracy、Regret [m]、fallback/評価不能率。
- 各分岐は同一SUMO/MCS checkpoint、固定入力、RNG、後続方策から開始する。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.3 / Eval.5 / Eval.7 |
| seed | 各ケースの文書化済み固定seedから選択 |
| オラクル時間 | 交渉直後10秒、0.1秒刻み |
| 入力 | コミット済み固定車両入力 |
| Python / SUMO | Ubuntu実行時にmanifestで確定 |
| 実装ブランチ | `codex/decision-oracle-benchmark` |
| 現在の実装基点 | `b5c9d7e`+本設計修正 |

## 現在の確認範囲

- Eval.3・1交渉のAccept/Reject分岐は、同一境界fingerprintと安全性ログを含めて機構確認済み。
- この1件は旧・正規化遅延オラクルの接続smokeであり、本設計の正式結果には含めない。
- 正式コーパスの件数とtie許容幅は、結果を見る前に固定して追記する。

## 完了条件

- [ ] Eval.3/5/7で両由来の状態を取得
- [ ] 全分岐が`exit_code: 0`かつ`source_unchanged: true`
- [ ] Accept/Rejectの境界fingerprint一致
- [ ] 安全性・ログ・artifact完全性を確認
- [ ] 由来別・ケース別・統合のAccuracy/Regretを集計
- [ ] 結果専用commitをpush

## 限界

独立した自由走行結果同士を時刻・車両IDで対応付けない。
各評価単位は1つの交渉前状態から生成した対の分岐とする。
