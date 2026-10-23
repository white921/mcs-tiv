# 減速伝播判断: 第1段階（shadow）

このブランチは、承諾・拒否それぞれを10秒先まで予測して比較する
減速伝播判断を追加する。`--deceleration-shadow`は既存TIVtepを変えずに
結果だけ記録し、`--deceleration-active`は評価済みの提案判断を実行する。
通常（OFF）は既存のTIVtepと同じ経路・判断・速度指示を使う。

## 実装済み

- 速度差を区間積分して、単位mの符号付き距離損失を得る純粋関数。
- `L_reject - L_accept`を明示して比較する関数。
- MCMの終端速度保持（既存`extendPath`と同じ速度側の規則）で、0.1秒刻み
  101点の評価窓を構成する。
- 要求車・受入判断車を根として、同一車線上の後続車列を安全車間
  `5 m + 1.5 s × 速度`、加速上限3 m/s²、減速上限5 m/s²で伝播予測する。
- 物理的に実行可能な既存の`alternative`が生成された後に、承諾／拒否の
  2ケースを評価するフック。
- JSON監査ログ（`MCS_DECELERATION_AUDIT`）と、未対応理由のカウンタ。

`shadow`は実車状態、TraCI、経路、乱数、TIVtepの判定を変更しない。
拒否ケースは両車の交渉前`planned`を維持する。

`active`は評価が成功した交渉だけ提案判断（`L_reject - L_accept >= 0`なら
承諾）を使う。軌道不足などで評価不能なら既存TIVtepへ安全にフォールバック
する。したがって、提案手法を使ったSUMO評価と、影響を隔離した比較評価の
両方を同じランナーで行える。

## 意図的な境界

後続車予測はライブCAVをコピーしてTraCIを仮想実行するのではなく、受信MCM
の軌道を入力とする純粋な運動学アダプタである。従って、交差点内での経路変更・
車線変更・複数の競合を含む厳密な再計画は次の精密化対象となる。現時点の比較
対象は、交渉時点で検出できる同一車線の後続連鎖である。

## 隔離スモーク例

```sh
MCS_DECELERATION_AUDIT=/tmp/deceleration-audit.json \
python3 junction/junction_three_agree.py 7 1 400 400 400 \
  --nogui --quiet --duration 600 --stop-time 40 --no-save \
  --bus-allocation paper-random25 --deceleration-shadow
```

提案判断で走らせる場合は、末尾を`--deceleration-active`に置き換える。

`--duration`は600秒のままにし、`--stop-time`だけで短縮する。論文再現用の
出力先や統計CSVと同居させない。
