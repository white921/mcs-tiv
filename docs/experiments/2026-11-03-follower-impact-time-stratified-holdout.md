# 後続車影響項の寄与を確認する時間層別独立holdout

- 台帳ID: `2026-11-03-follower-impact-time-stratified-holdout`
- 状態: `running`
- 位置づけ: `confirmatory independent holdout; amended before oracle outcomes`
- 比較対象: 到着時間項のみ、提案方式`lambda=2`、山下方式
- 使用seed: `13, 14, 15, 16, 17, 18, 19, 20, 21, 22`
- 自然走行source: `f56fd4bcfd68330399a9b0e6c870b9126f4447ed`
- 反実仮source: `f8412b944a4dcdaf42df8b556bebbc825572f6f8`
- 予定出力: `results/runs/follower-impact-time-stratified-*`

## 目的

先頭4交渉だけを用いた従来のオラクル計画は、全選択が走行開始後約17〜92秒に偏り、
300秒走行の中盤・後半を評価しなかった。各自然走行を4つの絶対時間帯に分け、各時間帯
から4交渉を抽出して、提案方式の判断後悔量低減が時間帯をまたいで再現するか確認する。
主比較は、到着時間項だけの判断に後続車影響項を加える効果である。

## 変更の時点と独立性

seed 13〜22の山下方式・提案方式の自然走行60 runは完了済みである。旧先頭4件corpusは
相対出力パスの不具合により全件がcapture後、分岐前に停止し、Accept/Rejectの結果は
1件も生成されていない。時間層別への変更はオラクル結果を観測する前に行った。

時間帯境界は、自然走行ログの交渉時刻と候補件数だけを監査して固定した。最初に検討した
`60–120 / 120–180 / 180–240 / 240–290秒`では5つのrun×時間帯で候補が3件しかなく、
全runで4件を確保できなかった。オラクル結果を参照せず、全60 runの各時間帯に4件以上
存在する次の区分へ変更した。

## 事前固定条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.3 / Eval.5 / Eval.7 |
| 自然走行origin | 山下方式、提案方式`lambda=2` |
| seed | 全ケース共通`13–22` |
| 自然走行時間 | 300秒 |
| 時間帯 | `[0,100)`, `[100,160)`, `[160,220)`, `[220,290]`秒 |
| 各時間帯の抽出数 | 各case × origin × seedから4件 |
| 抽出 | 全候補から非復元無作為抽出、固定乱数seed`20261103` |
| 一意性 | `(receiver_id, sender_id, desired_path_id)`の最初の出現だけを候補にする |
| 除外 | Accept/Reject両方を強制できない物理的拒否 |
| 分岐 | 同一checkpointからAccept/Rejectを強制し、直後10秒を0.1秒刻みで再生 |
| 一次cohort | requester、receiver、判断境界で予測された両分岐の後続影響車の和集合 |
| 二次cohort | いずれかの実現分岐で観測された全車両、後続影響車のみ |
| 主指標 | 10秒cohort総移動距離のCounterfactual Regret |
| 主比較 | `提案lambda=2 − 到着時間項のみ` |
| 集約 | caseと時間帯を等重みとするmacro平均 |
| 不確実性 | case内のorigin × seedをclusterとする100,000回bootstrap |

最後の時間帯を290秒までとし、判断後10秒の評価を300秒以内に収める。選択済み場面が
評価不能でも別場面へ差し替えない。

## corpus構成

5 seed群を`13–17`と`18–22`に分け、時間帯ごとに1 planを作る。1 planは
`3ケース × 2 origin × 5 seed × 4件 = 120場面`である。合計は8 plan、960場面、
Accept/Reject 1,920分岐となる。各planを10 workerで逐次実行し、1 planが正常終了した
場合だけ次へ進む。

## plan固定結果

全planは固定乱数seed`20261103`で生成した。各planは120場面、各case 40場面、
各origin 60場面、各case × origin × seed × 時間帯から4場面である。選択IDの重複、
時間範囲、件数を検証した。

| seed群 | 時間帯 [s] | 実際の選択時刻 [s] | plan SHA-256 |
| --- | --- | --- | --- |
| 13–17 | `[0,100)` | 20.4–99.9 | `3da2c236ad273ee73603504046f8051ad7b60cf9918e52f8b6d7cc24f2f3a01c` |
| 13–17 | `[100,160)` | 100.2–159.6 | `c5d6599267f0a0fcc6b80e5dc1a080a652ac8fe49997eeac5a3530fb2b30aa96` |
| 13–17 | `[160,220)` | 160.4–219.5 | `313a3b236f845133d3aefcdf2a3da844521b2e00ccf79feaa0cc4af6509ba59e` |
| 13–17 | `[220,290]` | 220.0–290.0 | `297bc4d5dd8557a12001fac768f525f28b288d94edd7e91070e7e6196306edd3` |
| 18–22 | `[0,100)` | 23.6–99.5 | `232444c4052bd421bda2077077e92da8488ab79acc8f000ff5ba6cd3800ca749` |
| 18–22 | `[100,160)` | 100.1–159.9 | `1de633272a8dd794afd68f9f4edaaa87d96177081761aa99b168505cced9fbc5` |
| 18–22 | `[160,220)` | 160.3–219.1 | `c5ecbd97871bdbe71e20f55df327b88275b83b534a8c8ca915496a18adf18034` |
| 18–22 | `[220,290]` | 220.1–289.8 | `c0d1d07afda5e21ba28319bec36acdaa13705aadd467d4497c55b5ad00870ab6` |

## 実装修正

- plan生成器に時間範囲と固定乱数による非復元抽出を追加する。
- corpus runnerのplan、出力、source関連パスを起動時に絶対化し、子プロセスの作業
  ディレクトリに依存しないようにする。
- 一次cohortを明示的に`actors-followers`として保存し、全観測車両の結果も二次指標に残す。
- 旧先頭4件planと不完全出力は正式結果に混ぜない。

Ubuntuで全123 test成功後、最初の単一場面smokeはPython実行ファイルの絶対化に
`Path.resolve()`を使ったため、venvのsymlinkがsystem Pythonへ解決され、NumPyを
読み込めずcapture開始前に停止した。分岐結果はなく、`source_unchanged: true`だった。
venvのsymlinkを保持する絶対パスへ修正し、同じ条件の新しい出力先で再検証する。

修正後はUbuntuのPython 3.15.1 / SUMO 1.28.0で123 testが再度すべて成功した。
Eval.3 seed 13の単一場面smokeは、capture、Accept、Rejectがすべてexit 0、
`source_unchanged: true`、境界fingerprint一致、物理衝突0、オラクル有効で完了した。
一次cohortはactor 2台と後続影響車6台の計8台、二次の全観測cohortは15台だった。
正式corpusはsmoke出力を持たない別のclean detached worktreeから開始する。

## 正式corpus開始

2026-11-03 05:22:28 JSTにUbuntu上で正式corpusを開始した。8 planごとに
`f8412b94`のclean detached worktreeを1つ割り当て、最初の
`13–17 / [0,100)`から10 workerで逐次実行している。planは一時領域ではなく
`/media/yamada/UbuntuData/ドキュメント/卒論研究/follower-impact-time-stratified-plans/`
へ固定し、開始直前に上表のSHA-256との一致を再確認した。

各corpusの出力先は、対応するworktree内の
`results/runs/follower-impact-time-stratified-<seed群>-t<時間帯>-f8412b94/`
である。corpusがexit 0、`status: completed`、120/120場面完了、失敗0、
`source_unchanged: true`、plan SHA-256一致の場合だけ次のplanへ進む。条件を満たさない
場合は後続planを開始せず停止する。開始後の初回監査では、orchestratorと最初の10場面の
capture processが稼働し、完了済み場面はまだ0件だった。

## capture効率の実行中修正

正式corpusの実行中、各場面の専用checkpointを作るcaptureが、自然走行で保存済みの
60秒間隔checkpointを利用せず、0秒から`event_time - 0.1`秒まで毎回再現していることを
確認した。Accept/Reject分岐自体は同一の専用checkpointから開始しており、問題はその
専用checkpointを作るcaptureの重複にある。

完了済み結果を破棄しないため、`13–17 / [160,220)`corpusは従来runnerで120/120場面まで
完了させる。親orchestratorだけを停止状態にし、実行中のcorpus子processは継続させた。
これにより現在のcorpus完了後に`13–17 / [220,290]`が自動開始されない。

残り5 corpusは、同一case・origin・seedの自然走行が保存した最新の60秒間隔checkpointから
captureを再開し、そこから従来と同じ`event_time - 0.1`秒の専用checkpointを作る。plan、
強制選択、10秒評価、cohort、指標は変更しない。開始前に同一場面を従来captureと
checkpoint再開captureの両方で実行し、判断境界fingerprint、対象交渉ID、Accept/Reject指標、
oracle、policy score、物理衝突が一致することを必須とする。一致しなければ残りcorpusは
開始しない。

## 実行順

1. 時間層別plan生成・cohort・絶対パス処理を実装し、テストする。
2. Ubuntuのclean worktreeで全テストと単一場面smokeを実行する。
3. 8 planを生成し、件数、時間範囲、一意性、SHA-256を記録する。
4. 8 corpusを逐次実行し、各120場面の完全性を確認する。
5. 960場面を統合し、事前固定した主比較と時間帯別結果を解析する。
6. 正常結果だけを専用commitでpushする。

## 完了条件

- [x] 実装テストとUbuntu smokeが成功している。
- [x] 8 planのSHA-256と時間帯が固定されている。
- [ ] 960場面のAccept/Reject両分岐が正常終了している。
- [ ] 全manifestが`source_unchanged: true`で、境界fingerprintが一致している。
- [ ] 必須artifact、物理衝突、runner/stdout/stderrを検証している。
- [ ] 主比較、時間帯別結果、cluster bootstrap区間を記録している。
- [ ] 正常結果だけを専用commitでpushしている。
