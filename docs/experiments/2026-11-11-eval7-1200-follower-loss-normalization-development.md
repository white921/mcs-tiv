# Eval.7・1200/1000の後続車損失正規化development

## 状態

- `running`
- 開始日: 2026-11-11
- 区分: development（既存の1200/1000結果と同じseedを使うため、独立検証ではない）

## 目的と仮説

1200/1000の既存stress testでは、integrated lambda=2が本線側を強く保護する一方、
合流側速度と流出台数を悪化させた。監査では、後続車損失が追従車数にほぼ比例して
増えるため、混雑時に到着時間差を圧倒してRejectへ偏ることを確認した。

このdevelopmentでは、正の後続車害をそのまま合計する現行方式に対し、まず次の2案を
順番に評価する。

1. `sqrt-followers`: 正の後続車害の合計を追従車数の平方根で除す。
2. `mean-followers`: 正の後続車害の合計を追従車数で除し、1台当たり平均にする。

平方根正規化は車群全体への影響を残しつつ密度依存を弱める案、平均化は密度依存を
除く強いアブレーションである。結果を見て係数や条件を変更しない。

その後、既存方式が負の損失差（Acceptの方がRejectより後続車に良いという予測）を
一切判定へ反映しない非対称性を議論した。これは上記2案の実行開始後に選んだ追加の
development案であり、事前規定した独立検証ではない。第3案として次を評価する。

3. `sqrt-followers + half-signed`: 損失差を`m=L_accept-L_reject`として、
   `arrival + lambda * [max(m,0) + 0.5*min(m,0)] / sqrt(n)`を用いる。

負の予測を全面的には信用せず半分だけ加点し、平方根正規化によって追従車数への線形な
依存も抑える。到着不能時のhard gate、lambda=2、予測時間、固定入力は変更しない。

## 固定条件

- case: Eval.7
- 交通量: 合流側1200／本線側1000台/時
- seeds: 33–42（既存stress testと同じ固定入力）
- duration: 600秒
- Bus: 25%、fixed allocation
- Python: 3.15.1
- SUMO: 1.28.0
- integrated loss、lambda=2、half-life=0
- 方式ごとに10 runを同時実行し、3方式は順番に実行する
- マシン全体の同時run上限: 15（本バッチは最大10）
- UTF・Yamashitaは再実行せず、既存の正常終了結果を比較対象にする
- 第3案は先行2方式の完了後に開始し、同時実行しない

## 実行ソース

- source commit: `d76a6aa9777919b99b9ea4613f4c765f14fc9cb6`
- source branch: `codex/eval7-1200-loss-normalization-development`
- 変更内容: 損失正規化モードと、その方式・追従車数・除数・正規化前後損失の監査記録
- 互換性: 既定値`sum`は従来式を変更しない
- 事前検証: ローカルfocused test 61件、sgnlabのPython 3.15.1による全155 testが成功
- smoke: 両方式ともseed 33・30秒で正常終了し、`exit_code: 0`、
  `source_unchanged: true`、source SHA一致、衝突0を確認
- smoke監査: `sqrt-followers`は除数`√n`、`mean-followers`は除数`n`を記録し、
  正規化前後の損失と最終判断余裕がmanifest・監査JSONへ保存された

### sqrt-followers + half-signed追加ソース

- source commit: `c1d6066c1959417d9fe95f04582026c484443127`
- source branch: `codex/eval7-1200-sqrt-half-signed-development`
- 変更内容: 負の損失差の採用率を0–1で指定するCLI・環境変数・監査項目を追加
- 互換性: 既定値`0`は従来の`max(m,0)`を変更しない
- 実行設定: `--deceleration-loss-normalization sqrt-followers`、
  `--deceleration-negative-loss-credit-weight 0.5`
- 事前検証: ローカルfocused test 44件、sgnlabのPython 3.15.1による全159 testが成功
- smoke: seed 33・20秒を正式結果とは別ディレクトリで実行し、`exit_code: 0`、
  `source_unchanged: true`、source SHA一致、衝突0を確認。manifestと監査JSONに
  `sqrt-followers`、負側係数`0.5`、新しい判定式が記録された

## 予定結果ディレクトリとbranch

### sqrt-followers

- result directory: `results/runs/eval7-1200-integrated-lambda2-sqrt-followers-seeds33-42-600s-development-20261111/`
- result branch: `codex/eval7-1200-sqrt-normalization-results`
- result commit: 未作成

### mean-followers

- result directory: `results/runs/eval7-1200-integrated-lambda2-mean-followers-seeds33-42-600s-development-20261111/`
- result branch: `codex/eval7-1200-mean-normalization-results`
- result commit: 未作成

### sqrt-followers + half-signed

- result directory: `results/runs/eval7-1200-integrated-lambda2-sqrt-followers-half-signed-seeds33-42-600s-development-20261111/`
- result branch: `codex/eval7-1200-sqrt-half-signed-results`
- result commit: 未作成

smokeはsource worktree内の別ディレクトリへ保存し、正式結果branchへ含めない。

## 比較と採否

既存1200/1000のintegrated `sum`、UTF alpha=5、Yamashita TIVtepとseed対応で比較する。
追加案はさらに`sqrt-followers`、`mean-followers`ともseed対応で比較する。
全車・合流側・本線側速度、停止時間、急減速時間、流出台数、承諾率、物理衝突に加え、
前半／後半300秒と終了時残留車両・挿入待ちを確認する。平均速度だけで採否を決めず、
合流側改善と本線側負担、処理台数、安全指標の同時改善を重視する。

本バッチは同じseedで設計選択を行うdevelopmentであり、改善が見えても一般的優越性や
独立した効果確認とは解釈しない。採用候補が得られた場合は、別seedまたは別条件での
独立検証を必要とする。

## 結果・監査・結論

実行完了後に追記する。
