# Eval.7・1200/1000の後続車損失正規化development

## 状態

- `completed`
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
- 1方式につき最大10 run。方式間はマシン全体の空き枠を共有する
- マシン全体の同時run上限: 15（本バッチは最大10）
- UTF・Yamashitaは再実行せず、既存の正常終了結果を比較対象にする
- 第3案は先行方式の未使用枠へ投入し、マシン全体で常に最大15 runを守る

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

- source commit: `ef191fa75664b9ec03bd68afb99f48167de7be11`
- source branch: `codex/eval7-1200-sqrt-half-signed-development`
- 変更内容: 負の損失差の採用率を0–1で指定するCLI・環境変数・監査項目と、
  マシン全体の空き枠へ待機seedを投入するwork-conservingラッパーを追加
- 互換性: 既定値`0`は従来の`max(m,0)`を変更しない
- 実行設定: `--deceleration-loss-normalization sqrt-followers`、
  `--deceleration-negative-loss-credit-weight 0.5`
- 事前検証: ローカルfocused test 47件、sgnlabのPython 3.15.1による全162 testが成功
- smoke: seed 33・20秒を正式結果とは別ディレクトリで実行し、`exit_code: 0`、
  `source_unchanged: true`、source SHA一致、衝突0を確認。manifestと監査JSONに
  `sqrt-followers`、負側係数`0.5`、新しい判定式が記録された
- global-slot smoke: seed 33・5秒が`exit_code: 0`、`source_unchanged: true`で完了。
  slot予約・解放・マシン全体のSUMO数を専用JSONLへ記録し、slot超過なしを確認
- 正式開始: 2026-11-11 13:34 JST。先行mean-followersが7本実行中だったため、
  第3案の先頭8本を投入してマシン全体を15本に保った。以後も空き枠へ待機seedを投入する

## 予定結果ディレクトリとbranch

### sqrt-followers

- result directory: `results/runs/eval7-1200-integrated-lambda2-sqrt-followers-seeds33-42-600s-development-20261111/`
- result branch: `codex/eval7-1200-sqrt-normalization-results`
- result commit: `05ce55be9c7918ba632c0a4258ad4fd77a5f639e`
- original dedicated commit / tree: `e78c9c67237489b30ae96e88ded621e86f6ae07d` / `42590dd6c192d8cddc2ba3bf38ff6e9ef407e9ee`

### mean-followers

- result directory: `results/runs/eval7-1200-integrated-lambda2-mean-followers-seeds33-42-600s-development-20261111/`
- result branch: `codex/eval7-1200-mean-normalization-results`
- result commit: `2c23c74e4f13f16cc03ff296d4d8fe6f707d8c2d`
- original dedicated commit / tree: `d40261b03005bdfdd1d5ec1bacac9a14084ac66d` / `4fd40cd944360d9fbd8675b1ea769b1588a3b2d6`

### sqrt-followers + half-signed

- result directory: `results/runs/eval7-1200-integrated-lambda2-sqrt-followers-half-signed-seeds33-42-600s-development-20261111/`
- result branch: `codex/eval7-1200-sqrt-half-signed-results`
- result commit: `772d14988a2f9ec917d9f0728d6db1d25df2126e`
- original dedicated commit / tree: `ed30ae040bef69adb66c4aa64c580a3d39dcfd5c` / `c58e289e3ec86c29febd7409bf37b6494e65234c`

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

## 結果

### 10 seed平均

| 方式 | 全車速度 [m/s] | 合流側速度 [m/s] | 本線側速度 [m/s] | 停止時間 [s] | 急減速時間 [s] | 流出台数 | 未挿入 | 残留 | 承諾率 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 従来sum | 4.0418 | 1.4994 | **9.9349** | 7997.61 | 4.75 | 200.3 | 128.1 | 37.6 | 17.68% |
| UTF | 4.0960 | 2.1502 | 7.6782 | 6265.70 | 9.72 | 217.7 | 106.5 | 41.8 | — |
| 山下 | 4.3448 | 2.2464 | 8.6169 | 4971.47 | 9.24 | 221.5 | 102.5 | 42.0 | 50.26% |
| sqrt-followers | **4.3834** | 2.0966 | 9.1021 | 5217.05 | 4.66 | 220.8 | 107.8 | **37.4** | 21.22% |
| mean-followers | 4.3584 | **2.5658** | 7.4108 | **3935.56** | 8.58 | **232.7** | **91.4** | 41.9 | **61.31%** |
| sqrt + half-signed | 3.9986 | 1.9161 | 8.3208 | 7654.35 | **4.16** | 200.1 | 126.2 | 39.7 | 26.24% |

全方式・全seedで物理衝突は0だった。これは本条件で観測されなかったことだけを示す。

### 20万回の対応percentile bootstrap

主要な対応差は次の通り。区間は95% percentile intervalである。

| 比較 | 全車速度差 [m/s] | 合流側速度差 [m/s] | 本線側速度差 [m/s] | 流出台数差 |
| --- | ---: | ---: | ---: | ---: |
| sqrt − sum | +0.3416 `[+0.0714,+0.6198]` | +0.5972 `[+0.2748,+0.9533]` | -0.8329 `[-1.3194,-0.2925]` | +20.5 `[+9.5,+33.1]` |
| sqrt − UTF | +0.2874 `[-0.0467,+0.6038]` | -0.0536 `[-0.5084,+0.4387]` | +1.4239 `[+0.4719,+2.2493]` | +3.1 `[-11.9,+19.2]` |
| sqrt − 山下 | +0.0386 `[-0.2197,+0.2804]` | -0.1498 `[-0.4962,+0.2206]` | +0.4851 `[-0.2572,+1.1209]` | -0.7 `[-12.3,+11.8]` |
| mean − sum | +0.3166 `[+0.0346,+0.5786]` | +1.0665 `[+0.6833,+1.4440]` | -2.5242 `[-3.0335,-1.9729]` | +32.4 `[+19.9,+45.1]` |
| mean − UTF | +0.2624 `[+0.0395,+0.4872]` | +0.4156 `[+0.0398,+0.8607]` | -0.2674 `[-1.2586,+0.4917]` | +15.0 `[+3.7,+29.2]` |
| mean − 山下 | +0.0136 `[-0.2531,+0.2544]` | +0.3194 `[+0.0012,+0.6386]` | -1.2062 `[-1.7622,-0.6962]` | +11.2 `[+0.5,+22.3]` |
| half-signed − sum | -0.0432 `[-0.9378,+0.5715]` | +0.4167 `[-0.1072,+0.8982]` | -1.6141 `[-3.2067,-0.5342]` | -0.2 `[-47.0,+30.7]` |

mean-followersは従来sumより全車・合流側速度、停止時間、流出台数を改善した一方、
本線側速度を2.52 m/s低下させ、急減速時間を3.83秒増やした。sqrt-followersは
本線側低下を0.83 m/sに抑えつつ、従来sumより全車・合流側速度と流出台数を改善した。
したがって正規化はReject偏重を弱めたが、平均化は本線保護を弱め過ぎる。

half-signedはseed 39で全車速度0.5369 m/s、流出台数19、未挿入289、停止時間
28628.8秒、承諾率70.30%となり、両流入が崩壊した。他9 seedの全車速度は
4.08–4.70 m/sだったため、平均とbootstrap区間はこの単一seedの強い影響を受ける。
負側0.5の採用は承諾率を上げたが、過剰承諾による破局的状態を防げず、採用候補から外す。

### 前半・後半300秒

| 方式 | 期間 | 全車速度 | 合流側速度 | 本線側速度 | 停止時間 | 急減速時間 | 流出台数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sqrt | 0–300秒 | 4.8054 | 2.6816 | 8.7220 | 2133.05 | 3.64 | 103.1 |
| sqrt | 300–600秒 | 4.0314 | 1.6303 | 9.5932 | 3051.34 | 1.52 | 117.7 |
| mean | 0–300秒 | 4.7588 | 3.0607 | 7.4739 | 1619.93 | 5.86 | 106.8 |
| mean | 300–600秒 | 4.0364 | 2.1729 | 7.4441 | 2286.09 | 4.25 | 125.9 |
| sqrt + half-signed | 0–300秒 | 4.4871 | 2.5618 | 8.0695 | 3025.63 | 3.74 | 94.9 |
| sqrt + half-signed | 300–600秒 | 3.5957 | 1.4017 | 8.6861 | 4598.66 | 0.96 | 105.2 |

## 監査・保存

- 30/30 runが`exit_code: 0`、`source_unchanged: true`、開始時clean
- source commit、固定入力hash、Python 3.15.1、SUMO 1.28.0、方式設定一致
- 必須artifact、全ログ、10 checkpoint/run、物理衝突0、重大traceback/fatalなし
- half-signedのマシン全体最大SUMO数は15、slot超過なし
- 診断JSONLとcheckpointを可逆圧縮し、復元SHA-256と行数を全項目で検証
  - sqrt: 21,882,134,476 → 2,286,584,330 B（1330項目、分割10ファイル）
  - mean: 21,400,431,473 → 2,283,806,259 B（1330項目、分割10ファイル）
  - half-signed: 20,969,687,071 → 2,138,339,258 B（1330項目、分割9ファイル）

GitHubへの一括pushはHTTP 500で切断されたため、seedを累積する一時commit chainで
objectを段階転送した。正式branchのcarrier commitは元の専用commitとtree SHAが完全一致し、
一時refは削除した。結果内容の変更やrerunはない。

監査ファイルSHA-256（`post-run` / `compression` / `storage-split`）:

- sqrt: `c7fc3a40ae1893e6b0c6f06ba460ff8a8a58b1dfcdcc6ea43317b2ca3e036cf9` / `0b76e5dcea8b0803b4df558fa42c1a6af2f3d0213508d7b4884e356917237eab` / `bad6bf7ef0cd9a5ee3dd3f627a1f200821f60c7951c942f451637be4a05c1e50`
- mean: `af18a985e390e3cc0047a25748d0ab3bbb06113826d6817504d7dde366c35081` / `a9c60223607402ea6dbccc31eb0ddec68b09554c47d56746a3ea7252862f0b7c` / `a5d16a8f78dee557bb1cfec86ad867b9f67a64ba94296af05dc4bbd2a902f41d`
- half-signed: `7edf2f9f6689391e60c3ab960bcbd820548489fe90ce9758376684cc206c2102` / `ed4155cc3955bbc3ecd953fddc3d57629a8cc0301d51aa11fd1fb9ba652794c2` / `05d20291864cc04344a5dea9449d816d4151eb3fbaac5fcbb3cc0580558a9631`

## 結論と制約

1200/1000の同一10 seed developmentでは、sqrt-followersが正規化なしのReject偏重を
緩和し、本線保護を一部残しながら合流側と処理台数を改善した。mean-followersは処理性能を
さらに改善したが本線側負担が大きい。sqrt + half-signedはseed 39で破局的状態を生じた。

よって次の独立検証候補は`sqrt-followers`とし、half-signedは採用しない。mean-followersは
公平性重視の比較対象として残せるが、現行提案の置換候補とはしない。本結果は同じseedを
見ながら案を追加したadaptive developmentであり、一般的優越性や独立した効果確認を
主張しない。採用判断には別seedでの事前固定検証が必要である。
