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
| running | 2026-10-30 | Eval.3/5/7・交渉単位Accept/Reject反実仮ベンチマーク | [記録](2026-10-30-decision-oracle-benchmark.md) |
