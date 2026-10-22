# mcs-tiv

SUMO上でMutual Concession System（MCS）とTime to Intersection Value（TIV）による
協調走行を検証する研究コードです。

## 山下修士論文のT字路 Eval.3 再現

`junction/junction_three_agree.py` は、山下裕太郎「経路影響値に基づく協調自動運転車の
交渉受入れ判断手法に関する研究」5.3.4節の条件を対象にしています。CAVcar と CAVbus は
同じ車体寸法（5.0 m × 1.8 m）で、最高速度・加減速度は論文の表5.1に合わせています。
TIVte は時間項・環境項、TIVtep はそれに性能項を加えた判定です。

まず依存パッケージと SUMO 1.20.0 を仮想環境へ導入します。論文実験と同じ版を使用します。

```bash
bash scripts/setup.sh
bash scripts/run_sumo.sh junction/run_yamashita_eval3.py
```

各方式（ALW/ACT/SPD40/UTF/TIVte/TIVtep）について、各方向400・500台/h、バス比率25%、
600秒、5 seed の平均速度を論文値と並べて表示します。

## 全評価（Eval.1--7）の再実行と照合

以下は、論文で総平均速度が掲載された全条件を、各5 seedで実行し、
`results/yamashita/comparison.csv` に論文値との差分を出力します。実験数が多く、完走には
長時間を要します。

```bash
bash scripts/setup.sh
python3 run_yamashita_evaluations.py
```

既定では仮想環境の SUMO 1.20.0 を使用し、個々の実験出力は `results/yamashita/` に隔離されるため、
既存の `junction/statistics/`・`merge/statistics/` は変更しません。評価を絞る場合は、例えば
`python3 run_yamashita_evaluations.py --evaluations eval4 eval5` とします。
12並列（既定値）を変更する場合は `--workers 6` のように指定できます。
まず全条件を seed 1 だけで比較する場合は `python3 run_yamashita_evaluations.py --stage-one` を使います。

2026年9月30日に、引き継ぎ用フォルダの `sumo-mcs-11` を作業中の最新スナップショットとして移行しました。

## 主な実験

山下研究のT字路・バス25%条件に最も近い実行ファイルは
[`junction/junction_three_agree.py`](junction/junction_three_agree.py) です。

- `alpha=6`: TIVte（時間優先度 + 環境優先度）
- `alpha=7`: TIVtep（時間優先度 + 環境優先度 + 性能優先度）
- シミュレーション時間: 600秒
- バス混入率: 25%

```bash
bash scripts/run_sumo.sh junction/junction_three_agree.py 7 1 400 400 400 --nogui
```

引数は順に `alpha`、`seed`、左・下・右方向の流入量（台/h）です。
`scripts/run_sumo.sh` は既定で仮想環境内の SUMO 1.20.0 を設定します。別の同版 SUMO を
使う場合は `MCS_TIV_SUMO_HOME=/path/to/sumo bash scripts/run_sumo.sh ...` と指定できます。描画は
既定で無効な Agg バックエンドを使うため、ディスプレイのない計算機でも実行できます。

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

TIVtep の判定経路を含め、実験ランナーをヘッドレスに起動できるよう設定しています。
論文と同じ SUMO 1.20.0、600秒、0.1秒刻み、5 seed の条件で全表の総平均値を再計算・照合できます。

## 引き継ぎ履歴

元リポジトリのブランチとPRマージ履歴は、このリポジトリの `upstream/*` ブランチに保存しています。
詳細は [`docs/upstream-history.md`](docs/upstream-history.md) を参照してください。
