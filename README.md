# mcs-tiv

SUMO上でMutual Concession System（MCS）とTime to Intersection Value（TIV）による
協調走行を検証する研究コードです。

2026年9月30日に、引き継ぎ用フォルダの `sumo-mcs-11` を作業中の最新スナップショットとして移行しました。

## 主な実験

山下研究のT字路・バス25%条件に最も近い実行ファイルは
[`junction/junction_three_agree.py`](junction/junction_three_agree.py) です。

- `alpha=6`: TIVte（時間優先度 + 環境優先度）
- `alpha=7`: TIVtep（時間優先度 + 環境優先度 + 性能優先度）
- シミュレーション時間: 600秒
- バス混入率: 25%

```bash
cd junction
python3 junction_three_agree.py 7 1 400 400 400 --nogui
```

引数は順に `alpha`、`seed`、左・下・右方向の流入量（台/h）です。
SUMOの利用には `SUMO_HOME` の設定が必要です。

## 現在の再現状況

TIVtepの判定経路が動作し、600秒間完走することは確認済みです。
ただし、現状は論文数値の完全再現ではありません。

- バスの最大加速度がコード上 `1.5 m/s²`、論文では `1.0 m/s²`
- 論文のSUMO 1.20.0に対し、直近の動作確認はSUMO 1.27.1
- 400/500台/hの各5 seed平均は未実施
- 衝突回数の集計は現在正しく機能していない

## 引き継ぎ履歴

元リポジトリのブランチとPRマージ履歴は、このリポジトリの `upstream/*` ブランチに保存しています。
詳細は [`docs/upstream-history.md`](docs/upstream-history.md) を参照してください。
