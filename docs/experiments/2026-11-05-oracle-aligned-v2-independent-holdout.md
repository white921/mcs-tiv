# オラクル整合v2の未使用seed時間層別独立holdout

- 台帳ID: `2026-11-05-oracle-aligned-v2-independent-holdout`
- 状態: `completed`
- 位置づけ: `confirmatory independent holdout`
- 実装branch: `codex/oracle-aligned-predictor-v2`
- 判断規則固定commit: `41b2852bde46d63222e878c9bae2cbe2a3c967de`
- 自然走行実行commit: `540c61e033fa793c9f7ed102b8e1cc004d682841`
- 正式corpus実行commit: `e3276b2f74f022f8617bfc01bdda6600768359a0`
- 結果branch: `codex/follower-attribution-time-stratified-results`
- 正式解析結果commit: `77726744e847b2f9cf982a1d881aa9a3be294e6e`
- 自然走行解析結果commit: `807f0e54d`
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
同一0.1秒に複数交渉がある場合は同じ物理checkpointを共有するが、960場面
すべてがcheckpointへ解決できることを完了条件とする。

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

## 実行結果と完全性監査

8 planは結果確認前にcommit `3a645c3b0`で固定した。正確checkpointは60 runを
10 workerで実行し、全manifestの正常終了、`exit_code: 0`、
`source_unchanged: true`、予定960場面からcheckpointへの960参照、950個の
一意な物理checkpointを確認した。結果commitは`2c0cd4666`である。

正確checkpointはsource `5d26269e14c03cc38c1964c79517e1f6a8139736`、正式corpusは
`e3276b2f74f022f8617bfc01bdda6600768359a0`で実行した。後者までの差分は固定入力時に
休眠するRNG状態をfingerprint比較から除外し、このsource互換性overrideをmanifestへ
記録する監査変更である。Eval.3/5/7×山下/v2の6条件で、従来captureと正確checkpointの
対象、判断、cohort、Accept/Reject数値、oracle、衝突が一致した。合格した再検査の
結果commitは`33473bd92`である。

正式corpusは8 planを順次実行し、各120/120、合計960/960場面、1,920/1,920分岐が
正常終了した。全8 corpusについてplan SHA-256、source commit、clean状態、必須artifact、
Accept/Reject境界fingerprint一致、240 runner log、物理衝突ログを監査した。oracle無効は
0件、物理衝突記録は0件、予測不能による山下fallbackは33件だった。

| seed・時間帯 | 結果ディレクトリ | 結果commit |
| --- | --- | --- |
| 23–27・0–100秒 | `results/runs/oracle-aligned-v2-independent-23-27-t0-100-20261106/` | `a4b7e09f9` |
| 23–27・100–160秒 | `results/runs/oracle-aligned-v2-independent-23-27-t100-160-20261106/` | `70b20ca91` |
| 23–27・160–220秒 | `results/runs/oracle-aligned-v2-independent-23-27-t160-220-20261106/` | `a0b638370` |
| 23–27・220–290秒 | `results/runs/oracle-aligned-v2-independent-23-27-t220-290-20261106/` | `9464c178f` |
| 28–32・0–100秒 | `results/runs/oracle-aligned-v2-independent-28-32-t0-100-20261106/` | `0ec02e995` |
| 28–32・100–160秒 | `results/runs/oracle-aligned-v2-independent-28-32-t100-160-20261106/` | `cef52bb2a` |
| 28–32・160–220秒 | `results/runs/oracle-aligned-v2-independent-28-32-t160-220-20261106/` | `2478511f8` |
| 28–32・220–290秒 | `results/runs/oracle-aligned-v2-independent-28-32-t220-290-20261106/` | `96f5b0da3` |

28–32・0–100秒では親SSH runnerが切断したが、120子processはすべて正常終了し、全artifactが
残っていた。`recover_decision_oracle_corpus.py`（source `bfa7af90a`）で集約manifestを
再構成し、他の7 corpusと同じ監査を通した。再実行や場面差し替えはしていない。

## 10秒オラクルholdoutの結果

解析は`results/runs/oracle-aligned-v2-independent-analysis-20261106-r2/`に保存した。
8 corpus、960場面、1,920分岐の監査はerror 0で、case内origin×seed cluster
bootstrapを100,000回実行した。

| 比較 | 共通場面 | 基準macro後悔量 [m] | v2 [m] | v2−基準 [m] | 95%区間 [m] |
| --- | ---: | ---: | ---: | ---: | ---: |
| 到着時間項のみ | 960 | 3.4499 | 2.8218 | -0.6281 | [-1.5135, +0.3341] |
| 山下方式 | 919 | 3.2132 | 2.9346 | -0.2787 | [-1.1091, +0.5118] |

v2は到着時間項よりmacro平均を18.2%下げたが、95%区間の上限が0 m未満という
事前確認基準を満たさなかった。したがって、独立holdoutで一般的な改善を確認したとは
結論しない。正解率は到着時間項86.15%に対してv2 87.19%、p95後悔量は20.3328 mから
15.3106 mへ低下した。

主比較のv2−到着時間項は、case別にEval.3 `-0.2913 m`、Eval.5 `-0.0022 m`、
Eval.7 `-1.5907 m`だった。時間帯別は0–100秒 `-0.7588 m`、100–160秒
`+0.8941 m`、160–220秒 `-1.2770 m`、220–290秒 `-1.3705 m`であり、
100–160秒だけ悪化した。origin別は山下originで`+0.4646 m`、v2 originで
`-1.7207 m`だった。効果がcase、時間帯、状態分布に依存することが、平均改善に対して
不確実性が残った主要な観測結果である。

## 300秒自然走行の別評価

山下方式30 runとv2 30 runはすべて`exit_code: 0`、`source_unchanged: true`で、
同じ固定入力を使用した。解析は
`results/runs/oracle-aligned-v2-natural-analysis-20261105/`へ保存し、同一seedをcase間で
共同resampleする対応bootstrapを100,000回実行した。

| 指標 | v2−山下 | 95%区間 | 解釈 |
| --- | ---: | ---: | --- |
| 平均速度 [m/s] | +0.0216 | [-0.1179, +0.1628] | 明確な差なし |
| 停止率 | +0.0300 | [+0.0052, +0.0523] | v2が悪化 |
| hard brake率 | -0.00033 | [-0.00074, +0.00009] | 明確な差なし |
| 300秒までの退出台数 | +1.1667 | [+0.6000, +1.7333] | v2が改善 |
| 交渉判断数 | -565.6 | [-722.5, -416.3] | v2で減少 |
| 物理衝突episode | 0 | [0, 0] | 両方式0 |

局所10秒後悔量と300秒ネットワーク性能は別のestimandである。v2は退出台数を増やした
一方で停止率を悪化させ、平均速度の改善は確認できなかったため、局所判断の平均改善を
そのままネットワーク全体の効率改善とは解釈しない。

自然走行の生ログは山下方式`2c4436f9c`、v2`07c6d0a6e`の専用commitへ保存した。
95,000,000 byte以上の原本38ファイルはUbuntuの結果checkoutに残し、決定的gzipコピー、
原本と圧縮物のSHA-256、サイズ、復元情報を`large-file-archive/manifest.json`へ記録した。
全38件でgzip展開後SHAが原本SHAと一致し、Gitへ100MB級原本を直接追加していない。

## 失敗出力と限界

- 最初の正確checkpoint同値性検査は、固定入力で使用されないprocess RNG状態まで比較した
  ためfingerprintだけ不一致となった。数値6/6は一致していた。失敗出力はローカル保持し、
  pushしていない。
- 最初の正式解析は先行4 corpusの日付を誤指定し、統計処理前の監査で停止した。失敗出力は
  ローカル保持し、正しい8パスでr2を実行した。
- 10 m閾値と片方向規則は開発seed 13–22から選択している。独立seedで平均差は負になったが、
  信頼区間は0をまたいだため、閾値の再調整や成功主張には用いない。
- 山下方式との共通採点は919/960場面である。主比較は事前登録どおり全960場面で到着時間項と
  比較し、予測不能33場面を山下fallbackで含めた。
- 代表誤差traceと開発時の予測不能43場面の偏りは開発実験記録に保存済みである。正式holdoutの
  33 fallbackは別の未使用seed上の観測であり、両者を同じ標本として合成しない。

## 結論

固定v2は独立holdoutで平均後悔量、正解率、p95後悔量を改善する方向を示し、300秒では
退出台数も増やした。しかし、主比較の95%区間は0を含み、100–160秒、山下origin、停止率では
悪化した。よって本実験の結論は「局所的な改善信号はあるが、事前登録した一般的優越性は
確認できず、効果は状態分布に依存する」である。

## 完了条件

- [x] 自然走行60 runが正常終了し、全manifestが`exit_code: 0`、`source_unchanged: true`である。
- [x] 8 planの件数、時間範囲、一意性、SHA-256を結果確認前に固定する。
- [x] 960場面のAccept/Reject 1,920分岐が正常終了する。
- [x] 全manifest、境界fingerprint、必須artifact、ログ、物理衝突を監査する。
- [x] 主比較、不確実性区間、副次指標、300秒別評価を記録する。
- [x] 未採点43場面と代表誤差事例を監査する。
- [x] 正常終了結果だけを専用commitでpushする。
