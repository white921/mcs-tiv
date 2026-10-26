# coding: utf-8
#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import print_function
import os
import sys
import optparse
from collections import deque
from contextlib import redirect_stdout
import numpy as np
import datetime
import csv
import time


# the directory in which this script resides
THISDIR = os.path.dirname(__file__)
sys.path.append("../PathPlanning/FrenetOptimalTrajectory/")
sys.path.append("../func")
from cav_merge2512 import CAV
from cav_merge2512_bus import CAV_bus
from animation_merge import Animation
from frenet_merge import emergency_stop
from fixed_vehicle_inputs import load_fixed_vehicle_input
import evaluation_metrics
import diagnostic_trace
import deceleration_prediction
import mcs_checkpoint
import thesis_tiv

# we need to import python modules from the $SUMO_HOME/tools directory
# If the the environment variable SUMO_HOME is not set, try to locate the python modules relative to this script
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")
import traci  # noqa
from sumolib import checkBinary  # noqa


simulation_time = 600.0
bus_share = 0.0
bus_allocation = "fixed"
diagnostic_stop_time = None
fixed_input_path = None
fixed_input_schedule = None
resume_checkpoint = None
# matplotlibによる描画
show_animation = False
import random

vehicle_type_rng = random.Random()


def mean_or_nan(values):
    if np.isscalar(values):
        return float(values)
    if len(values) == 0:
        return float("nan")
    return float(np.mean(values))

vehicle_instance = []
nonCAV_list = []
veh_id = 1
veh_id_bus = 0
alpha = 0.0

departTime_lane0 = []
departTime_lane1 = []
departTime_lane2 = []
vehicleType_lane0 = deque()
vehicleType_lane1 = deque()

count_accept_utility = 0
count_refuse_utility = 0
count_refuse_physics = 0
count_send_PT = 0
count_send_DT = 0
count_send_AT = 0

count_desired = [0, 0, 0, 0]
count_accepted = [0, 0, 0, 0]


count_Distribution = False

CHECKPOINT_RUN_FIELDS = (
    "sumo_time", "next_central_path_server", "cav0_speed", "cav1_speed",
    "cav0_300s", "cav1_300s", "cav0_bus_speed", "cav1_bus_speed",
    "cav0_bus_300s", "cav1_bus_300s", "cav0_dist", "cav1_dist",
    "total_collision_time", "total_caution_time", "get_parameter",
    "get_followrange",
)


def _checkpoint_globals():
    return {
        "vehicle_instance": vehicle_instance,
        "nonCAV_list": nonCAV_list,
        "veh_id": veh_id, "veh_id_bus": veh_id_bus,
        "fixed_input_schedule": fixed_input_schedule,
        "depart_times": [departTime_lane0, departTime_lane1, departTime_lane2],
        "vehicle_types": [vehicleType_lane0, vehicleType_lane1],
        "counters": [count_accept_utility, count_refuse_utility,
                     count_refuse_physics, count_send_PT, count_send_DT,
                     count_send_AT],
        "count_desired": count_desired,
        "count_accepted": count_accepted,
        "random_state": random.getstate(),
        "vehicle_type_random_state": vehicle_type_rng.getstate(),
    }


def _restore_checkpoint_globals(state):
    global vehicle_instance, nonCAV_list, veh_id, veh_id_bus, fixed_input_schedule
    global departTime_lane0, departTime_lane1, departTime_lane2
    global vehicleType_lane0, vehicleType_lane1
    global count_accept_utility, count_refuse_utility, count_refuse_physics
    global count_send_PT, count_send_DT, count_send_AT
    vehicle_instance = state["vehicle_instance"]
    nonCAV_list = state["nonCAV_list"]
    veh_id, veh_id_bus = state["veh_id"], state["veh_id_bus"]
    fixed_input_schedule = state["fixed_input_schedule"]
    departTime_lane0, departTime_lane1, departTime_lane2 = state["depart_times"]
    vehicleType_lane0, vehicleType_lane1 = state["vehicle_types"]
    (count_accept_utility, count_refuse_utility, count_refuse_physics,
     count_send_PT, count_send_DT, count_send_AT) = state["counters"]
    count_desired[:] = state["count_desired"]
    count_accepted[:] = state["count_accepted"]
    random.setstate(state["random_state"])
    vehicle_type_rng.setstate(state["vehicle_type_random_state"])


def build_vehicle_type_schedules(lane_counts, target_bus_share):
    """Create shuffled lane schedules with the nearest possible total bus share."""
    if not 0 <= target_bus_share <= 1:
        raise ValueError("bus share must be between 0 and 1")

    total_vehicles = sum(lane_counts)
    target_bus_count = int(total_vehicles * target_bus_share + 0.5)
    bus_counts = [int(count * target_bus_share) for count in lane_counts]
    remaining_buses = target_bus_count - sum(bus_counts)
    if remaining_buses:
        lane_order = list(range(len(lane_counts)))
        vehicle_type_rng.shuffle(lane_order)
        lane_order.sort(
            key=lambda index: lane_counts[index] * target_bus_share - bus_counts[index],
            reverse=True,
        )
        for index in lane_order[:remaining_buses]:
            bus_counts[index] += 1

    schedules = []
    for count, buses in zip(lane_counts, bus_counts):
        schedule = ["Bus"] * buses + ["Car"] * (count - buses)
        if 0 < buses < count:
            vehicle_type_rng.shuffle(schedule)
        schedules.append(deque(schedule))
    return schedules


def select_vehicle_type(schedule):
    """Select a vehicle type without changing the paper's random draw order."""
    if bus_share <= 0:
        return "Car"
    draw = random.choice(["Bus", "Car", "Car", "Car"])
    if bus_allocation == "paper-random25":
        return draw
    return schedule.popleft()

#初期設定（障害物の配置など）
def set_environment(inflow_0=750, inflow_1=750):
    global vehicle_instance
    global veh_id
    global departTime_lane0, departTime_lane1, departTime_lane2
    global vehicleType_lane0, vehicleType_lane1
    global fixed_input_schedule

    #合流地点を示すための障害物
    traci.vehicle.add(vehID="stone", routeID="main", typeID="CAV_0", departLane="0", departPos="305.0", departSpeed="0")
    traci.vehicle.setColor("stone", (250, 250, 250))
    traci.vehicle.setSpeed(vehID="stone", speed=0)
    nonCAV_list.append("stone")

    if fixed_input_path is not None:
        fixed_input_schedule = load_fixed_vehicle_input(
            fixed_input_path,
            expected_case="eval7",
            expected_seed=seed,
            expected_duration_s=600.0,
            expected_flows_vph={"requesting": inflow_0, "accepting": inflow_1},
            expected_bus_share=bus_share,
            prefix_duration_s=simulation_time,
        )
        departTime_lane0 = fixed_input_schedule.departure_times("requesting")
        departTime_lane1 = fixed_input_schedule.departure_times("accepting")
        print(departTime_lane0)
        print(departTime_lane1)
        return

    k_0 = int((simulation_time/3600)*inflow_0)
    k_1 = int((simulation_time/3600)*inflow_1)

    # 車両の合流時刻を決定
    departTime_lane0 = sorted(random.sample(range(int(simulation_time/2.0)), k_0))
    departTime_lane1 = sorted(random.sample(range(int(simulation_time/2.0)), k_1))
    # departTime_lane2 = sorted(random.sample(range(int(simulation_time/2.0)), k))

    #departTime_lane0 = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    #SdepartTime_lane1 = [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]    

    # 2秒以上開けて流入
    departTime_lane0 = [round((n*2.0), 1)+0.1 for n in departTime_lane0]
    departTime_lane1 = [round((n*2.0), 1)+0.1 for n in departTime_lane1]
    vehicleType_lane0, vehicleType_lane1 = build_vehicle_type_schedules(
        [k_0, k_1], bus_share
    )
    # departTime_lane2 = [round((n*2.0), 1)+0.1 for n in departTime_lane2]

    print(departTime_lane0)
    print(departTime_lane1)
    # print(departTime_lane2)


def add_vehicle(alpha):
    global veh_id
    global veh_id_bus
    global departTime_lane0, departTime_lane1, departTime_lane2
    global vehicleType_lane0, vehicleType_lane1
    sumo_time = traci.simulation.getTime()

    alpha = float(alpha)
    # if sumo_time in departTime_lane1: 本線（受け入れ）
    if sumo_time in departTime_lane1:
        if fixed_input_schedule is None:
            kind = select_vehicle_type(vehicleType_lane1)
        else:
            kind = fixed_input_schedule.pop("accepting", sumo_time)["vehicle_type"]
        #kind = "Car"
        if kind == "Car":
            traci.vehicle.add(vehID=str(veh_id), routeID="main", typeID="CAV_1", departLane="1", departPos="base", departSpeed="5")
            instance = CAV(veh_id, alpha, withAgree=True)
            veh_id += 2
            count_accepted[1] += 1
        elif kind == "Bus":
            traci.vehicle.add(vehID=str(veh_id_bus), routeID="main", typeID="CAV_1_bus", departLane="1", departPos="base", departSpeed="5")
            instance = CAV_bus(veh_id_bus, alpha, withAgree=True)
            veh_id_bus += 2
            count_accepted[0] += 1

        vehicle_instance.append(instance)
        

    # if sumo_time in departTime_lane0:
    if sumo_time in departTime_lane0:
        if fixed_input_schedule is None:
            kind = select_vehicle_type(vehicleType_lane0)
        else:
            kind = fixed_input_schedule.pop("requesting", sumo_time)["vehicle_type"]
        #kind = "Car"
        if kind == "Car":
            traci.vehicle.add(vehID=str(veh_id), routeID="main", typeID="CAV_0", departLane="0", departPos="base", departSpeed="5")
            instance = CAV(veh_id, alpha, withAgree=True)
            veh_id += 2
            count_desired[1] += 1
        elif kind == "Bus":
            traci.vehicle.add(vehID=str(veh_id_bus), routeID="main", typeID="CAV_0_bus", departLane="0", departPos="base", departSpeed="5")
            instance = CAV_bus(veh_id_bus, alpha, withAgree=True)
            veh_id_bus += 2
            count_desired[0] += 1
        vehicle_instance.append(instance)
        


def run(alpha='0.0', inflow_0=750, inflow_1=750, quiet=False, save_statistics=True):
    """execute the TraCI control loop"""
    global vehicle_instance
    global count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT
    sumo_time = 0
    split_time = round(simulation_time / 2, 1)
    central_path_server = []
    next_central_path_server = []
    cav0_speed = []
    cav1_speed = []
    cav0_300s = 0
    cav1_300s = 0

    cav0_bus_speed = []
    cav1_bus_speed = []
    cav0_bus_300s = 0
    cav1_bus_300s = 0


    cav0_dist = [0]*168
    cav1_dist = [0]*168
    total_collision_time = 0
    total_caution_time = 0
    get_parameter = 0
    get_followrange = 0

    #初期設定（障害物の配置など）
    diagnostic_trace.initialize()
    if resume_checkpoint:
        checkpoint_manifest, checkpoint_payload, _ = mcs_checkpoint.load(
            resume_checkpoint)
        if checkpoint_manifest.get("case") != "eval7":
            raise ValueError("resume checkpoint is not an Eval.7 checkpoint")
        _restore_checkpoint_globals(checkpoint_payload["globals"])
        mcs_checkpoint.restore_shared_modules(
            checkpoint_payload["modules"], evaluation_metrics,
            deceleration_prediction, thesis_tiv)
        restored = checkpoint_payload["run"]
        sumo_time = restored["sumo_time"]
        next_central_path_server = restored["next_central_path_server"]
        cav0_speed, cav1_speed = restored["cav0_speed"], restored["cav1_speed"]
        cav0_300s, cav1_300s = restored["cav0_300s"], restored["cav1_300s"]
        cav0_bus_speed = restored["cav0_bus_speed"]
        cav1_bus_speed = restored["cav1_bus_speed"]
        cav0_bus_300s = restored["cav0_bus_300s"]
        cav1_bus_300s = restored["cav1_bus_300s"]
        cav0_dist, cav1_dist = restored["cav0_dist"], restored["cav1_dist"]
        total_collision_time = restored["total_collision_time"]
        total_caution_time = restored["total_caution_time"]
        get_parameter = restored["get_parameter"]
        get_followrange = restored["get_followrange"]
        actual_time = traci.simulation.getTime()
        if abs(actual_time - sumo_time) > 1e-6:
            raise ValueError(
                f"SUMO/MCS checkpoint time mismatch: {actual_time} != {sumo_time}")
        mcs_checkpoint.restore_vehicle_controls(traci, vehicle_instance)
        # SUMO state files preserve the obstacle vehicle itself, but not the
        # outstanding TraCI speed command that keeps it stationary.
        if "stone" in traci.vehicle.getIDList():
            traci.vehicle.setSpeed("stone", 0)
    else:
        set_environment(inflow_0, inflow_1)
    file = alpha + '_' + str(inflow_0) + '_' + str(inflow_1)
    animator = Animation(file)

    #シミュレーション開始
    run_until = diagnostic_stop_time if diagnostic_stop_time is not None else simulation_time
    while sumo_time < run_until:
        step_started = time.perf_counter()
        traci.simulationStep()
        sumo_time = traci.simulation.getTime()
        evaluation_metrics.observe_sumo_safety(traci, sumo_time)
        print("\nTIME:", sumo_time)
        if sumo_time % 20 == 0:
            now = datetime.datetime.now().time() # 実時刻を取り込んでいる
            print("TIME:", sumo_time, now, "alpha", alpha, "seed", seed, "inflow_0", inflow_0, "inflow_1", inflow_1, file = sys.stderr)

        arrived_list = traci.simulation.getArrivedIDList()
        running_list = traci.vehicle.getIDList()

        ob = np.array([[302.5, -7.3]]) # obstacles lists (車両で障害物を表現しているため、幅と長さを考慮した位置)
        central_path_server = [path for path in next_central_path_server if path.vehID in running_list]
        next_central_path_server = []
        poplist = []
        
        #non-CAVは等加速度で動くと仮定して経路を生成
        stone_pos = (299.5, -8.0)
        if sumo_time > 2:
            print("Stonepos: ", stone_pos)
        #stone_pos = traci.vehicle.getPosition("stone") #応急処置
        print("Stonepos: ", stone_pos)
        stonePath = emergency_stop(302.5, 0.0, stone_pos[1], route=None)[0]
        stonePath.pathID = "stone"
        stonePath.vehID = "stone"
        stonePath.type = "planned"
        stonePath.t = [round(n+sumo_time, 1) for n in stonePath.t]
        central_path_server.append(stonePath)
        

        print([i.pathID for i in central_path_server])
        print([i.type for i in central_path_server])
        #CAV各車両の動作
        for index, ins in enumerate(vehicle_instance):
            # シミュレーション範囲を出た車両をリスト化
            if ins.id in arrived_list:
                poplist.append(index)
                total_collision_time += ins.returnCollisionTime()
                total_caution_time += ins.returnCautionTime()
                get_parameter = ins.returnParameter()
                get_followrange = ins.returnFollowRange()
                continue
            # 混雑でまだ道路に入れていない車両はパス
            elif ins.id not in running_list:
                continue

            #他車両の情報を収集
            ins.receiveMCM(central_path_server)

            #自車両の情報（位置や速度）を更新
            ins.updateStatus(running_list)
            if ins.leadPath:
                print("\tvehid:", ins.id, "status", ins.status, "current speed", '{:.5g}'.format(ins.speed), "route", ins.route, "road", ins.road, "leader", ins.leader, "pos x,y", '{:.5g}'.format(ins.pos_x), '{:.5g}'.format(ins.pos_y), "leadPath", ins.leadPath.pathID)
            else:
                print("\tvehid:", ins.id, "status", ins.status, "current speed", '{:.5g}'.format(ins.speed), "route", ins.route, "road", ins.road, "leader", ins.leader, "pos x,y", '{:.5g}'.format(ins.pos_x), '{:.5g}'.format(ins.pos_y))

            #自車両の経路を更新
            ins.updatePlannedPath(ob)

            #自車両の希望経路を更新
            if ins.status not in ["lanechange"]:
                ins.updateDesiredPath(ob)
                
            #自車両の希望経路が他車両の経路と衝突しないか判定
            collision_list_desired = []
            if ins.desiredPaths:
                collision_list_desired, _ = ins.checkPathCollision(ins.desiredPaths[0], ins.receivedPaths, s_type="planned")
                if collision_list_desired:
                    ins.desiredPaths[0].negotiationID = [i["collideID"] for i in collision_list_desired]
                    ins.desiredPaths[0].negotiationID.sort()
                    if ins.status == "lanechange":
                        ins.status = None
                        
                # 衝突しない場合は希望経路を通る
                elif (len(collision_list_desired) == 0 and ins.status != "lanechange") or (ins.status == "lanechange"):
                    ins.plannedPath = ins.desiredPaths[0]
                    ins.plannedPath.type = "planned"
                    ins.desiredPaths = None
                    ins.status = "lanechange"
                    print("\tchange to desired path")
            
            # SUMO上での車線変更
            if ins.status == "lanechange":
                ins.judgeAndDoLaneChange()

            #予定経路に基づき速度調整
            ins.executionDrive()

            #経路情報を集中サーバーへ送信
            ins.sendMCM(next_central_path_server)

            ins.checkPassJunction()

            au, ru, rp, sp, sd, sa = ins.getStatistics()
            count_accept_utility += au
            count_refuse_utility += ru
            count_refuse_physics += rp
            count_send_PT += sp
            count_send_DT += sd
            count_send_AT += sa

            if ins.type == "Car":
                if ins.typeID in ("CAV_0", "CAV_0_bus"):
                    cav0_speed.append(ins.speed)
                if ins.typeID in ("CAV_1", "CAV_1_bus"):
                    cav1_speed.append(ins.speed)
                if sumo_time == split_time:
                    cav0_300s = len(cav0_speed)
                    cav1_300s = len(cav1_speed)
                if ins.passjunctionstatus == "now":
                    if ins.typeID in ("CAV_0", "CAV_0_bus"):
                        count_desired[3] += 1
                    elif ins.typeID in ("CAV_1", "CAV_1_bus"):
                        count_accepted[3] += 1

            
            if ins.type == "Bus":
                if ins.typeID in ("CAV_0", "CAV_0_bus"):
                    cav0_bus_speed.append(ins.speed)
                if ins.typeID in ("CAV_1", "CAV_1_bus"):
                    cav1_bus_speed.append(ins.speed)
                if sumo_time == split_time:
                    cav0_bus_300s = len(cav0_bus_speed)
                    cav1_bus_300s = len(cav1_bus_speed)
                if ins.passjunctionstatus == "now":
                    if ins.typeID in ("CAV_0", "CAV_0_bus"):
                        count_desired[2] += 1
                    elif ins.typeID in ("CAV_1", "CAV_1_bus"):
                        count_accepted[2] += 1
            
            
            if(count_Distribution and sumo_time > 30):
                if ins.typeID in ("CAV_0", "CAV_0_bus"):
                    cav0_dist[int(round(ins.speed,1)*10)] += 1
                if ins.typeID in ("CAV_1", "CAV_1_bus"):
                    cav1_dist[int(round(ins.speed,1)*10)] += 1

        # Record actual 0.1-second motion after all controllers have updated.
        # This is a no-op unless MCS_EVALUATION_AUDIT is configured.
        observed = [ins for ins in vehicle_instance if ins.id in running_list]
        evaluation_metrics.observe(
            observed, sumo_time,
            {str(ins.id): traci.vehicle.getAllowedSpeed(ins.id) for ins in observed})
        diagnostic_trace.record_vehicle_states(observed, sumo_time, traci)

        #車両インスタンスを削除
        if poplist:
            for i in sorted(poplist, reverse=True):
                vehicle_instance.pop(i)

        if show_animation:
            animator.path_animation(vehicle_instance, time=sumo_time, objects=ob)

        # 車両の新規流入
        add_vehicle(alpha)
        diagnostic_trace.record_runtime(
            sumo_time, {}, len(observed), time.perf_counter() - step_started)
        checkpoint_root = os.environ.get("MCS_CHECKPOINT_DIR")
        if checkpoint_root and mcs_checkpoint.is_due(sumo_time):
            local_values = locals()
            run_state = {name: local_values[name]
                         for name in CHECKPOINT_RUN_FIELDS}
            mcs_checkpoint.save(
                traci, checkpoint_root, sumo_time,
                {"globals": _checkpoint_globals(), "run": run_state,
                 "modules": mcs_checkpoint.capture_shared_modules(
                     evaluation_metrics, deceleration_prediction, thesis_tiv)},
                {"case": "eval7", "seed": int(seed), "alpha": int(alpha),
                 "fixed_input_path": fixed_input_path})

    statistics_path = "./statistics/acceptance.csv" if save_statistics else os.devnull
    with open(statistics_path, "a", encoding='utf-8') as f:
        #text = "{},{},{},{},{},{},{},{},{},{}\n".format(seed, alpha, inflow_0, inflow_1, count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT)
        text = "{},{},{},{},{},{},{},{},{},{},{}\n".format("seed", "alpha", "inflow_desired", "inflow_accepted", "accept_utility", "refuse_utility", "refuse_physics", "send_PT", "send_DT", "send_AT", "date_time")
        f.write(text)
        text = "{},{},{},{},{},{},{},{},{},{},{}\n".format(seed, alpha, inflow_0, inflow_1, count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT, datetime.datetime.now())
        f.write(text)

        text = "{},{},{},{},{}\n".format(" ", "desired", "accepted", "pass_desired", "pass_accepted")
        f.write(text)
        text = "{},{},{},{},{}\n".format("Bus", count_desired[0], count_accepted[0], count_desired[2], count_accepted[2])
        f.write(text)
        text = "{},{},{},{},{}\n".format("Car", count_desired[1], count_accepted[1], count_desired[3], count_accepted[3])
        f.write(text)

        text = "{},{},{},{},{},{},{},{}\n".format(
            " ",
            "all",
            "desired",
            "accepted",
            f"desired[0-{split_time:g}]",
            f"accepted[0-{split_time:g}]",
            f"desired[{split_time:g}-{simulation_time:g}]",
            f"accepted[{split_time:g}-{simulation_time:g}]",
        )
        f.write(text)
        text = "{},{},{},{},{},{},{},{}\n".format("Bus", round(mean_or_nan(cav0_bus_speed+cav1_bus_speed),4), round(mean_or_nan(cav0_bus_speed),4), round(mean_or_nan(cav1_bus_speed),4), round(mean_or_nan(cav0_bus_speed[:cav0_bus_300s]),4), round(mean_or_nan(cav1_bus_speed[:cav1_bus_300s]),4), round(mean_or_nan(cav0_bus_speed[cav0_bus_300s:]),4), round(mean_or_nan(cav1_bus_speed[cav1_bus_300s:]),4))
        f.write(text)
        text = "{},{},{},{},{},{},{},{}\n".format("Car", round(mean_or_nan(cav0_speed+cav1_speed),4), round(mean_or_nan(cav0_speed),4), round(mean_or_nan(cav1_speed),4), round(mean_or_nan(cav0_speed[:cav0_300s]),4), round(mean_or_nan(cav1_speed[:cav1_300s]),4), round(mean_or_nan(cav0_speed[cav0_300s:]),4), round(mean_or_nan(cav1_speed[cav1_300s:]),4))
        f.write(text)
        text = "{},{},{},{},{},{},{},{}\n".format("All", round(mean_or_nan(cav0_speed+cav0_bus_speed+cav1_speed+cav1_bus_speed),4), round(mean_or_nan(cav0_speed+cav0_bus_speed),4), round(mean_or_nan(cav1_speed+cav1_bus_speed),4), round(mean_or_nan(cav0_speed[:cav0_300s]+cav0_bus_speed[:cav0_bus_300s]),4), round(mean_or_nan(cav1_speed[:cav1_300s]+cav1_bus_speed[:cav1_bus_300s]),4), round(mean_or_nan(cav0_speed[cav0_300s:]+cav0_bus_speed[cav0_bus_300s:]),4), round(mean_or_nan(cav1_speed[cav1_300s:]+cav1_bus_speed[cav1_bus_300s:]),4))
        f.write(text)

        text = "{},{},{},{},{},{},{},{}\n".format("---", "↑All", "---", "---", "---", "---", "---", "---")
        f.write(text)

             

    summary_stream = sys.stderr if quiet else sys.stdout
    all_vehicle_speed = cav0_speed + cav0_bus_speed + cav1_speed + cav1_bus_speed
    generated_bus_count = count_desired[0] + count_accepted[0]
    generated_car_count = count_desired[1] + count_accepted[1]
    generated_vehicle_count = generated_bus_count + generated_car_count
    actual_bus_share = generated_bus_count / generated_vehicle_count if generated_vehicle_count else float("nan")

    print(
        f"vehicle_mix : Bus {generated_bus_count} Car {generated_car_count} "
        f"bus_rate {actual_bus_share * 100:.2f}%",
        file=summary_stream,
    )
    print("requesting_speed :", mean_or_nan(cav0_speed+cav0_bus_speed), file=summary_stream)
    print("accepting_speed :", mean_or_nan(cav1_speed+cav1_bus_speed), file=summary_stream)
    print("all_speed :", mean_or_nan(all_vehicle_speed), file=summary_stream)
    
    print("cav0_speed (30s ~ end) :", np.mean(cav0_speed[cav0_300s:]))
    print("cav1_speed (30s ~ end) :", np.mean(cav1_speed[cav1_300s:]))
    print("all_speed (30s ~ end) :", np.mean(cav0_speed[cav0_300s:]+cav1_speed[cav1_300s:]))
    print("cav0_bus_speed (30s ~ end) :", np.mean(cav0_bus_speed[cav0_bus_300s:]))
    print("cav1_bus_speed (30s ~ end) :", np.mean(cav1_bus_speed[cav1_bus_300s:]))
    print("all_bus_speed (30s ~ end) :", np.mean(cav0_bus_speed[cav0_bus_300s:]+cav1_bus_speed[cav1_bus_300s:]))
    print(
        "sumo_physical_collision_episodes :",
        int(evaluation_metrics.COUNTS.get("sumo_unique_collision_episodes", 0)),
    )
    print(
        "sumo_physical_collision_steps :",
        int(evaluation_metrics.COUNTS.get("sumo_collision_steps", 0)),
    )
    print("controller_proximity_counter :", total_collision_time)
    print("caution :", total_caution_time)
    if(count_Distribution):
        palameter = [alpha, seed, inflow_0, inflow_1, simulation_time, get_followrange, get_parameter, np.mean(cav0_speed), np.mean(cav1_speed), np.mean(all_speed), np.mean(cav0_speed_after_30s), np.mean(cav1_speed_after_30s), np.mean(all_speed_after_30s)]
        #pala_dist = palameter + cav0_dist + cav1_dist
        with open("./statistics/speed_distribution.csv", "a", encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(palameter)
            writer.writerow(cav0_dist)
            writer.writerow(cav1_dist)
    

    sys.stdout.flush()
    traci.close()


def get_options():
    """define options for this script and interpret the command line"""
    optParser = optparse.OptionParser()
    optParser.add_option("--nogui", action="store_true",
                         default=False, help="run the commandline version of sumo")
    optParser.add_option("--duration", type="float", default=600.0, help="duration of the simulation")
    optParser.add_option("--stop-time", type="float", default=None, help="stop early while retaining the full-duration input schedule")
    optParser.add_option("--bus-allocation", type="choice", choices=["fixed", "paper-random25"], default="fixed", help="fixed share or the paper artifact's per-vehicle 25%% draw")
    optParser.add_option("--bus-share", type="float", default=0.0, help="share of buses from 0 to 1")
    optParser.add_option("--fixed-input", type="string", default=None,
                         help="versioned JSONL vehicle schedule; bypasses runtime input randomness")
    optParser.add_option("--quiet", action="store_true", default=False, help="suppress verbose per-step output")
    optParser.add_option("--no-save", action="store_true", default=False, help="do not append the run to statistics CSV")
    optParser.add_option("--deceleration-shadow", action="store_true", default=False,
                         help="record read-only deceleration-propagation comparisons")
    optParser.add_option("--deceleration-active", action="store_true", default=False,
                         help="experimentally use deceleration-propagation decisions")
    optParser.add_option("--resume-checkpoint", type="string", default=None,
                         help="resume from a paired SUMO/MCS checkpoint directory")
    options, args = optParser.parse_args()
    if len(args) != 4:
        optParser.error("expected: alpha seed inflow_requesting inflow_accepting")
    if not 0 <= options.bus_share <= 1:
        optParser.error("--bus-share must be between 0 and 1")
    if options.stop_time is not None and not 0 < options.stop_time <= options.duration:
        optParser.error("--stop-time must be greater than 0 and no greater than --duration")
    if options.bus_allocation == "paper-random25" and options.bus_share not in (0.0, 0.25):
        optParser.error("--bus-allocation paper-random25 requires --bus-share 0 or 0.25")
    return options, args


# this is the main entry point of this script
if __name__ == "__main__":
    # load whether to run with or without GUI
    options, args = get_options()
    if options.deceleration_shadow or options.deceleration_active:
        selected_mode = "active" if options.deceleration_active else "shadow"
        if os.environ.get("MCS_DECELERATION_MODE", "off") not in ("off", selected_mode):
            raise ValueError("requested deceleration mode conflicts with MCS_DECELERATION_MODE")
        os.environ["MCS_DECELERATION_MODE"] = selected_mode
        import deceleration_prediction
        deceleration_prediction.configure(selected_mode)
    simulation_time = options.duration
    diagnostic_stop_time = options.stop_time
    bus_share = options.bus_share
    bus_allocation = options.bus_allocation
    fixed_input_path = options.fixed_input
    resume_checkpoint = options.resume_checkpoint
    if not options.quiet:
        print(args)
    alpha = str(args[0])
    seed = args[1]
    if fixed_input_path is None:
        random.seed(seed)
        vehicle_type_rng.seed(f"{seed}:vehicle-types")
    inflow_0 = int(args[2])
    inflow_1 = int(args[3])

    # this script has been called from the command line. It will start sumo as a server, then connect and run
    if options.nogui:
        sumoBinary = checkBinary('sumo')
    else:
        sumoBinary = checkBinary('sumo-gui')

    # this is the normal way of using traci. sumo is started as a subprocess and then the python script connects and runs
    sumo_command = [sumoBinary, '-c', os.path.join('merge.sumocfg')]
    if os.environ.get("MCS_CHECKPOINT_DIR") or resume_checkpoint:
        sumo_command.extend([
            "--save-state.precision", "16",
            "--save-state.rng", "true",
        ])
    if resume_checkpoint:
        _, _, sumo_state = mcs_checkpoint.load(resume_checkpoint)
        sumo_command.extend(["--load-state", str(sumo_state)])
    fcd_output = os.environ.get("MCS_FCD_OUTPUT")
    if fcd_output:
        sumo_command.extend([
            "--fcd-output", fcd_output,
            "--fcd-output.acceleration", "true",
            "--fcd-output.signals", "true",
        ])
    if options.quiet:
        sumo_command.extend(["--no-step-log", "true"])

    if options.quiet:
        with open(os.devnull, "w") as devnull:
            with redirect_stdout(devnull):
                traci.start(sumo_command)
                run(alpha, inflow_0, inflow_1, quiet=True, save_statistics=not options.no_save)
                vehicle_instance.clear()
    else:
        traci.start(sumo_command)
        run(alpha, inflow_0, inflow_1, save_statistics=not options.no_save)
