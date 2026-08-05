# V2C Cooperative Ramp-Merging Simulation

SUMO上の3台協調ランプ合流を、MQTTを介したVehicle-to-Cloud-to-Vehicle通信として実行する研究用の最小実装です。

このリポジトリは、Liao et al. の4G/LTEベースV2C協調合流の**論理構成**をSUMOで再現するための土台です。元論文はアプリケーションプロトコルを明記していないため、本実装ではMQTTを研究上の比較対象として採用しています。

## Architecture

```text
SUMO vehicles
  ↕ TraCI
Vehicle adapter (mqtt_control.py)
  ↕ MQTT topics
Mosquitto broker
  ↕ MQTT topics
Cloud Controller (cloud_service.py)
```

車両アダプタは各シミュレーションステップで`MV1`、`MV2`、`RV`の状態をPublishします。クラウドは3台分の同時刻状態を受信して既存の合流制御を実行し、目標速度を含むコマンドを返します。車両アダプタはそれをTraCI経由でSUMOへ反映します。

## Quick start (Docker)

Docker DesktopまたはDocker EngineとDocker Composeがあれば、次だけでヘッドレス実験が実行されます。

```bash
docker compose up --build
```

実行後の要約は`SUMO/outputs/mqtt_run_summary.json`に保存されます。

停止とコンテナ削除は以下です。

```bash
docker compose down
```

## Local Ubuntu run

UbuntuでSUMO、Python 3、`paho-mqtt`、Mosquittoを用意している場合は、次のように分けて実行できます。

```bash
# 1. SUMOネットワーク生成（初回のみ）
netconvert --node-files SUMO/net/ramp.nod.xml \
  --edge-files SUMO/net/ramp.edg.xml \
  --output-file SUMO/net/ramp.net.xml

# 2. Broker
mosquitto -c docker/mosquitto.conf

# 3. Cloud Controller
python -m v2c.cloud_service

# 4. SUMO + vehicle adapter
python SUMO/scripts/mqtt_control.py --nogui
```

`--nogui`を外せば、SUMO GUIで車両挙動を確認できます。

## MQTT topics

| Direction | Topic | QoS |
| --- | --- | --- |
| Vehicle to cloud | `v2c/{run_id}/vehicle/{vehicle_id}/state` | 0 by default (configurable) |
| Cloud to vehicle adapter | `v2c/{run_id}/cloud/commands` | 1 |

位置・速度などの状態更新をQoS 0 / 1で切り替えられるようにしてあります。

## Next research steps

1. 通信なしの既存`control.py`とMQTT版の結果を比較する。
2. MQTT QoS 0 / 1を比較する。
3. 車両側リンクに遅延・損失・一時切断を加え、クラウド状態の鮮度と合流安全性を評価する。
4. 古い状態を廃棄する鮮度考慮方式を提案・比較する。

## Repository policy

SUMOの生成ネットワーク、実験出力、Python仮想環境はGit管理しません。ソース、道路定義、ルート、制御パラメータ、再現手順のみを管理します。
