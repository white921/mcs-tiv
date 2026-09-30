# Upstream history

## インポート元

- 元URL: `https://github.com/TaikiKunimoto/sumo-mcs.git`
- 作業スナップショット: `sumo-mcs-11`
- 移行日: 2026-09-30
- スナップショット取得時のHEAD: `d9b9647b57a6d7d05f1f9e092f116731da9e50e6`

2026年9月30日時点で元URLはGitHubから参照できません。
そのため、ローカルに残っていたGitオブジェクトと作業フォルダから履歴を保存しました。

## 保存ブランチ

| 現在のブランチ | 元の意味 | コミット |
|---|---|---|
| `upstream/sumo-mcs-main` | 元リポジトリのマージ後main | `e22fd73` |
| `upstream/feature-1121` | 元の `feature/1121` | `11aa305` |
| `upstream/feature-1124` | 元の `feature/1124` | `d9b9647` |
| `archive/pre-mcs-tiv-migration` | 移行前の `v2c-ramp-merging` | `8813721` |

## ローカルで確認できたPR履歴

- PR #1: `feature/1121` をmainへマージ
  - マージコミット: `a46e97b`
  - タイトル: `いったん動いた`
- PR #2: `feature/1124` をmainへマージ
  - マージコミット: `e22fd73`
  - タイトル: `本線合流ができるところまでなおした`

## Git管理外だった差分

元の `.gitignore` は `*` で全ファイルを無視する状態でした。
このため、以下を含むTIV関連ファイルは元のブランチ履歴には入っていません。

- `junction/junction_three_agree.py`
- `func/cav_three_junction.py`
- `func/cav_three_junction_bus.py`
- `junction/junction_four_agree.py`
- `func/cav_four_junction.py`
- `func/cav_four_junction_bus.py`

これらは移行時の `main` で初めて正式にGit追跡対象にしました。

## Issueについて

GitHub IssueはGitオブジェクトに含まれません。
元リポジトリにアクセスできないため、元Issueの本文・コメント・ラベルは復元できていません。
将来Issueのエクスポートが得られた場合は、このリポジトリに追加移行できます。
