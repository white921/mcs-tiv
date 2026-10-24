# 再現実験結果

`mcs-tiv`と引き継ぎコードを使って実行した再現・監査結果を時系列で保存する。

| ディレクトリ | 主な内容 | 注意 |
| --- | --- | --- |
| `2026-10-02-archived-reconstruction/` | 初期のT字路再現とスモーク実行 | 現在の正本実装より前のアーカイブ |
| `2026-10-17-multi-eval/` | T字路、十字路Eval.4/5、合流Eval.6/7のseed別CSVとログ | FCDとソース複製は元保存先に残した |
| `2026-10-19-paper-original-sumo120/` | 引き継ぎ原本をSUMO 1.20.0で実行した25ケース、集計、環境監査 | `original-results/`が25 seed分の結果。`paper-model-results/`は未完了 |
| `2026-10-20-baseline-original/` | 原本ALWケースの隔離実行 | manifestと比較結果を保存 |
| `2026-10-20-thesis-zotero/` | 論文条件のスモーク、更新間隔比較、監査 | 完走ケースと短時間ケースを区別する |
| `2026-10-21-thesis-zotero/` | SUMO 1.17.0によるEval.3 TIVtep seed 2の600秒完走 | 単一seedであり5-seed平均ではない |

## 元保存先

- `/Users/shige/Documents/重野研/卒論研究/アーカイブ/sumo-mcs-reconstruction-2026-10-02/outputs`
- `/Users/shige/Documents/重野研/卒論研究/再現実験/2026-10-17-*`
- `/Users/shige/Documents/重野研/卒論研究/再現実験/2026-10-19-paper-original-sumo120`
- `/Users/shige/Documents/重野研/卒論研究/再現実験/2026-10-20-*`
- `/Users/shige/Documents/重野研/卒論研究/再現実験/2026-10-21-thesis-zotero`

## 集約時の除外

Git内の重複を避けるため、各seedに複製されていたソースツリー、仮想環境、キャッシュ、生成XML、FCD `sumoStat.xml`はコピーしていない。必要な実行条件はmanifest、監査JSON、レポート、ログ、CSVから確認し、FCDが必要な再解析では上記の元保存先を使う。

`2026-10-20-thesis-zotero`の`smoke-t3-seed2-v2`と`v3`では、終了処理の例外により元の`tiv-audit.json`が途中で切れていた。この2ファイルは有効なJSONではないため集約対象から除外し、失敗内容を確認できる`stderr.log`を残している。
