# 3シナリオ共通λ=0.95の最終holdout

- 台帳ID `2026-11-27-universal-lambda095-final-holdout`
- 状態 `running`
- 分類 `formal`

## 目的

合流、T字路、十字路を共通の式とパラメータで扱うため、development
screeningで事前固定した正規化凸結合式の `lambda=0.95`を、選定に使って
いないseedで山下TIVtepと比較する。主指標は各形状の全車平均速度とし、
形状別の対応seed差、3形状の等重み相対差平均、および最悪形状の相対差を
報告する。結果を見てlambdaを再調整しない。

## 条件

| 形状 | 条件（台/時） | 方式 | seed | 本数 |
| --- | --- | --- | --- | ---: |
| Eval.3 T字路 | 500 / 500 / 500 | 提案λ=0.95、山下TIVtep | 23–32 | 20 |
| Eval.5 十字路 | 300 / 300 / 300 / 300 | 提案λ=0.95、山下TIVtep | 23–32 | 20 |
| Eval.7 合流 | 合流1000 / 本線1000 | 提案λ=0.95、山下TIVtep | 23–32 | 20 |

- 各600秒、Bus比率25%固定、Python 3.15.1、SUMO 1.28.0。新規60 run。
- 診断トレースを有効、60秒間隔のcheckpointを保存する。
- 方式以外の条件は対応seed内で一致させる。提案手法は
  `M=(1-lambda)Z_time+lambda Z_follow`、`lambda=0.95`、山下TIVtepは減速伝播を無効にする。
- 固定入力は
  `fixed_inputs/thesis/universal-lambda095-holdout/<condition>/seed-<seed>.jsonl`。
  seed 23–32は既存のλ選定development（Eval.3/5は13–22、Eval.7は33–42）で
  使用していない。
- 実行キューは `condition -> method -> seed`。条件順は
  `Eval.3 500 -> Eval.5 300 -> Eval.7 1000`、方式順は`提案 -> 山下`。
  実行機全体で15 SUMOを上限とする。
- 起動時に先行のEval.7診断SUMOが残っている場合は、そのコマンドが記録済みの
  診断出力パスと一致することを検査し、`15 - 先行SUMO数`の空き枠だけを投入する。
  先行runが終了した分は自動的にholdoutで補充し、常に機械全体で15本以下とする。

## 比較対象と選定の系譜

- 共通λの選定根拠は
  [3シナリオ共通λの高λ域スイープ](2026-11-25-universal-lambda-high-sweep-development.md)。
- 本holdoutでは同じ新規固定入力を使い、現行の同一実行ソースから提案と山下
  TIVtepを実行する。既存の山下結果は旧ソースとの交絡を避けるため再利用しない。
- 実行ソースbranchは `codex/universal-lambda095-holdout`、source commitは
  `f7590fd4d73d78c4f7863512b12985f33d6540bf`。実験worktreeはこのcommitに固定し、
  scheduler修正は別control worktreeから行う。

## 実行・保存予定

- 実行機 `sgnlab`。systemd user unit、invocation ID、実行開始時刻は起動時に追記する。
- `scripts/run_holdout_alongside_diagnostic_20261127.sh`で先行診断の空き枠を使って
  holdoutを起動する。先行診断の完了監査は
  `scripts/audit_after_eval7_diagnostic_20261127.sh`の別unitが行う。いずれも失敗時は自動再実行しない。
- 初回起動で、run内の短時間の`sumo --version`を外部SUMOと誤検知し、12本投入後に
  新規補充が停止した。投入済みrunは中断せず完了させ、
  `scripts/run_universal_lambda095_overlap_filler.py`が実行中runを出力パスで除外して空き枠へ
  未投入runを補充する。その後、`scripts/resume_holdout_after_overlap_filler_20261127.sh`が
  成功済みmanifestを再監査し、未投入runだけを再開する。失敗または未完了のper-run
  manifestがあれば自動再実行せず停止する。
- 初回fillerは終了直後のゾンビプロセス`[sumo]`を外部SUMOと誤検知し、2026-11-27
  21:05 JSTに新規補充だけを停止した。実行中runは継続し、プロセス状態`Z`を枠数から
  除外する修正版filler v2が成功済み・実行中runを除外して引き継ぐ。シミュレーションは
  再実行しない。
- 先行Eval.7診断4本は全run成功したが、初回監査unitはmanifestに存在しない
  `requesting_speed` / `accepting_speed`を参照して終了コード1となった。シミュレーションは
  再実行せず、既存集計と同じく`stderr.log`末尾の名前付き速度を読むよう監査を修正して
  同じartifactを再監査する。
- schedulerは `scripts/run_universal_lambda095_holdout.py`。定数・キュー順・固定入力ハッシュ・
  Python/SUMO版・開始時Git clean・既存SUMO 0をpreflightで検査する。
- 完了後は `scripts/finalize_universal_lambda095_holdout.py`をsystem Pythonで実行し、
  60 runの完全性、対応入力、形状別差と等重み集計、圧縮復元を監査する。
- 完了後はmanifest、metrics、物理衝突、固定入力hash、診断artifact、checkpoint、
  ログを監査する。診断JSONLとcheckpointは可逆圧縮を復元検査する。
- Gitには実験記録、manifest、compact metrics、比較summary、選定図を保存する。
  大容量生artifactの外部保存先は未決定のため、検証済みコピができるまでUbuntu上に保持する。

## 実行状態

- 初回unitは`mcs-universal-lambda095-final-holdout-20261127.service`、invocation
  `4287509a96fe4a9695b4b2583c524b35`、2026-11-27 16:32:45 JST開始。
- 空き枠補充unitは`mcs-universal-lambda095-overlap-filler-20261127.service`、invocation
  `0a9d716e2e064f248e32ef7a8c1ab358`。終了後の再監査・集計unitは
  `mcs-universal-lambda095-final-holdout-resume-v2-20261127.service`、invocation
  `ed2d869e69674092b961bcd8c136ec15`。
- 先行Eval.7診断4本はexit code 0、source unchanged、600秒到達、物理衝突0、必須artifact完備。
  修正版監査`diagnostic-audit.json`は`ok: true`、run count 4。監査修正commitは
  `03e34cf86`で、シミュレーションの再実行はしていない。
- λ=0.95−0.525の対応差はseed 37で全車速度−0.6714 m/s、合流側−1.1052 m/s、
  本線側+0.9038 m/s、停止時間+2881.8 s。seed 38では全車速度+0.9922 m/s、
  合流側+0.5063 m/s、本線側+2.1525 m/s、停止時間−722.7 s。2 seedで符号が揃わず、
  700/1000条件の遅延改善はseed依存である。この診断だけで1000/1000の正式holdoutを
  変更せず、事前登録どおり継続する。
- sgnlabのroot filesystemが100%で、監査のbuffered stdout flushが終了コード120になった。
  監査JSON自体は別ディスクへ正常保存され、unbuffered再確認は終了コード0。古いsmoke一時物
  77MBを削除せず`/media/yamada/UbuntuData/home-yamada/Documents/卒業研究/mcs-tiv-temp-backup/20261127-root-full`
  へ退避したが、一般ユーザー向け空きはまだ0。ChatGPTアプリもユーザー許可後に正常終了したが
  容量は変わらず、当初の「削除済みバイナリ保持」という推定は誤りだった。再取得可能なAPT
  cache約614MBの清掃にはsudoが必要。実験artifact先のUbuntuDataは約1.1TB空き。

## 制約と判定

- 本holdoutはλ=0.95の独立性能評価であり、追加のλ選定には使わない。
- 3形状で山下TIVtepをすべて上回らない場合も、不都合な形状を除外せず結果として保持する。
- 実行結果と結論は未検証。
