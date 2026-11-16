# Ubuntu/SUMO実験の標準監視

ユーザーが「いつも通り監視」「監視もお願い」と依頼したときの正本手順。
個別実験のunit、worktree、結果パス、条件は対応する実験記録に書き、この文書には
共通の監視方法だけを置く。

## 監視基盤

1. 実行開始後、現在のCodexスレッドに紐づくheartbeat automationを作成または更新する。
2. 前景ターンをshellの`sleep`や連続pollで占有しない。
3. 各heartbeatは必ずUbuntuへSSHし、実状態を読み直す。過去の会話、ローカル記憶、
   前回heartbeatの値だけから状態を推測しない。
4. heartbeat automationを利用できない場合は、別方式へ黙って切り替えず、監視方法が
   変わることをユーザーへ伝える。

## 周期

- 実行中runの最遅simulation timeがシミュレーション時間の60%未満: 30分ごと。
- 最遅runが60%以上: 15分ごと。
- worker補充で新しいrunが開始し、最遅runが60%未満へ戻った場合: 30分ごとへ戻す。
- 完了、失敗、重大異常を確認した回は、次の周期を待たずその回で報告する。

## 複数交通量の実行順

- Eval.7で複数の交通量比を実行するときは、ユーザーが混在実行を明示しない限り、
  比率ごとに完了させてから次へ進む。
- 優先順は`300/1000 → 500/1000 → 700/1000 → 1000/1000 → 1200/1000`とする。
  安全な最大並列枠は、順番が最も早い未完了比率へ集中させる。
- この順序は今後の起動に適用し、すでに実行中のバッチの並列条件は変更しない。

## 各heartbeatで確認するもの

- 対象systemd unitのactive/failed/inactive状態
- batchの`experiment-manifest.json`、各runの`manifest.json`
- `runner.log`と各`runtime.jsonl`の最終更新
- 正常完了数、失敗数、方式別の最遅・中央値・最速simulation time
- 実際のSUMOプロセス数と予定並列数の整合
- runtime停滞、traceback、異常終了、ディスク不足などの重大異常

ユーザーへの進捗報告は、少なくとも完了数/総数、失敗数、最遅run、稼働数を簡潔に含める。
各heartbeatで必ずこの進捗をユーザーへ通知し、状態が正常・実質不変でも省略しない。

## 禁止事項

- seed、入力、方式、パラメータ、並列条件を監視中に変更しない。
- 失敗runを自動で再実行、差し替え、削除しない。
- 不完全結果をcommit/pushしない。
- SSH確認を省略して「正常」「完了」と報告しない。

## 完了時

1. 全runの`exit_code: 0`、`source_unchanged: true`、実行ソース、開始時clean、
   固定入力hash、Python/SUMO版を確認する。
2. 必須artifact、checkpoint、runner/stdout/stderr、物理衝突、致命的ログを監査する。
3. 実験記録を更新し、結果保存規則に従う。
4. systemd unit、SUMO/runner残存、一時物を確認して後始末する。
5. 結果と必要な証拠を保存・pushした後、cleanで非稼働の実験worktreeを削除する。
   branchとremote commitは残し、必要時に再作成する。未コミット変更、未追跡の実験証拠、
   active processまたはactive automationから参照されるworktreeは削除しない。
6. heartbeat automationを停止する。

## 現行の周期変更

過去の一部automationには60%以降を10分とする記録があるが、2026-11-15のユーザー指示に
より、現行標準は60%以降15分とする。
