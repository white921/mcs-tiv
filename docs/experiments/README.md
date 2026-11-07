# 実験台帳

数値の正本は`results/runs/<experiment-id>/`配下のmanifestとログとする。
このディレクトリには、各バッチの目的、条件、比較対象、Git系譜、
限界と結論を記録する。

## 運用

- 実行前に記録を作り、`planned`または`running`にする。
- 正常終了後、全Runの`exit_code: 0`と`source_unchanged: true`を確認する。
- runner/stdout/stderr/SUMOログ、必須artifact、物理衝突を確認する。
- 結果ディレクトリのみを専用commitでpushする。
- 失敗・未完了結果はpushしない。

## 現在の実験

| 状態 | 開始日 | 実験 | 記録 |
| --- | --- | --- | --- |
| completed | 2026-10-30 | Eval.3/5/7・交渉単位Accept/Reject反実仮ベンチマーク | [記録](2026-10-30-decision-oracle-benchmark.md) |
| completed | 2026-10-31 | 後続車害のみ合成・未使用seed独立holdout | [記録](2026-10-31-decision-oracle-harm-only-holdout.md) |
| completed | 2026-11-02 | 判断後悔量の評価窓・評価量に対する頑健性確認 | [記録](2026-11-02-decision-regret-robustness.md) |
| incomplete | 2026-11-02 | 後続車影響項の寄与を確認する先頭4交渉holdout | [記録](2026-11-02-follower-impact-attribution-holdout.md) |
| completed | 2026-11-03 | 後続車影響項の寄与を確認する時間層別holdout | [記録](2026-11-03-follower-impact-time-stratified-holdout.md) |
| completed | 2026-11-05 | オラクル整合距離予測v2の保存済み960場面開発再採点 | [記録](2026-11-05-oracle-aligned-predictor-v2-development.md) |
| completed | 2026-11-05 | オラクル整合v2の未使用seed時間層別独立holdout | [記録](2026-11-05-oracle-aligned-v2-independent-holdout.md) |
| planned | 2026-11-07 | オラクル整合v2のEval.7交通量スイープ | [記録](2026-11-07-oracle-v2-eval7-flow-sweep.md) |
