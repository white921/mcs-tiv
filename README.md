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

seed 1〜5を連続実行し、バス込みの全車両平均速度を集計する場合は次を実行します。

```bash
python3 run_three_seeds.py 7 400 400 400 --duration 600 --reference-speed 7.4159
```

バスは各車を25%の確率で選ぶのではなく、全流入車両数の25%に最も近い台数をあらかじめ割り当てます。
400台/h・600秒・3方向の場合は全198台のため、バス50台（25.25%）です。

## ディレクトリ構成

```text
mcs-tiv/
├── junction/                  # 交差点シナリオと実行スクリプト
│   ├── junction_three_agree.py # 論文再現の中心となるT字路
│   ├── junction_four_agree.py  # 4方向の十字路
│   ├── junction_agree.py       # 旧版のT字路
│   ├── *.net.xml              # SUMOの道路ネットワーク
│   ├── *.rou.xml              # 車両種別・経路定義
│   ├── *.sumocfg              # SUMO起動設定
│   ├── statistics/            # 過去の実験結果と集計ファイル
│   └── gif/                   # 過去の可視化用画像
├── func/                      # CAV・バスの制御と合意判定
│   ├── cav_three_junction.py  # T字路の乗用車、TIVte/TIVtep式
│   ├── cav_three_junction_bus.py # T字路のバス
│   ├── cav_four_junction*.py  # 十字路用制御
│   ├── cav_merge*.py          # 本線合流用制御
│   ├── animation_*.py         # 走行状況の可視化
│   └── unused/                # 現在の主実験から外れた旧実装
├── PathPlanning/              # 現在の実験が呼び出す軌道生成
│   ├── FrenetOptimalTrajectory/ # Frenet座標系の軌道計画
│   ├── CubicSpline/           # スプライン計算
│   └── QuinticPolynomialsPlanner/ # 5次多項式軌道
├── PathPlanning_frenet/       # 各種経路計画手法の参考実装群
├── merge/                     # 本線合流シナリオと過去の結果
│   ├── merge_agree2512.py     # 新しい合流実験ランナー
│   ├── merge_agree4.py        # 旧版の合流実験
│   ├── statistics/            # 過去の合流実験結果
│   └── unused/                # 旧ランナー
└── docs/
    └── upstream-history.md     # 移行元のGit・PR・Issue情報
```

論文のT字路実験を追う場合の主な呼び出し関係は次の通りです。

```text
junction/junction_three_agree.py
    ├── func/cav_three_junction.py
    ├── func/cav_three_junction_bus.py
    └── PathPlanning/FrenetOptimalTrajectory/frenet_three_junction.py
```

`junction` は交差点全般を指す名前です。その中で `three` は3方向から流入するT字路、
`four` は4方向から流入する十字路を表します。

## 現在の再現状況

TIVtepの判定経路が動作し、600秒間完走することは確認済みです。
ただし、現状は論文数値の完全再現ではありません。

- バスの最大加速度は論文に合わせて `1.0 m/s²`に修正済み
- バス混入率は総車両数の25%に最も近い台数に固定済み
- 論文のSUMO 1.20.0に対し、直近の動作確認はSUMO 1.27.1
- 400/500台/hの各5 seed平均は未実施（一括実行スクリプトは追加済み）
- 衝突回数の集計は現在正しく機能していない

## 引き継ぎ履歴

元リポジトリのブランチとPRマージ履歴は、このリポジトリの `upstream/*` ブランチに保存しています。
詳細は [`docs/upstream-history.md`](docs/upstream-history.md) を参照してください。
