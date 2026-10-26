# 実験結果の保存先

今後のシミュレーション結果は、すべてこの `results/` を正本とする。
新規実行では単数形の `result/` を使用しない。

## 新しい配置

`scripts/run_thesis_batch.py` は、`--output` を省略すると次の形式で
実験フォルダーを自動作成する。

```text
results/
└── runs/
    └── 20261026T153000+0900__proposal__eval3__600s__seeds-1-2-3-4-5/
        ├── experiment-manifest.json
        ├── runner.log
        ├── summary.json
        └── eval3/
            ├── seed-1/
            │   ├── manifest.json
            │   ├── stdout.log
            │   ├── stderr.log
            │   ├── fcd.xml.gz
            │   ├── vehicle-states.jsonl
            │   ├── negotiations.jsonl
            │   ├── conflicts.jsonl
            │   ├── prediction-events.jsonl
            │   ├── evaluation-metrics.json
            │   ├── checkpoints/
            │   └── source/
            └── seed-2/
                └── ...
```

- バッチ1回を `runs/<実験ID>/` へまとめる。
- 独立したシミュレーション1回（1ケース・1seed）は
  `<実験ID>/<Eval>/seed-<seed>/` の1フォルダーにまとめる。
- 実験全体の条件と完了状態は `experiment-manifest.json`、各seedの条件と
  完了状態は `manifest.json` を正本とする。
- `runner.log` も実験フォルダー内へ保存し、フォルダーの外へ置かない。
- 同名フォルダーへの追記・上書きはしない。

## 実行例

保存先を自動命名する場合:

```bash
python3 scripts/run_thesis_batch.py \
  --sumo-home "$SUMO_HOME" \
  --cases eval3 \
  --seeds 1 2 3 4 5 \
  --duration 600 \
  --workers 5 \
  --deceleration-active
```

短い名前を指定する場合:

```bash
python3 scripts/run_thesis_batch.py \
  --sumo-home "$SUMO_HOME" \
  --run-name eval3-proposal-seeds1-5-600s \
  --cases eval3 \
  --seeds 1 2 3 4 5 \
  --duration 600 \
  --workers 5 \
  --deceleration-active
```

## 既存ディレクトリ

- `results/` 直下にすでにある過去実験は、参照切れを防ぐため移動しない。
- `result/` は引き継ぎ資料や過去の集約結果を保持する旧アーカイブであり、
  新しいシミュレーションの出力先にはしない。

