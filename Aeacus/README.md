# Aeacus QUIC Timeout Lab

AeacusのQUIC monitorがタイムアウトと判定した後に、その失敗が「DNSキャッシュの古いIP」によるものか、それ以外の一時的・継続的な障害かを分類するための最小実験環境です。

## 収録物

- `Aeacus_論文詳細まとめ.html`: Li et al. (2025) Aeacus論文の日本語解説
- `aeacus_lab/experiment.py`: 実際のQUICハンドシェイク、DNS応答、UDP破棄を使った制御実験
- `tests/test_classification.py`: 原因分類ロジックのテスト
- `results/`: 各試行のJSONとqlog出力

## 実験の考え方

キャッシュ済みIPを`127.0.0.10`、旧サーバを`127.0.0.2`、新サーバを`127.0.0.3`とします。`127.0.0.10`のUDP relayが、シナリオに応じてQUICデータグラムを一時的または永続的に破棄します。

最初のQUIC接続がタイムアウトした場合だけ、次を並行します。

1. 同じIPへ別のQUIC接続を1回開始する
2. DNSに最新Aレコードを問い合わせる
3. DNS応答が変化していれば新IPにも接続する

この同一IP再接続はAeacusの最終機能ではなく、タイムアウト原因を分類するための測定用プローブです。

## シナリオ

| 名前 | 故障の与え方 | 期待する分類 |
| --- | --- | --- |
| `control` | 破棄なし | `initial_success` |
| `transient` | 初回接続中だけUDPを破棄 | `transient_same_ip_recovered` |
| `stale` | 旧IPは常に破棄、DNSは新IPを返す | `stale_ip_likely` |
| `persistent` | 旧IPは常に破棄、DNSも旧IPを返す | `non_dns_or_persistent_unknown` |
| `changed_old_recovers` | DNSは変わるが旧IPも一時破棄後に復旧 | `dns_changed_old_still_usable` |

`changed_old_recovers`は「DNS応答が変わった」だけで旧IPが失敗原因だと断定できないことを確認するシナリオです。

## Dockerで実行

```bash
cd Aeacus
docker compose build
docker compose run --rm experiment
```

個別シナリオだけ実行する場合は、次のように指定します。

```bash
docker compose run --rm experiment --scenario stale --results-dir /app/results
```

各シナリオを20回ずつ実行し、分類回数を集計する例は次の通りです。

```bash
docker compose run --rm experiment \
  --scenario all --repetitions 20 --results-dir /app/results
```

分類ロジックのテストは、entrypointを上書きして実行します。

```bash
docker compose run --rm --entrypoint python experiment \
  -m unittest discover -s tests -v
```

## 出力

`results/summary.json`に全シナリオの結果と分類回数、`results/trials.csv`に試行ごとの集計表、`results/<scenario>/trial_NNN/result.json`に個別結果を保存します。各QUIC接続の`*.qlog.json`には、送受信パケットや損失回復のイベントが入ります。

`elapsed_ms`は接続成功またはタイムアウトを判定するまで、`total_elapsed_ms`はQUICの終了処理を含む試行全体の時間です。

主な分類は次の通りです。

- `stale_ip_likely`: 旧IP失敗、DNS変化、新IP成功
- `transient_same_ip_recovered`: DNSは同じで、同一IPへの新規接続が成功
- `non_dns_or_persistent_unknown`: DNSは同じで、同一IPへの新規接続も失敗
- `dns_changed_old_still_usable`: DNSは変化したが、新旧どちらのIPでも成功

## 制約

- 実験内のDNSはUDP/5353以降を使う小型権威サーバで、実際のLDNSキャッシュ全体は再現していません。
- TLS証明書は実行時に生成する自己署名証明書です。本実験はタイムアウトと接続先変化を対象とするため、クライアントの証明書検証は無効にしています。
- これはAeacusの5GC、UPF、NAT、`preferred_address`を完全再現する実装ではなく、タイムアウト原因分類の検証に範囲を絞ったプロトタイプです。
