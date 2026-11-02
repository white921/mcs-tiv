# 信号形成車群における積算・終端値アブレーション

- 台帳ID: `2026-11-02-signal-release-integration-ablation`
- 状態: `completed`
- 位置づけ: `development`
- 実施日: 2026-11-02
- 比較対象: 同一条件・同一seedの`integrated`と`terminal-held`
- 実験ディレクトリ:
  - `results/runs/signal-red08-integrated-harm-lambda2-seeds1-2-3-7-11-300s-20261102T/`
  - `results/runs/signal-red08-terminal-harm-lambda2-seeds1-2-3-7-11-300s-20261102T/`
  - `results/runs/signal-red16-integrated-harm-lambda2-seeds1-2-3-7-11-300s-20261102T/`
  - `results/runs/signal-red16-terminal-harm-lambda2-seeds1-2-3-7-11-300s-20261102T/`

## 目的

10秒後の終端速度だけでは捨てられる途中の速度損失を積算することが、信号放流で
形成された車群の合流判断と交通性能に寄与する条件を探索する。現在の提案式
`arrival_margin + 2 * max(accept_loss - reject_loss, 0)`は固定し、損失の時間表現だけを比較した。

## 条件

| 項目 | 値 |
| --- | --- |
| ケース | Eval.7 |
| 交通量 | 合流側1000 / 本線側1000台/時 |
| Bus比率 | 25% |
| seed | `1, 2, 3, 7, 11` |
| 時間 | 300秒 |
| 放流条件 | 40秒cycle、赤信号8秒または16秒、放流1秒headway |
| 判断式 | 害のみ加点、`lambda=2`、一様10秒 |
| 比較 | 10秒積算 vs 10秒後の速度差を10秒保持した同単位アブレーション |
| 併用しない機能 | 反復拒否待ち、承諾リース、早期合流、2段階交渉、priority hold |
| 環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |

## Git系譜

| 種別 | 値 |
| --- | --- |
| 実行ソース | `6b9c192056d4882417ebf632427f081ca9ad94b6` |
| red-08 integrated結果 | `a0c35bd7bc330cab5a196c74a7f06db07df4fc1c` |
| red-08 terminal-held結果 | `b2361f35420be093d8f060f47eab9c5edd1fe4a4` |
| red-16 integrated結果 | `4f51b9c564f5590af27668934f9265b3134cd29e` |
| red-16 terminal-held結果 | `36c0207163f53659a00c40c10eb6a622e6230729` |
| 結果branch | `codex/integration-condition-search-night-results` |
| 記録commit | この記録の完了更新を含むcommit |

## 完全性確認

- 4バッチ20 Runすべて`experiment completed`、`exit_code: 0`、`source_unchanged: true`。
- 開始時Git clean、実行ソースSHA、固定入力hash、Python/SUMO版、機能manifestは条件どおり。
- runner/stdout/stderr/SUMOログ、FCD、trace、metrics、5 checkpoint/Runを確認した。
- 物理衝突は全Runで0。Traceback、error、重大warning、collision warningはなかった。
- 90 MiB超の診断JSONLとcheckpointは決定的gzipへ可逆圧縮し、展開後SHA-256と
  行数またはbyte数を全件照合した。必須入力とsource snapshotは圧縮していない。
- red-08 terminal seed 11の圧縮済み診断1件は50.01 MBでGitHubの推奨値をわずかに
  超えたが、100 MB制限未満でpushと整合性検証は成功した。

## 結果

差はすべて`integrated - terminal-held`のseed対応差である。

| 条件 | 平均速度 integrated / terminal (m/s) | Δ速度 | Δ停止時間 (s) | Δ流出台数 | Δ急減速 (s) | Δ承諾率 (pt) | Δdecision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| red-08 | 5.084096 / 4.767359 | +0.316737 | -313.04 | +5.4 | +0.22 | -0.441963 | -179.6 |
| red-16 | 4.928891 / 4.798048 | +0.130843 | +37.98 | +0.2 | -0.34 | +0.779708 | -61.6 |

| 条件 | seed | Δ速度 (m/s) | Δ停止 (s) | Δ流出台数 | Δ急減速 (s) | Δ承諾率 (pt) | Δdecision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| red-08 | 1 | +0.328 | +239.0 | +5 | -0.8 | -1.57 | -162 |
| red-08 | 2 | +0.190 | -299.4 | +2 | +3.1 | -1.53 | -87 |
| red-08 | 3 | -0.487 | +789.1 | -1 | -0.7 | -4.31 | -167 |
| red-08 | 7 | +0.395 | -987.3 | +7 | +0.0 | +2.58 | -147 |
| red-08 | 11 | +1.159 | -1306.6 | +14 | -0.5 | +2.63 | -335 |
| red-16 | 1 | +0.170 | -337.3 | +3 | -0.3 | -1.28 | -125 |
| red-16 | 2 | -0.380 | +654.2 | -7 | +2.5 | +5.80 | +104 |
| red-16 | 3 | +0.684 | -1187.7 | +4 | +2.8 | +1.90 | +24 |
| red-16 | 7 | -0.042 | +1171.0 | -3 | -2.0 | -3.94 | -40 |
| red-16 | 11 | +0.223 | -110.3 | +4 | -4.7 | +1.42 | -271 |

### 判断診断

軌跡分岐後の診断であり、同一の反実仮状態を再現した比較ではない。開始時刻、sender、
receiver、希望経路、代替経路が一致する判断だけを対応付けた。「終端差小」は
終端値換算の速度差が0.05 m/s以下、「積算差あり」は積算損失差が0.1 m超である。

| 条件 | 対応判断 | 判断不一致 | 終端差小・積算差あり |
| --- | ---: | ---: | ---: |
| red-08 | 66 | 18 | 25 |
| red-16 | 94 | 21 | 27 |

## 結論と限界

red-08は5 seed中4 seedで平均速度が上がり、停止時間と流出も平均改善したため、
「途中で減速し終端までに回復する車群」は積算の有効条件候補として残る。ただし急減速は
平均0.22秒増えており、単純な全面優位ではない。red-16は速度差が小さく停止時間も平均悪化し、
赤時間を長くすれば積算の利点が単調に増えるという仮説は支持されなかった。

この2条件とseedは探索段階で選ばれており独立確認ではない。終端値方式も同単位比較用の
合成アブレーションである。採用判断には条件を事前固定した未使用seedで、red-08近傍の
信号位相と減速回復時間を独立確認する必要がある。
