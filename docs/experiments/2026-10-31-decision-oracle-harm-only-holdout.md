# 後続車害のみ合成・独立holdout

## 状態

`completed`

実装・固定入力・事前登録sourceは`6dc6ddc3cc97ef3b7e66da39d4f5ee4201bf4f2f`。
Ubuntuのclean worktreeで120 testsが成功した。最初のsmokeは誤って
SUMO 1.18.0を指定したためcheckpoint復元時刻が0.0となって停止し、不完全結果を
保全・除外した。正式環境のPython 3.15.1 / SUMO 1.28.0でやり直したsmokeは、
計画ID一致、両分岐exit 0、同一fingerprint、source unchanged、物理衝突0で成功した。

自然走行の交渉場面収集は、山下方式15 runと改善提案方式15 runの全30 runが
正常完了した。全件で`exit_code=0`、`source_unchanged=true`、開始時Git
`6dc6ddc` clean、Python 3.15.1 / SUMO 1.28.0、両方式の固定入力hash一致、
必須artifactあり、物理衝突0、stderr重大異常0を確認した。

事前固定ルールから120イベントplanを作成し、formal corpusを実行中である。

- plan: `/tmp/decision-oracle-harm-holdout-plan-20261031T1448JST-6dc6ddc.json`
- plan SHA-256: `3ff0d0920ec547a321cceade051d00faa0e6f5b41a7c1561dd925238f7e168d1`
- formal output: `results/runs/decision-oracle-harm-holdout-formal-120-20261031T`
- formal source: `6dc6ddc3cc97ef3b7e66da39d4f5ee4201bf4f2f`
- result branch/commit: `codex/decision-oracle-harm-holdout-results@f9306ed86f30ecae6c0781ebb737b789f01703f9`

## 自然走行300秒の結果

5 seed平均では、改善提案の全車平均速度は全ケースで山下方式を下回った。

| ケース | 山下方式 [m/s] | 改善提案lambda=2 [m/s] | 提案−山下 [m/s] |
| --- | ---: | ---: | ---: |
| Eval.3 | 7.1714 | 6.7146 | -0.4568 |
| Eval.5 | 7.4309 | 7.1923 | -0.2386 |
| Eval.7 | 5.1542 | 5.0763 | -0.0780 |

したがって、以下の交渉単位の結果を、そのまま300秒全体の交通性能改善とは解釈しない。

## 最終確認用120場面の結果

全120場面が正常完了した。計画のreceiver/sender/path一致、同一checkpoint
fingerprint、Accept/Reject両分岐の`exit_code=0`、`completed=true`、
`source_unchanged=true`、物理衝突0、runner重大異常0を全件で確認した。
オラクル評価不能は0件だった。

主指標のケース等重み平均後悔量は、山下方式7.0198 mに対し改善提案lambda=2は
2.5404 mで、4.4794 m（63.8%）低かった。山下方式はオラクルtie 7件で選択値を
持たず、113件が採点対象、改善提案は120件すべてが採点対象だった。tieを両方式の
後悔量0として山下方式の分母にも含める感度分析でも、山下6.6679 m、提案2.5404 m
で結論は変わらない。

| ケース | 山下方式 後悔量 [m] | 提案lambda=2 [m] | 山下正解率 | 提案正解率 |
| --- | ---: | ---: | ---: | ---: |
| Eval.3 | 7.3992 | 2.3582 | 81.1% (30/37) | 87.5% (35/40) |
| Eval.5 | 3.1862 | 2.9850 | 81.1% (30/37) | 82.5% (33/40) |
| Eval.7 | 10.4741 | 2.2781 | 82.1% (32/39) | 90.0% (36/40) |
| 全体（参考、イベント集計） | 7.0809 | 2.5404 | 81.4% (92/113) | 86.7% (104/120) |

中央値は両方式とも0 m。p95は山下41.5371 m、提案18.1630 mだった。
自然走行方式別でも提案が低く、山下方式から収集した60場面では
5.3359→3.0419 m、提案方式から収集した60場面では9.0565→2.0389 mだった。

ケース内で自然走行方式×seedをclusterとして100,000回再標本化した
「提案−山下」の95%区間は`[-8.6227, -1.1252] m`で0をまたがなかった
（固定乱数seed 20261031）。オラクルtieを両方式0 mとして含める感度分析でも
`[-7.7770, -0.9642] m`だった。

6つのケース×自然走行方式区分のうち5区分で提案が低かった。唯一、
Eval.5の山下方式由来20場面では山下2.9752 m、提案3.0115 mで、提案が
0.0363 mだけ高かった。この局所的なほぼ同値の反転は限界として残す。

## 結論

未使用seedを結果を見る前に固定した最終確認用データでも、改善提案lambda=2は
交渉直後10秒の判断後悔量を山下方式より有意に小さくした。ケース別と自然走行方式別
の平均でも一貫して低く、後続車への予測害だけを拒否側へ加える改善には、交渉単位の
判断精度に関する再現可能な優位性がある。

一方、300秒自然走行の平均速度は全ケースで悪化した。よって本実験が示すのは
「個々の交渉で承諾／拒否を選ぶ精度」の優位性であり、「システム全体の交通効率」の
優位性ではない。反復交渉、拒否頻度、ネットワーク内の波及により、局所判断の改善が
全体性能へ結び付いていない可能性がある。

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
- [x] 山下／提案の自然走行30 runを正常完了・検証
- [x] 120件planと入力hashを結果を見る前に固定
- [x] 反実仮想120件を正常完了・完全性検証
- [x] 主指標・補助指標・cluster bootstrapを集計
- [x] 正常結果のみ専用commitでpush

