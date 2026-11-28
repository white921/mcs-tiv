# 信号形成車群における積算・終端値アブレーション

- 台帳ID: `2026-11-02-signal-release-integration-ablation`
- 状態: `completed`
- 位置づけ: `development`
- 開始日: 2026-11-02
- 終了日時: 2026-11-02 06:31:55 JST
- 実験ディレクトリ:
  - `results/runs/signal-red08-integrated-harm-lambda2-seeds1-2-3-7-11-300s-20261102T/`
  - `results/runs/signal-red08-terminal-harm-lambda2-seeds1-2-3-7-11-300s-20261102T/`
  - red-08完了後、事前条件に従ってred-16の同様2バッチを実行する。

## 目的

10秒後の終端速度だけでは捨てられる途中の速度損失を積算することが、
信号放流で形成された車群の合流判断と交通性能に寄与する条件を探索する。
現在の提案式 `arrival_margin + 2 * max(accept_loss - reject_loss, 0)` は固定し、
損失の時間表現だけを比較する。

## 仮説と比較対象

- 積算: 10秒間の0.1秒速度差を台形積分する。
- 終端値: 10秒後の速度差を10秒保持した同単位のアブレーションとする。
- 仮説: 赤信号で溜めた本線側車列を1秒headwayで放流すると、合流判断による
  一時的な減速波が生じる。10秒後に回復する場面では終端値に対し積算が有利になる。
- 条件選択: 旧・dirtyな単一seed診断で積算の速度が終端値より高かった
  `red-08`（+0.5055 m/s）と`red-16`（+0.3676 m/s）の2条件に限定する。旧結果自体は
  判断根拠に使わず、今回はcleanな現行式で全seedを再実行する。
- 本実験は有効条件探索であり、最終確認ではない。

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
| 比較 | `integrated` vs `terminal-held` |
| 併用しない機能 | 反復拒否待ち、承諾リース、早期合流、2段階交渉、priority hold |
| 環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |
| 並列数 | 各方5、合計10 SUMO |

## 評価

- 主にseed対応の全車平均速度差を見る。
- 停止時間、流出数、急減速、物理衝突、承諾率を併記する。
- 判断不一致場面で、終端速度差が小さいのに積算損失差が残る件数を集計する。
- 積算の5-seed平均速度が高くても、物理衝突または急減速が悪化した場合は
  「交通性能と安全性のtrade-off」とし、単純な優位としない。

## 完了後に記録するもの

- 全Runの`exit_code`、`source_unchanged`、Git clean状態、固定入力hash。
- runner/stdout/stderr/SUMOログ、必須artifact、物理衝突、警告。
- 条件別・seed別の主要指標、判断不一致の内訳、限界。
- 実行ソースcommit、結果commit、記録commit。

## 完全性監査

- red-08・red-16、integrated・terminal-heldの4 batch、合計20 runはすべて
  `exit_code: 0`、`source_unchanged: true`、開始時Git clean、5 checkpoint/runだった。
- 実行ソースは全runで`6b9c192056d4882417ebf632427f081ca9ad94b6`、固定入力hashは
  各run manifestに記録されている。
- 全20 runで物理衝突episodeは0。
- 結果commit: `429b7d7ba34b3d852a86b866bc937589e165cb9e`
  (`codex/integration-condition-search-night-results`)。

## 結果

| 放流条件 | integrated平均 (m/s) | terminal-held平均 (m/s) | 対応平均差 (m/s) | integrated勝利seed |
| --- | ---: | ---: | ---: | ---: |
| red-08 | 5.0841 | 4.7674 | +0.3167 | 4 / 5 |
| red-16 | 4.9289 | 4.7980 | +0.1308 | 3 / 5 |

red-08ではseed 3だけintegratedが低く、red-16ではseed 2と7で低かった。どちらも
平均点推定はintegratedが上だが、5 seedのdevelopmentであり一般的優越性は主張しない。

## 結論

信号放流車群では10秒後の終端値だけでなく途中の速度損失を積算することで、平均速度が
改善する条件が存在するという仮説と整合した。ただし条件は旧・dirtyな単一seed診断を
見て選ばれており、方式も現在の正規化凸結合式ではなく旧`lambda=2`害のみ加点である。
その後の正規化式・共通lambda選定・独立holdoutが主系列となったため、本結果を理由に
red条件や旧方式を追加実行しない。積算表現の補助的development証拠として保持する。
