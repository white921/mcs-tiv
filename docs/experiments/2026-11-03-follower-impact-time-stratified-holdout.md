# 後続車影響項の寄与を確認する時間層別独立holdout

- 台帳ID: `2026-11-03-follower-impact-time-stratified-holdout`
- 状態: `running`
- 位置づけ: `confirmatory independent holdout; amended before oracle outcomes`
- 比較対象: 到着時間項のみ、提案方式`lambda=2`、山下方式
- 使用seed: `13, 14, 15, 16, 17, 18, 19, 20, 21, 22`
- 自然走行source: `f56fd4bcfd68330399a9b0e6c870b9126f4447ed`
- 反実仮source: 実装・テスト完了後に固定する
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

## 実行順

1. 時間層別plan生成・cohort・絶対パス処理を実装し、テストする。
2. Ubuntuのclean worktreeで全テストと単一場面smokeを実行する。
3. 8 planを生成し、件数、時間範囲、一意性、SHA-256を記録する。
4. 8 corpusを逐次実行し、各120場面の完全性を確認する。
5. 960場面を統合し、事前固定した主比較と時間帯別結果を解析する。
6. 正常結果だけを専用commitでpushする。

## 完了条件

- [ ] 実装テストとUbuntu smokeが成功している。
- [ ] 8 planのSHA-256と時間帯が固定されている。
- [ ] 960場面のAccept/Reject両分岐が正常終了している。
- [ ] 全manifestが`source_unchanged: true`で、境界fingerprintが一致している。
- [ ] 必須artifact、物理衝突、runner/stdout/stderrを検証している。
- [ ] 主比較、時間帯別結果、cluster bootstrap区間を記録している。
- [ ] 正常結果だけを専用commitでpushしている。
