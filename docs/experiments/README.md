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
| completed | 2026-10-31 | 反復拒否の実測待ち時間を加えた300秒交通性能試験 | [記録](2026-10-31-repeated-rejection-wait-development.md) |
| planned | 2026-11-01 | Eval.7の合流側交通量を見直す比率試験 | [記録](2026-11-01-eval7-flow-ratio-sweep.md) |
