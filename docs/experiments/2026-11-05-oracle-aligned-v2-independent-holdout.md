# オラクル整合v2の未使用seed時間層別独立holdout

- 台帳ID: `2026-11-05-oracle-aligned-v2-independent-holdout`
- 状態: `running`
- 位置づけ: `confirmatory independent holdout`
- 実装branch: `codex/oracle-aligned-predictor-v2`
- 判断規則固定commit: `41b2852bde46d63222e878c9bae2cbe2a3c967de`
- 自然走行実行commit: `540c61e033fa793c9f7ed102b8e1cc004d682841`
- 開発実験: [2026-11-05-oracle-aligned-predictor-v2-development.md](2026-11-05-oracle-aligned-predictor-v2-development.md)

## 目的

開発用seed 13–22で得た次の判断規則を一切再調整せず、未使用seed
23–32で確認する。

> 到着時間項がAcceptで、かつ予測`Accept - Reject < -10 m`のときだけ
> Rejectへ上書きする。RejectからAcceptへは上書きしない。

併せて、同じseedの300秒自然走行で局所判断改善とネットワーク全体の走行性能を
分離して評価する。

## 事前固定条件

| 項目 | 条件 |
| --- | --- |
| ケース | Eval.3 / Eval.5 / Eval.7 |
| seed | `23, 24, 25, 26, 27, 28, 29, 30, 31, 32` |
| 自然走行origin | 山下方式、固定済み片方向10 m v2 |
| 自然走行時間 | 300秒 |
| 自然走行並列数 | 10 worker |
| checkpoint間隔 | 30秒 |
| 時間帯 | `[0,100)`, `[100,160)`, `[160,220)`, `[220,290]`秒 |
| 抽出数 | 各case × origin × seed × 時間帯から4交渉 |
| 抽出 | 候補から非復元無作為抽出、固定乱数seed `20261105` |
| 抽出不足 | 別時間帯から補完せず、不足として記録する |
| 評価不能場面 | 事後に別交渉へ差し替えない |
| 予測不能時 | オンライン実装と同じく山下方式の判断へフォールバック |
| 分岐 | 同一判断前checkpointからAccept/Rejectを強制し、直後10秒を0.1秒刻みで記録 |
| 一次cohort | 交渉2台と予測Accept/Reject後続影響車の和集合 |
| 主指標 | 10秒cohort総移動距離のCounterfactual Regret |
| 主比較 | `固定v2 - 到着時間項のみ` |
| 副比較 | `固定v2 - 山下方式` |
| 集約 | case×時間帯等重みmacro平均 |
| 不確実性 | case内のorigin×seed cluster bootstrap 100,000回 |
| bootstrap seed | `20261105` |

seedは`23–27`と`28–32`の2群に分け、4時間帯それぞれに120場面のplanを作る。
全8 plan、960場面、1,920分岐とする。各planはハッシュと件数を固定し、前のplanが
120/120正常終了した場合だけ次を開始する。

## checkpoint作成の事前固定

各選択交渉を0秒から個別再現する重複を避けるため、plan固定後に同一
case×origin×seedの16交渉を1回の0秒からの再生で通過し、各`event_time - 0.1秒`の
SUMO/MCS対checkpointを一括保存する。全60再生を10 workerで実行し、その後の
Accept/Reject 1,920分岐はこの正確checkpointから開始する。

正式corpusの開始前に、Eval.3/5/7×山下/固定v2の6条件で、従来の個別の
0秒からのcaptureと一括checkpointを比較する。対象交渉ID、policy choice、cohort、
Accept/Reject実現指標、oracle、物理衝突が一致しない場合は正式corpusを
開始しない。この効率化はplan、判断規則、分岐時間、cohort、指標を変更しない。

## 確認基準

主比較は、オラクル自体が物理衝突等で無効な場面を除き、予測不能だけを
理由に除外しない。次の両方を満たしたときにのみ独立holdoutでの改善を
確認したとする。

1. `固定v2 - 到着時間項のみ`のmacro平均後悔量が0 m未満。
2. cluster bootstrap 95%区間の上限が0 m未満。

山下方式との比較、case別、時間帯別、origin別、正解率、p95後悔量は副次指標とし、
主比較の結論と入れ替えない。予測方向や10 m閾値は結果確認後も変更しない。

## 300秒自然走行の別評価

山下方式と固定v2を同case×seedで対にし、次を記録する。

- 300秒全体の平均速度、停止時間、到着数、交渉数。
- TraCIが記録した物理衝突数。
- case等重みの対応差とseed対応bootstrap 95%区間。

この自然走行はネットワーク性能の別実験であり、10秒オラクルの局所判断後悔量と
一つの指標に合成しない。

## 追加監査

- 開発用960場面で従来未採点だった43場面の予測不能率がcase、時間帯、
  origin、seedに偏っていないか記録する。正式holdoutではこれらを山下方式で
  フォールバック採点し、予測不能をサンプル除外に使わない。
- 開発用データから、正しいAccept→Reject修正、誤ったAccept→Reject修正、
  失敗するReject→Acceptの代表事例を固定基準で抽出し、車間、速度、後続数、
  予測距離差、実現距離差を可視化する。

## 完了条件

- [ ] 自然走行60 runが正常終了し、全manifestが`exit_code: 0`、`source_unchanged: true`である。
- [ ] 8 planの件数、時間範囲、一意性、SHA-256を結果確認前に固定する。
- [ ] 960場面のAccept/Reject 1,920分岐が正常終了する。
- [ ] 全manifest、境界fingerprint、必須artifact、ログ、物理衝突を監査する。
- [ ] 主比較、不確実性区間、副次指標、300秒別評価を記録する。
- [ ] 未採点43場面と代表誤差事例を監査する。
- [ ] 正常終了結果だけを専用commitでpushする。
