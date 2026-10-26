# mcs-tiv

SUMO上でMutual Concession System（MCS）とTime to Intersection Value（TIV）による
協調走行を検証する研究コードです。

2026年9月30日に、引き継ぎ用フォルダの `sumo-mcs-11` を作業中の最新スナップショットとして移行しました。

## Zotero原文による再現監査（2026-10-20）

方式6/7は、送信側TIV計算・MCM格納を行う共通実装に更新しています。
現段階は**原文準拠の再実装候補であり、論文数値の再現完了ではありません**。
原文との対応、明記されていない処理の仮定、単体テスト、SUMO1.17.0 /
Python3.9.6による隔離1ケース実行は
[再現監査](docs/thesis-audit.md)を参照してください。
評価条件と現行引数の対応は
[第5章の評価条件](docs/yamashita-evaluations.md)に一元化しています。
全条件の確認・実行には `run_yamashita_evaluations.py` を使用します。

## 主な実験

山下研究のT字路実験に対応する実行ファイルは
[`junction/junction_three_agree.py`](junction/junction_three_agree.py) です。

- `alpha=6`: TIVte（時間優先度 + 環境優先度）
- `alpha=7`: TIVtep（時間優先度 + 環境優先度 + 性能優先度）
- シミュレーション時間: 600秒
- バス混入率: Eval.1/2は0%、Eval.3は25%

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

Eval.1・2ではバス0%を指定し、Eval.1だけA・Cを直進に固定します。

```bash
# Eval.1-3（A/B/C = 600/300/600、TIVte）
python3 run_three_seeds.py 6 600 300 600 \
  --duration 600 --bus-share 0 --route-mode eval1 --no-save

# Eval.2-1（A/B/C = 400/400/400、TIVte）
python3 run_three_seeds.py 6 400 400 400 \
  --duration 600 --bus-share 0 --route-mode random --no-save
```

バスは各車を25%の確率で選ぶのではなく、全流入車両数の25%に最も近い台数をあらかじめ割り当てます。
400台/h・600秒・3方向の場合は全198台のため、バス50台（25.25%）です。

### 十字路

論文のEval.4（バス0%、4方向とも300台/h、TIV）を実行する例です。
原本CSVで論文値に使われたseedは `1, 3, 5, 6, 7` です。

```bash
python3 junction/run_four_seeds.py 6 300 300 300 300 \
  --duration 600 --bus-share 0 --reference-speed 7.2485
```

Eval.5（バス25%、4方向とも300台/h、TIVtep）はseed `1〜5`で次のように実行します。

```bash
python3 junction/run_four_seeds.py 7 300 300 300 300 \
  --duration 600 --bus-share 0.25 --reference-speed 6.4420
```

流入量は順に左・下・右・上です。論文と同様、上下方向から入る車両は
直進せず右左折のみを選びます。

### 合流

論文のEval.6（バス0%、要求側・受入側とも1000台/h、TIV）を実行する例です。
原本CSVで論文値に使われたseedは `1, 2, 3, 6, 8` です。

```bash
python3 merge/run_merge_seeds.py 6 1000 1000 \
  --duration 600 --bus-share 0 --reference-speed 4.8032
```

Eval.7（バス25%、TIVtep）はseed `1, 2, 3, 7, 11`で次のように実行します。

```bash
python3 merge/run_merge_seeds.py 7 1000 1000 \
  --duration 600 --bus-share 0.25 --reference-speed 4.2084
```

合流の流入量は順に要求車両（合流車線）・受入車両（本線）です。
試運転などで統計CSVへ追記したくない場合は `--no-save` を付けます。

## ディレクトリ構成

```text
mcs-tiv/
├── junction/                  # 交差点シナリオと実行スクリプト
│   ├── junction_three_agree.py # 論文再現の中心となるT字路
│   ├── junction_four_agree.py  # 4方向の十字路
│   ├── run_four_seeds.py        # 十字路の複数seed実行・平均集計
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
│   ├── run_merge_seeds.py      # 合流の複数seed実行・平均集計
│   ├── statistics/            # 過去の合流実験結果
│   └── unused/                # 旧ランナー
├── results/                   # 新しい実験結果の正本（1実験1フォルダー）
│   └── runs/<実験ID>/<Eval>/seed-<seed>/
├── result/                    # 引き継ぎ・旧集約結果の読み取り用アーカイブ
└── docs/
    ├── result-layout.md        # 実験結果の標準保存規約
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
- 原本CSVではT字路400台/h・TIVtepのseed 1が7.3317 m/s、seed 1〜5平均が論文値と同じ7.4159 m/s
- 現行コードのT字路400台/h・TIVtep（バス50/198台固定）は5 seed平均6.6741 m/s。論文値7.4159 m/sに対して-0.7418 m/s（-10.00%）
- 現行T字路は全seedで原本と6方向の生成台数が一致し、車種内訳だけをBus 50台・Car 148台に固定できている
- T字路500台/hの5 seed平均は未実施
- 十字路・合流は論文条件を指定できる複数seed実行スクリプトを追加済み
- 十字路Eval.4（300台/h、バス0%、TIV）は5 seed平均7.1545 m/s。論文値7.2485 m/sに対して-0.0940 m/s（-1.30%）
- 十字路Eval.4は全seedでBus 0台・Car 200台、かつ12方向の生成台数が原本と完全一致
- 十字路Eval.5（300台/h、バス25%、TIVtep）は5 seed平均5.6046 m/s。論文値6.4420 m/sに対して-0.8374 m/s（-13.00%）
- 十字路Eval.5は全seedでBus 50台・Car 150台、かつ12方向の生成台数が原本と完全一致
- 合流Eval.6（1000:1000台/h、バス0%、TIV）は5 seed平均4.4322 m/s。論文値4.8032 m/sに対して-0.3710 m/s（-7.72%）
- 合流Eval.6は全seedでBus 0台・Car 332台。seed 2だけ現行SUMOで強い渋滞状態に分岐し、原本比-49.95%
- 合流Eval.7（1000:1000台/h、バス25%、TIVtep）は5 seed平均3.1329 m/s。論文値4.2084 m/sに対して-1.0755 m/s（-25.56%）
- 合流Eval.7は全seedでBus 83台・Car 249台。seed 3・11が現行SUMOで強い渋滞状態に分岐
- 衝突回数の集計は現在正しく機能していない

## 引き継ぎ履歴

元リポジトリのブランチとPRマージ履歴は、このリポジトリの `upstream/*` ブランチに保存しています。
詳細は [`docs/upstream-history.md`](docs/upstream-history.md) を参照してください。
