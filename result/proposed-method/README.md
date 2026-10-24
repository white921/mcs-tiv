# 提案手法の結果

減速伝播を用いた提案手法の評価結果を保存する。2026-10-24時点では、該当する正式な結果はまだない。

## Eval.3の推奨構成

```text
proposed-method/
└── eval3/
    ├── evaluation-report.json
    ├── evaluation-report.md
    ├── seed-1/
    │   ├── manifest.json
    │   ├── evaluation-metrics.json
    │   └── deceleration-audit.json
    ├── seed-2/
    ├── seed-3/
    ├── seed-4/
    └── seed-5/
```

## 保存条件

- seedごとに新規ディレクトリを作り、別実行のファイルを上書きしない。
- `manifest.json`にはGit commit、SUMO/Python/依存版、実行コマンド、流入量、seed、時間、車種割当を記録する。
- `evaluation-metrics.json`には速度・局所負担・予測精度の計測値を保存する。
- `deceleration-audit.json`には提案判断、TIV判断、一致・不一致、フォールバックを保存する。
- 集計版の`evaluation-report.json`はseed別JSONだけから生成し、HTMLレポートの数値正本とする。
- 選択されなかった逆判断は、同じ状態から2枝で再実行しない限り反実仮想の実測結果と呼ばない。
