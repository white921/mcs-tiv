# 実験名

- 台帳ID: `YYYY-MM-DD-short-name`
- 状態: `planned | running | completed | failed | incomplete | superseded`
- 位置づけ: `exploratory | development | confirmatory | reproduction`
- 開始日時:
- 終了日時:
- 実験ディレクトリ: `results/runs/<experiment-id>/`

## 目的

この実験で答えたい問いを1〜3文で書く。

## 仮説と比較対象

- 仮説:
- 基準実験:
- 基準から変更するもの:
- 固定するもの:
- 採否基準:
- 結果を見た後に変更しないもの:

## 条件

| 項目 | 値 |
| --- | --- |
| 方式 | |
| ケース | |
| seed | |
| シミュレーション時間 | |
| 入力 | 固定入力 / 乱数入力 |
| 交通量・Bus比率 | |
| 主要パラメータ | |
| 診断ログ | |
| Python | |
| SUMO | |
| OS・実行機 | |
| 並列数 | |

## 再現用Git情報

| 項目 | 値 |
| --- | --- |
| ブランチ | |
| 実行ソースcommit | |
| 実行開始時dirty | |
| 結果commit | |
| 記録commit | |
| 実行コマンド | |

## 完了・完全性確認

- [ ] バッチmanifestが正常完了
- [ ] 予定した全case/seedが存在
- [ ] 全Runが`exit_code: 0`
- [ ] 全Runが`source_unchanged: true`
- [ ] runner/stdout/stderr/SUMOログを確認
- [ ] 必須artifactとhashを確認
- [ ] 物理衝突と既知警告を確認
- [ ] 結果ディレクトリだけの専用commitをpush

## 結果

### 集約

| ケース | 指標 | 今回 | 基準 | 差 | 解釈 |
| --- | --- | ---: | ---: | ---: | --- |
| | | | | | |

### seed別

| ケース | seed | 主要指標 | 完了 | 異常・警告 |
| --- | ---: | ---: | --- | --- |
| | | | | |

## 結論

- 確認できたこと:
- 確認できなかったこと:
- 採否・次の判断:
- 既存の研究判断から変わったこと:

## 限界・異常

実行時間、環境差、dirty状態、欠損ログ、交絡、警告、外れseed、探索後に選んだ条件などを
記録する。

## 次の作業

1.
