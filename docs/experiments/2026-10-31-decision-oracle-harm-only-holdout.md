# 後続車害のみ合成・独立holdout

## 状態

`running`

実装・固定入力・事前登録sourceは`6dc6ddc3cc97ef3b7e66da39d4f5ee4201bf4f2f`。
Ubuntuのclean worktreeで120 testsが成功した。最初のsmokeは誤って
SUMO 1.18.0を指定したためcheckpoint復元時刻が0.0となって停止し、不完全結果を
保全・除外した。正式環境のPython 3.15.1 / SUMO 1.28.0でやり直したsmokeは、
計画ID一致、両分岐exit 0、同一fingerprint、source unchanged、物理衝突0で成功した。

## 目的

2026-10-30の120イベントをdevelopment corpusとして診断し、到着時間項を
保持したまま後続車影響項の誤った便益信用を除く。改善式と未使用seedを、
holdoutの交渉場面収集や反実仮想結果を見る前に固定し、山下方式に対する
Counterfactual Regretの優位性が独立条件でも再現するか検証する。

## Development診断と固定する改善

- 旧式は `arrival_margin + lambda * signed_loss_margin` だった。
- 旧120件で、予測が「承諾は後続車に有害」とした符号は、実測後続車距離差が
  1 mを超える36件中31件（86.1%）で一致した。一方、「承諾は有利」は
  26件中9件（34.6%）しか一致せず、Eval.7 seed 11の大Regret 2件も
  負の損失差が到着時間上のRejectをAcceptへ反転したことで生じた。
- 改善式を `M = arrival_margin + lambda * max(signed_loss_margin, 0)` とする。
  rawの符号付き損失差は監査に残すが、予測上の便益をAcceptへの加点に使わない。
  後続車への予測害は、到着時間上のAcceptをRejectへ変更できる。
- developmentで事前に比較した係数は `0.5, 1.0, 2.0` の粗い3点とし、
  後続車項が判断に使われる回数とRegretの両方から `lambda=2.0` を固定する。
  同じ120件でのmacro Regretは2.7839 m（山下3.2603 m）だが、これは調整値であり
  優位性の最終根拠には使わない。山下由来では3.2012 m対2.7633 mで悪化しており、
  独立holdoutでのorigin頑健性が未確認である。

## 事前固定holdout条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.3 / Eval.5 / Eval.7 |
| seed | 全ケース共通 `6, 8, 9, 10, 12` |
| duration | 300秒 |
| 自然走行origin | 山下方式、改善提案方式 `lambda=2.0` |
| 時間重み | uniform 10秒 |
| 選択 | 各case × origin × seedで、自然ログ順の先頭4件の一意なforceable policy decision |
| corpus | 3ケース × 2 origin × 5 seed × 4件 = 120件 |
| オラクル | 同一checkpointからAccept/Rejectを強制し、直後10秒の全観測車両の総移動距離を比較 |
| tie | 距離差1 m以下 |
| 主指標 | Eval.3/5/7を等重みしたmean Counterfactual Regret [m] |
| 補助指標 | accuracy、median/p95、invalid率、case/origin別Regret、coverage |

seedは旧developmentのEval.3/5 `1–5`、Eval.7 `1,2,3,7,11`と重ならない。
固定入力はシミュレーション開始前に生成・commitし、山下／提案で同一hashを使う。
選択済みイベントが評価不能でも差し替えない。

## 判定基準

改善提案の主指標が山下方式より小さく、case別・origin別でも一方向に極端な依存が
なく、cluster bootstrap区間が0未満なら優位性の主要根拠とする。主指標だけが小さく
区間が0をまたぐ場合は「公称改善」に限定する。caseまたはoriginで反転する場合は
頑健な優位性を主張しない。

holdout結果を見て式、lambda、seed、イベント選択を変更しない。変更が必要なら
このholdoutを新たなdevelopmentとして明示し、さらに別の未使用条件を固定する。

## 完了条件

- [x] 改善式・固定入力・holdout条件をcommit/push
- [x] Ubuntuで全テストと単一交渉smoke
- [ ] 山下／提案の自然走行30 runを正常完了・検証
- [ ] 120件planと入力hashを結果を見る前に固定
- [ ] 反実仮想120件を正常完了・完全性検証
- [ ] 主指標・補助指標・cluster bootstrapを集計
- [ ] 正常結果のみ専用commitでpush

