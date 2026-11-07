# オラクル整合v2のEval.7交通量スイープ

- 台帳ID: `2026-11-07-oracle-v2-eval7-flow-sweep`
- 状態: `running`
- 位置づけ: `development; reuse of previously observed inputs`
- 開始日時: 2026-11-07 15:22 JST
- 実装ブランチ: `codex/oracle-v2-eval7-flow-sweep`
- 実行ソースcommit: `d9d9a457af78a8a19a76daff5ec5e277021e3a0a`
- Ubuntu unit: `mcs-oracle-v2-eval7-flow-sweep-20261107.service`
- orchestrator SHA256: `f722a5d5da0ec578b5750a466d630cd96a8fd87ddd5ec785520bc5b99c8203f6`

## 目的

旧害のみlambda=2方式が中負荷の500/1000、700/1000台/時で示した交通性能改善が、
到着時間Acceptのうち予測総移動距離でRejectが10 m超有利な判断だけをRejectへ上書きする
オラクル整合v2でも再現するか調べる。既存の山下方式・旧lambda=2結果は再実行せず、
同一固定入力でv2だけを新規実行する。

## 固定条件

| 項目 | 条件 |
| --- | --- |
| ケース | Eval.7車線減少型合流 |
| 方式 | オラクル整合v2片方向10 m Rejectゲート |
| 交通量 | 合流側/本線側 = 300/1000、500/1000、700/1000、1000/1000台/時 |
| seed | `6, 8, 9, 10, 12` |
| 時間 | 300秒 |
| 入力 | `fixed_inputs/thesis/eval7-flow-sweep/`の既存固定入力 |
| Bus比率 | 25%固定 |
| 予測窓 | 10秒、0.1秒刻み、1秒再計画 |
| v2規則 | 到着時間Acceptかつ`Accept-Reject < -10 m`だけRejectへ上書き |
| fallback | 予測不能時は山下TIVtep |
| 併用しない機能 | 待ち時間加点、早期交渉、2段階交渉、priority hold |
| 環境 | Ubuntu `sgnlab`、Python 3.15.1、SUMO 1.28.0 |

4交通量は独立した実験ディレクトリとする。最大10 SUMOを守るため、5-worker batchを
2本ずつ並行し、前半2本が正常終了した場合だけ後半2本を開始する。

実行前にUbuntuのPython 3.15.1 / SUMO 1.28.0で全175 testが成功した。
500/1000、seed 6、20秒stop-timeのsmokeも`exit_code: 0`、
`source_unchanged: true`で完了し、交通量別固定入力とv2規則、必須artifact生成を確認した。

## 比較対象

既存の`2026-11-01-eval7-flow-ratio-sweep`を数値の正本とする。

- 山下300/500: `025b4f0d`
- 旧lambda=2 300/500: `3e82e417`
- 山下700/1000: `97715840`
- 旧lambda=2 700/1000: `07ca873f`

既存40 runと新規20 runは同じ固定入力・seed・300秒prefixを使う。v2実行前に
`SHA256SUMS`と各run manifestの入力SHAを照合する。

## 評価

- 全車および合流側・本線側の平均速度
- 停止時間、最大停止列、車線端10秒以上停止
- 300秒までの退出台数
- 承諾率、v2のAccept→Reject上書き数、山下fallback率
- hard brake時間、TraCI物理衝突
- seed対応のv2−山下、v2−旧lambda=2差

この交通量とseedは既に結果を見ているため、本実験は方式選択用のdevelopmentであり、
最終的な優位性の確認には用いない。良い条件だけを事後選択して成功主張せず、4交通量を
すべて報告する。有望な条件は未使用seed・事前固定条件で別途確認する。

## 完了条件

- [x] 実行ソースcommitと入力SHAを記録
- [x] Ubuntu正式環境で全テストと単一seed smoke
- [ ] 4 batch、20 runが`exit_code: 0`かつ`source_unchanged: true`
- [ ] 必須artifact、runner/stdout/stderr/SUMOログを監査
- [ ] 物理衝突と既知警告を確認
- [ ] 4交通量のcase/seed別結果を既存2方式と比較
- [ ] 正常結果だけを専用commitでpush
