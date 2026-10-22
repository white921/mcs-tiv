# 山下修士論文 第5章の評価条件

この文書は、論文表5.3、5.4、5.6〜5.15を現行コードの引数へ対応付ける。
方式番号は `ALW=1`、`ACT=2`、`SPD20=3`、`SPD40=4`、`UTF=5`、
`TIVte=6`、`TIVtep=7` とする。

## 評価条件

| 評価 | シナリオ | CAVbus | 流入量 | 経路 | 比較方式 |
| --- | --- | ---: | --- | --- | --- |
| Eval.1 | T字路 | 0% | A/B/C = 660/180/660、630/240/630、600/300/600、570/360/570、540/420/540 | A・C直進、BはA/Cへ50%ずつ | ALW、ACT、SPD40、UTF、TIVte |
| Eval.2 | T字路 | 0% | 各方向400、500、600 | 各流入から2方向へ50%ずつ | ALW、ACT、SPD20、UTF、TIVte |
| Eval.3 | T字路 | 25% | 各方向400、500、600 | 各流入から2方向へ50%ずつ | ALW、ACT、SPD40、UTF、TIVte、TIVtep |
| Eval.4 | 十字路 | 0% | 各方向300、400 | A・Cは3方向、B・Dは右左折 | ALW、ACT、SPD40、UTF、TIVte |
| Eval.5 | 十字路 | 25% | 各方向300 | Eval.4と同じ | ALW、ACT、SPD20、UTF、TIVte、TIVtep |
| Eval.6 | 合流 | 0% | 受入/要求 = 1200/800、1000/1000、800/1200 | 本線と合流車線 | ALW、ACT、SPD40、UTF、TIVte |
| Eval.7 | 合流 | 25% | 受入/要求 = 1000/1000 | 本線と合流車線 | ALW、ACT、SPD40、UTF、TIVte、TIVtep |

Eval.3の600/600/600は表5.3で定義されているが、第5章には対応する平均速度表がない。
そのため全評価ランナーは条件を実行対象に含める一方、論文参照値を空欄にする。

## T字路の直接実行

Eval.1の代表条件600/300/600、TIVte:

```bash
python3 junction/run_three_seeds.py 6 600 300 600 \
  --duration 600 --bus-share 0 --route-mode eval1 --no-save
```

Eval.2の400/400/400、TIVte:

```bash
python3 junction/run_three_seeds.py 6 400 400 400 \
  --duration 600 --bus-share 0 --route-mode random --no-save
```

Eval.3の400/400/400、TIVtep:

```bash
python3 junction/run_three_seeds.py 7 400 400 400 \
  --duration 600 --bus-share 0.25 --route-mode random --no-save
```

## 全条件ランナー

実行せずコマンドだけ確認する:

```bash
python3 run_yamashita_evaluations.py --dry-run --evaluations eval1 eval2
```

実際に選択した評価を走らせる場合は `--dry-run` を外す。実行結果は既存の
`statistics` へ追記せず、既定では `results/yamashita/runs.csv` と
`comparison.csv` へ分離して保存する。

論文本文は「異なる5 seedの平均」とだけ記し、seed識別子は示していない。
保存集計と一致する組は、Eval.3・5が1〜5、Eval.4が1/3/5/6/7、
Eval.6が1/2/3/6/8、Eval.7が1/2/3/7/11である。Eval.1/2は保存ブックの
seedシート名に合わせて1〜5を既定にするが、Eval.2の一部方式には欠損があり、
論文集計のseed由来は完全には確定していない。別の組を試す場合は `--seeds` を明示する。

## 静的監査で残る境界

- TIVte/TIVtepは共通の `func/thesis_tiv.py` を使う。
- ACTは、交差点では優先道路上または直進の受入車両が優先権を保持する。
- SPDは速度低下率が20%または40%ちょうどの場合も受け入れる。
- 25%は現行既定では総生成台数に最も近い固定台数とする。引き継ぎ原本の
  確率抽選を比較する場合だけ `--bus-allocation paper-random25` を使う。
- 流入時刻の生成、平均速度の時系列集計、通信の1ステップ遅延など、論文本文が
  規定していない実装上の仮定は残る。条件一致と数値再現完了は区別する。
