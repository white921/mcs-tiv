# 減速伝播判断: 第1段階（shadow）

このブランチは、既存のTIVtep判断を変更しない比較モードを追加する。
`MCS_DECELERATION_MODE=shadow` またはT字路ランナーの
`--deceleration-shadow`で有効にできる。通常（OFF）は既存のTIVtepと同じ
経路・判断・速度指示を使う。

## 実装済み

- 速度差を区間積分して、単位mの符号付き距離損失を得る純粋関数。
- `L_reject - L_accept`を明示して比較する関数。
- 物理的に実行可能な既存の`alternative`が生成された後に、受入判断車と
  要求車の承諾/拒否プロファイルを読むread-only shadowフック。
- JSON監査ログ（`MCS_DECELERATION_AUDIT`）と、未対応理由のカウンタ。

`shadow`は実車状態、TraCI、経路、乱数、TIVtepの判定を変更しない。
拒否ケースは両車の交渉前`planned`を維持する。

## 意図的な境界

この第1段階では、受信MCMに含まれる古い送信軌道が10秒の共通評価窓を
満たさない場合、補間・終端等速・速度ゼロで埋めず`unsupported`として
記録する。また、後続車のCAV状態をコピーして既存再計画を動かすアダプタは
まだ実装していない。そのため、直接の2車両だけが10秒間そろう場合にのみ
損失を記録し、後続車列を含む判断への切り替えは行わない。

次段階は、コピーしたCAV状態で既存の候補生成・更新条件・車種制約を使う
予測アダプタを作り、A/B双方の後続車列と共通基準速度列を構成することである。
これは基準の定義、TIVとの併用、同損失時の規則を確認してからactiveモードへ
接続する。

## 隔離スモーク例

```sh
MCS_DECELERATION_AUDIT=/tmp/deceleration-audit.json \
python3 junction/junction_three_agree.py 7 1 400 400 400 \
  --nogui --quiet --duration 600 --stop-time 40 --no-save \
  --bus-allocation paper-random25 --deceleration-shadow
```

`--duration`は600秒のままにし、`--stop-time`だけで短縮する。論文再現用の
出力先や統計CSVと同居させない。
