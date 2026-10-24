# Eval.3 減速伝播評価 HTML 化指示書

## 目的

`evaluation-report.json` と `evaluation-report.md` を根拠に、山下TIVtepと
減速伝播提案法を比較する静的HTMLレポートを作成する。結果の解釈を誇張せず、
「判断根拠を直接化してもマクロ交通性能を許容範囲で維持できたか」と
「予測器は実測をどの程度説明できたか」を分けて示すこと。

## 入力

- `evaluation-report.json`: 数値の唯一の正本。
- `evaluation-report.md`: 表記・要約の補助。
- 各実行の `eval3/seed-*/manifest.json`: 条件・再現性情報。
- 各実行の `eval3/seed-*/evaluation-metrics.json`: seed別の詳細。
- 提案法の `eval3/seed-*/deceleration-audit.json`: 判断数・提案/TIV判断一致数。

HTML中の数値はJSONから転記し、推測で補わない。

## 必須構成

1. **結論カード**
   - Eval.3の平均速度: TIVtep、提案法、対応差。
   - 「平均速度の優劣」と「判断根拠の直接性」は別の主張であること。
2. **実験条件**
   - T字路、α=7、流入400/400/400、paper-random25、600秒、seed 1〜5。
   - 同一seedの対応比較であること。
3. **seed別速度表と可視化**
   - `per_seed` を表と対応棒グラフまたはダンベル図で示す。
   - 平均だけでなくseedごとの増減を隠さない。
4. **予測精度**
   - `proposal_prediction_accuracy` の速度MAE、速度RMSE、10秒累積距離の絶対誤差、窓数、平均後続車数。
   - これは「選択した行動の実測との一致」であり、逆判断の実測ではないと明記する。
5. **安全・局所負担**
   - `traffic_metrics` の強い減速時間率、停止時間率、車両別free-flow shortfallの中央値・p95・最大値を、TIVtepと提案法で並べる。
   - `following_vehicle_shortfall` は、ライブ制御で前方車を持つ車両に限定した同じ分布であり、後続車への局所負担の比較に使う。
   - 許容速度shortfallは、各時刻のSUMO許容速度（道路・車種上限込み）と実速度の正の差を積分した代理指標であり、反実仮想距離損失そのものではないと明記する。バスに乗用車の上限を適用しない。
6. **判断差**
   - `proposal_decision_counts` の `decision_agreement`、`decision_disagreement`、`proposal_accept/reject`、`tiv_would_accept/reject` を示す。
   - 不一致は「提案法が実際に既存手法と異なる判断を出した」証拠である。
   - ただし、同一イベントで逆判断を実際に走らせていないので、不一致だけで因果的な優劣を断定しない。
7. **限界と次の評価**
   - JSONの `limitations` をそのまま反映する。
   - 反実仮想の優劣は、判断時点から承諾・拒否を2枝で再実行する実験が必要。

## 表現上の禁止事項

- 平均速度が高い／低いだけで「提案法が優れている」「安全である」と断定しない。
- 予測精度を反実仮想の正しさと呼ばない。
- 許容速度shortfallを提案法の累積距離損失と同一視しない。符号付きの純距離差も別指標として示す。
- 未計測の急減速回数、停止回数、反実仮想結果を作らない。

## 推奨する図

- seed別のTIVtep・提案法のダンベル図。
- 強い減速時間率・停止時間率の群別比較棒グラフ。
- 車両別free-flow shortfallの中央値／p95の比較。
- 予測速度MAE・RMSE・距離誤差の指標カード。
- 判断一致／不一致の積み上げ棒グラフ。

## 出力先

静的HTMLと必要なCSS/JSは、Git管理対象の `docs/` 配下へ追加する。既存の
`docs/deceleration-propagation-explainer.html` は説明資料なので、同ファイルを
大きく改変せず、評価レポートは別HTMLにする。
