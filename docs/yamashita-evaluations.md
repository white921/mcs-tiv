# 山下修士論文: 評価再現条件

全実験は600秒、0.1秒ステップ、5 seed（1--5）で実行する。方式の `alpha` は ALW=1、ACT=2、SPD20=3、SPD40=4、UTF=5、TIVte=6、TIVtep=7 に対応する。

## T字路

- Eval.1: `junction_three_agree.py` に `--bus-share 0 --route-mode eval1` を付ける。流入は A/B/C = 660/180/660、630/240/630、600/300/600、570/360/570、540/420/540。AとCは直進、Bは右左折をランダムに選ぶ。
- Eval.2: `--bus-share 0 --route-mode random`。各方向400、500、600台/h。
- Eval.3: `--bus-share 0.25 --route-mode random`。各方向400、500、600台/h。表5.7/5.8の比較には `run_yamashita_eval3.py` を使用する。

例:

```bash
cd junction
python3 junction_three_agree.py 6 1 600 300 600 --nogui --bus-share 0 --route-mode eval1
python3 junction_three_agree.py 7 1 500 500 500 --nogui --bus-share 0.25 --route-mode random
```

## 十字路

`junction_four_agree.py` は、左右流入を3方向に均等ランダム、上下流入を右左折に均等ランダムで割り当てる。

- Eval.4: 各方向300、400台/h、`--bus-share 0`、比較方式は ALW/ACT/SPD40/UTF/TIVte。
- Eval.5: 各方向300台/h、`--bus-share 0.25`、比較方式は ALW/ACT/SPD20/UTF/TIVte/TIVtep。

```bash
cd junction
python3 junction_four_agree.py 6 1 300 300 300 300 --nogui --bus-share 0
python3 junction_four_agree.py 7 1 300 300 300 300 --nogui --bus-share 0.25
```

## 合流

`merge_agree2512.py` の第3引数は合流車線（requesting）、第4引数は本線（accepting）の流入量。

- Eval.6: `--bus-share 0`。本線/合流 = 1200/800、1000/1000、800/1200。
- Eval.7: `--bus-share 0.25`。本線/合流 = 1000/1000。

```bash
cd merge
python3 merge_agree2512.py 6 1 1000 1000 --nogui --bus-share 0
python3 merge_agree2512.py 7 1 1000 1000 --nogui --bus-share 0.25
```

論文と同じSUMO 1.20.0で実行し、各設定についてseed 1--5の算術平均を表5.4--5.15の値と比較する。
実行と総平均値の照合は、リポジトリ直下で `python3 run_yamashita_evaluations.py` を使う。
