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

# the directory in which this script resides
THISDIR = os.path.dirname(__file__)
sys.path.append("../PathPlanning/FrenetOptimalTrajectory/")
sys.path.append("../func")
from cav_three_junction import CAV
from cav_three_junction_bus import CAV_bus
from animation_junction import Animation
from frenet_merge import emergency_stop
from thesis_scenarios import choose_t_junction_route
import evaluation_metrics

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
bus_share = 0.25
bus_allocation = "fixed"
route_mode = "random"
diagnostic_stop_time = None
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
veh_id = 1
veh_id_bus = 0
alpha = 0

departTime_lane0 = []
departTime_lane1 = []
departTime_lane2 = []
vehicleType_lane0 = deque()
vehicleType_lane1 = deque()
vehicleType_lane2 = deque()

count_accept_utility = 0
count_refuse_utility = 0
count_refuse_physics = 0
count_send_PT = 0
count_send_DT = 0
count_send_AT = 0

count_LR = [0, 0, 0, 0]
count_LB = [0, 0, 0, 0]
count_RB = [0, 0, 0, 0]
count_RL = [0, 0, 0, 0]
count_BL = [0, 0, 0, 0]
count_BR = [0, 0, 0, 0]


count_Distribution = False


def build_vehicle_type_schedules(lane_counts, target_bus_share):
    """Create shuffled lane schedules whose total bus count is closest to the target share."""
    if not 0 <= target_bus_share <= 1:
        raise ValueError("bus share must be between 0 and 1")

    total_vehicles = sum(lane_counts)
    target_bus_count = int(total_vehicles * target_bus_share + 0.5)
    bus_counts = [int(count * target_bus_share) for count in lane_counts]

    # Give the remaining buses to lanes with the largest fractional remainder.
    # Shuffle first so equal remainders do not always favor the same approach.
    lane_order = list(range(len(lane_counts)))
    vehicle_type_rng.shuffle(lane_order)
    lane_order.sort(
        key=lambda index: lane_counts[index] * target_bus_share - bus_counts[index],
        reverse=True,
    )
    for index in lane_order[:target_bus_count - sum(bus_counts)]:
        bus_counts[index] += 1

    schedules = []
    for count, buses in zip(lane_counts, bus_counts):
        schedule = ["Bus"] * buses + ["Car"] * (count - buses)
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
def set_environment(inflow_0=750, inflow_1=750, inflow_2=750):
    global vehicle_instance
    global veh_id
    global departTime_lane0, departTime_lane1, departTime_lane2
    global vehicleType_lane0, vehicleType_lane1, vehicleType_lane2

    k_0 = int((simulation_time/3600)*inflow_0)
    k_1 = int((simulation_time/3600)*inflow_1)
    k_2 = int((simulation_time/3600)*inflow_2)

    # 車両の合流時刻を決定
    departTime_lane0 = sorted(random.sample(range(int(simulation_time/2.0)), k_0))
    departTime_lane1 = sorted(random.sample(range(int(simulation_time/2.0)), k_1))
    departTime_lane2 = sorted(random.sample(range(int(simulation_time/2.0)), k_2))

    # 2秒以上開けて流入
    departTime_lane0 = [round((n*2.0), 1)+0.1 for n in departTime_lane0]
    departTime_lane1 = [round((n*2.0), 1)+0.1 for n in departTime_lane1]
    departTime_lane2 = [round((n*2.0), 1)+0.1 for n in departTime_lane2]

    vehicleType_lane0, vehicleType_lane1, vehicleType_lane2 = build_vehicle_type_schedules(
        [k_0, k_1, k_2], bus_share
    )

    print(departTime_lane0)
    print(departTime_lane1)
    print(departTime_lane2)


def add_vehicle(alpha):
    global veh_id
    global veh_id_bus
    global departTime_lane0, departTime_lane1, departTime_lane2
    global vehicleType_lane0, vehicleType_lane1, vehicleType_lane2
    sumo_time = traci.simulation.getTime()

    alpha = int(alpha)
    # if sumo_time in departTime_lane1:
    if sumo_time in departTime_lane1:
        # 下から入る車両：BR（下→右）またはBL（下→左）を均等に割り振り
        route_id = choose_t_junction_route("bottom", route_mode, random.choice)
        kind = select_vehicle_type(vehicleType_lane1)
        #kind = "Car"
        if kind == "Car":
            traci.vehicle.add(vehID=str(veh_id), routeID=route_id, typeID="CAV_0", departLane="0", departPos="base", departSpeed="5")
            instance = CAV(veh_id, alpha, withAgree=True)
            veh_id += 2
            if route_id == "BR":
                count_BR[1] += 1
            elif route_id == "BL":
                count_BL[1] += 1
        elif kind == "Bus":
            traci.vehicle.add(vehID=str(veh_id_bus), routeID=route_id, typeID="CAV_bus", departLane="0", departPos="base", departSpeed="5")
            instance = CAV_bus(veh_id_bus, alpha, withAgree=True)
            veh_id_bus += 2
            if route_id == "BR":
                count_BR[0] += 1
            elif route_id == "BL":
                count_BL[0] += 1
        vehicle_instance.append(instance)
        

    # if sumo_time in departTime_lane0:
    if sumo_time in departTime_lane0:
        # 左から入る車両：LR（左→右）またはLB（左→下）を均等に割り振り
        route_id = choose_t_junction_route("left", route_mode, random.choice)
        #route_id = "LR"
        kind = select_vehicle_type(vehicleType_lane0)
        #kind = "Car"
        if kind == "Car":
            traci.vehicle.add(vehID=str(veh_id), routeID=route_id, typeID="CAV_0", departLane="0", departPos="base", departSpeed="5")
            instance = CAV(veh_id, alpha, withAgree=True)
            veh_id += 2
            if route_id == "LR":
                count_LR[1] += 1
            elif route_id == "LB":
                count_LB[1] += 1        
        elif kind == "Bus":
            traci.vehicle.add(vehID=str(veh_id_bus), routeID=route_id, typeID="CAV_bus", departLane="0", departPos="base", departSpeed="5")
            instance = CAV_bus(veh_id_bus, alpha, withAgree=True)
            veh_id_bus += 2
            if route_id == "LR":
                count_LR[0] += 1
            elif route_id == "LB":
                count_LB[0] += 1
        vehicle_instance.append(instance)
        

    if sumo_time in departTime_lane2:
        # 右から入る車両：RL（右→左）またはRB（右→下）を均等に割り振り
        route_id = choose_t_junction_route("right", route_mode, random.choice)
        #route_id = "RL"
        kind = select_vehicle_type(vehicleType_lane2)
        #kind = "Car"
        if kind == "Car":
            traci.vehicle.add(vehID=str(veh_id), routeID=route_id, typeID="CAV_0", departLane="0", departPos="base", departSpeed="5")
            instance = CAV(veh_id, alpha, withAgree=True)
            veh_id += 2
            if route_id == "RL":
                count_RL[1] += 1
            elif route_id == "RB":
                count_RB[1] += 1
        elif kind == "Bus":
            traci.vehicle.add(vehID=str(veh_id_bus), routeID=route_id, typeID="CAV_bus", departLane="0", departPos="base", departSpeed="5")
            instance = CAV_bus(veh_id_bus, alpha, withAgree=True)
            veh_id_bus += 2
            if route_id == "RL":
                count_RL[0] += 1
            elif route_id == "RB":
                count_RB[0] += 1
        vehicle_instance.append(instance)
        


def run(alpha=0, inflow_0=750, inflow_1=750, inflow_2=750, quiet=False, save_statistics=True):
    """execute the TraCI control loop"""
    global vehicle_instance
    global count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT
    sumo_time = 0
    split_time = round(simulation_time / 2, 1)
    central_path_server = []
    next_central_path_server = []
    all_speed = []
    all_speed_after_30s = 0
    all_speed_after_60s = []
    all_bus_speed = []
    all_bus_speed_after_30s = 0
    all_bus_speed_after_60s = 0
    LR_speed = []
    LR_BI_speed = []
    LB_speed = []
    TB_speed = []
    RB_speed = []
    RL_speed = []
    RL_BI_speed = []
    BL_speed = []
    BR_speed = []
    LR_bus_speed = []
    LR_BI_bus_speed = []
    LB_bus_speed = []
    TB_bus_speed = []
    RB_bus_speed = []
    RL_bus_speed = []
    RL_BI_bus_speed = []
    BL_bus_speed = []
    BR_bus_speed = []
    
    cav0_dist = [0]*168
    total_collision_time = 0
    total_caution_time = 0
    get_parameter = 0
    get_followrange = 0

    #初期設定（障害物の配置など）
    set_environment(inflow_0, inflow_1, inflow_2)
    file = alpha + '_' + str(inflow_0) + '_' + str(inflow_1) + '_' + str(inflow_2)
    animator = Animation(file)

    #シミュレーション開始
    run_until = diagnostic_stop_time if diagnostic_stop_time is not None else simulation_time
    while sumo_time < run_until:
        traci.simulationStep()
        sumo_time = traci.simulation.getTime()
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

        print([i.pathID for i in central_path_server])
        print([i.type for i in central_path_server])
        #CAV各車両の動作
        for index, ins in enumerate(vehicle_instance):
            # シミュレーション範囲を出た車両をリスト化
            if ins.id in arrived_list:
                poplist.append(index)
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
            #if ins.status == "lanechange":
                #ins.judgeAndDoLaneChange()

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
                all_speed.append(ins.speed)
                if sumo_time == split_time:
                    all_speed_after_30s = len(all_speed)
                if(sumo_time == 60):
                    all_speed_after_60s = len(all_speed)

                if ins.route == "LB":
                    LB_speed.append(ins.speed)
                elif ins.route == "RB":
                    RB_speed.append(ins.speed)
                elif ins.route == "BL":
                    BL_speed.append(ins.speed)
                elif ins.route == "BR":
                    BR_speed.append(ins.speed)
                elif ins.route == "LR":
                    LR_speed.append(ins.speed)
                    if ins.pos_x < 140:
                        LR_BI_speed.append(ins.speed)   
                elif ins.route == "TB":
                    TB_speed.append(ins.speed)             
                elif ins.route == "RL":
                    RL_speed.append(ins.speed)
                    if ins.pos_x > 160:
                        RL_BI_speed.append(ins.speed)

                if ins.passjunctionstatus == "now":
                    if ins.route == "LB":
                        count_LB[3] += 1
                    elif ins.route == "RB":
                        count_RB[3] += 1
                    elif ins.route == "BL":
                        count_BL[3] += 1
                    elif ins.route == "BR":
                        count_BR[3] += 1
                    elif ins.route == "LR":
                        count_LR[3] += 1
                    elif ins.route == "RL":
                        count_RL[3] += 1


            

            if ins.type == "Bus":
                all_bus_speed.append(ins.speed)
                if sumo_time == split_time:
                    all_bus_speed_after_30s = len(all_bus_speed)
                if(sumo_time == 60):
                    all_bus_speed_after_60s = len(all_bus_speed)

                if ins.route == "LB":
                    LB_bus_speed.append(ins.speed)
                elif ins.route == "RB":
                    RB_bus_speed.append(ins.speed)
                elif ins.route == "BL":
                    BL_bus_speed.append(ins.speed)
                elif ins.route == "BR":
                    BR_bus_speed.append(ins.speed)
                elif ins.route == "LR":
                    LR_bus_speed.append(ins.speed)
                    if ins.pos_x < 140:
                        LR_BI_bus_speed.append(ins.speed)
                elif ins.route == "TB":
                    TB_bus_speed.append(ins.speed)
                elif ins.route == "RL":
                    RL_bus_speed.append(ins.speed)
                    if ins.pos_x > 160:
                        RL_BI_bus_speed.append(ins.speed)

                if ins.passjunctionstatus == "now":
                    if ins.route == "LB":
                        count_LB[2] += 1
                    elif ins.route == "RB":
                        count_RB[2] += 1
                    elif ins.route == "BL":
                        count_BL[2] += 1
                    elif ins.route == "BR":
                        count_BR[2] += 1
                    elif ins.route == "LR":
                        count_LR[2] += 1
                    elif ins.route == "RL":
                        count_RL[2] += 1
                
                

            if(count_Distribution and sumo_time > 30):
                cav0_dist[int(round(ins.speed,1)*10)] += 1

        # Record actual 0.1-second motion after all controllers have updated.
        # This is a no-op unless MCS_EVALUATION_AUDIT is configured.
        observed = [ins for ins in vehicle_instance if ins.id in running_list]
        evaluation_metrics.observe(
            observed, sumo_time,
            {str(ins.id): traci.vehicle.getAllowedSpeed(ins.id) for ins in observed})

        #車両インスタンスを削除
        if poplist:
            for i in sorted(poplist, reverse=True):
                vehicle_instance.pop(i)

        if show_animation:
            animator.path_animation(vehicle_instance, time=sumo_time, objects=ob)

        # 車両の新規流入
        add_vehicle(alpha)


    statistics_path = "./statistics/acceptance_three.csv" if save_statistics else os.devnull
    with open(statistics_path, "a", encoding='utf-8') as f:
        #text = "{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(seed, alpha, inflow_0, inflow_1, inflow_2, inflow_3, count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT, "test")
        text = "{},{},{},{},{},{},{},{},{},{},{},{}\n".format("seed", "alpha", "inflow_Left", "inflow_Bottom", "inflow_Right", "accept_utility", "refuse_utility", "refuse_physics", "send_PT", "send_DT", "send_AT", "date_time")
        f.write(text)
        text = "{},{},{},{},{},{},{},{},{},{},{},{}\n".format(seed, alpha, inflow_0, inflow_1, inflow_2, count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT, datetime.datetime.now())
        f.write(text)

        text = "{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format(" ", "LR", "LB", "RB", "RL", "BL", "BR", "pass_LR", "pass_LB", "pass_RB", "pass_RL", "pass_BL", "pass_BR")
        f.write(text)
        text = "{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format("Bus", count_LR[0], count_LB[0], count_RB[0], count_RL[0], count_BL[0], count_BR[0], count_LR[2], count_LB[2], count_RB[2], count_RL[2], count_BL[2], count_BR[2])
        f.write(text)
        text = "{},{},{},{},{},{},{},{},{},{},{},{},{}\n".format("Car", count_LR[1], count_LB[1], count_RB[1], count_RL[1], count_BL[1], count_BR[1], count_LR[3], count_LB[3], count_RB[3], count_RL[3], count_BL[3], count_BR[3])
        f.write(text)

        text = "{},{},{},{},{},{},{},{}\n".format(" ", "LR", "LB", "TB", "RB", "RL", "BL", "BR")
        f.write(text)
        text = "{},{},{},{},{},{},{},{}\n".format("Bus", round(mean_or_nan(LR_bus_speed),4), round(mean_or_nan(LB_bus_speed),4), round(mean_or_nan(TB_bus_speed),4), round(mean_or_nan(RB_bus_speed),4), round(mean_or_nan(RL_bus_speed),4), round(mean_or_nan(BL_bus_speed),4), round(mean_or_nan(BR_bus_speed),4))
        f.write(text)
        text = "{},{},{},{},{},{},{},{}\n".format("Car", round(mean_or_nan(LR_speed),4), round(mean_or_nan(LB_speed),4), round(mean_or_nan(TB_speed),4), round(mean_or_nan(RB_speed),4), round(mean_or_nan(RL_speed),4), round(mean_or_nan(BL_speed),4), round(mean_or_nan(BR_speed),4))
        f.write(text)

        text = "{},{},{},{},{},{},{}\n".format(
            " ",
            "tn_right",
            "tn_left",
            "tn_straight",
            f"0-{simulation_time:g}",
            f"0-{split_time:g}",
            f"{split_time:g}-{simulation_time:g}",
        )
        f.write(text)
        text = "{},{},{},{},{},{},{}\n".format("Bus", round(mean_or_nan(LB_bus_speed+BR_bus_speed),4), round(mean_or_nan(RB_bus_speed+BL_bus_speed),4), round(mean_or_nan(LR_BI_bus_speed+RL_BI_bus_speed),4), round(mean_or_nan(all_bus_speed),4), round(mean_or_nan(all_bus_speed[:all_bus_speed_after_30s]),4), round(mean_or_nan(all_bus_speed[all_bus_speed_after_30s:]),4))
        f.write(text)
        text = "{},{},{},{},{},{},{}\n".format("Car", round(mean_or_nan(LB_speed+BR_speed),4), round(mean_or_nan(RB_speed+BL_speed),4), round(mean_or_nan(LR_BI_speed+RL_BI_speed),4), round(mean_or_nan(all_speed),4), round(mean_or_nan(all_speed[:all_speed_after_30s]),4), round(mean_or_nan(all_speed[all_speed_after_30s:]),4))
        f.write(text)
        text = "{},{},{},{},{},{},{}\n".format("All", round(mean_or_nan(LB_speed+BR_speed+LB_bus_speed+BR_bus_speed),4), round(mean_or_nan(RB_speed+BL_speed+RB_bus_speed+BL_bus_speed),4), round(mean_or_nan(LR_BI_speed+RL_BI_speed+LR_BI_bus_speed+RL_BI_bus_speed),4), round(mean_or_nan(all_speed+all_bus_speed),4), round(mean_or_nan(all_speed[:all_speed_after_30s]+all_bus_speed[:all_bus_speed_after_30s]),4), round(mean_or_nan(all_speed[all_speed_after_30s:]+all_bus_speed[all_bus_speed_after_30s:]),4))
        f.write(text)
        text = "{},{},{},{},{},{},{}\n".format("---", "---", "---", "---", "↑All", "---", "---")
        f.write(text)

    summary_stream = sys.stderr if quiet else sys.stdout
    all_vehicle_speed = all_speed + all_bus_speed
    all_vehicle_speed_first_half = all_speed[:all_speed_after_30s] + all_bus_speed[:all_bus_speed_after_30s]
    all_vehicle_speed_second_half = all_speed[all_speed_after_30s:] + all_bus_speed[all_bus_speed_after_30s:]
    generated_bus_count = sum(count[0] for count in (count_LR, count_LB, count_RB, count_RL, count_BL, count_BR))
    generated_car_count = sum(count[1] for count in (count_LR, count_LB, count_RB, count_RL, count_BL, count_BR))
    generated_vehicle_count = generated_bus_count + generated_car_count
    actual_bus_share = generated_bus_count / generated_vehicle_count if generated_vehicle_count else float("nan")

    print(
        f"vehicle_mix : Bus {generated_bus_count} Car {generated_car_count} "
        f"bus_rate {actual_bus_share * 100:.2f}%",
        file=summary_stream,
    )
    print("car_speed :", mean_or_nan(all_speed), file=summary_stream)
    print("bus_speed :", mean_or_nan(all_bus_speed), file=summary_stream)
    print("all_speed :", mean_or_nan(all_vehicle_speed), file=summary_stream)
    print(f"all_speed (0s ~ {split_time:g}s) :", mean_or_nan(all_vehicle_speed_first_half), file=summary_stream)
    print(f"all_speed ({split_time:g}s ~ end) :", mean_or_nan(all_vehicle_speed_second_half), file=summary_stream)
    print("collision :", total_collision_time, file=summary_stream)
    print("caution :", total_caution_time, file=summary_stream)
    #print("collision :", CAV.returnCollisionTime())

    if(count_Distribution and save_statistics):
        palameter = [alpha, seed, inflow_0, inflow_1, simulation_time, get_followrange, get_parameter, mean_or_nan(cav0_speed), mean_or_nan(cav1_speed), mean_or_nan(all_speed), mean_or_nan(cav0_speed_after_30s), mean_or_nan(cav1_speed_after_30s), mean_or_nan(all_speed_after_30s)]
        #pala_dist = palameter + cav0_dist + cav1_dist
        with open("./statistics/speed_distribution.csv", "a", encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(palameter)
            writer.writerow(cav0_dist)


    sys.stdout.flush()
    traci.close()


def get_options():
    """define options for this script and interpret the command line"""
    optParser = optparse.OptionParser()
    optParser.add_option("--nogui", action="store_true",default=False, help="run the commandline version of sumo")
    optParser.add_option("--duration", type="float", default=600.0, help="duration of the simulation")
    optParser.add_option("--stop-time", type="float", default=None, help="stop early while retaining the full-duration input schedule")
    optParser.add_option("--bus-allocation", type="choice", choices=["fixed", "paper-random25"], default="fixed", help="fixed share or the paper artifact's per-vehicle 25%% draw")
    optParser.add_option("--bus-share", type="float", default=0.25, help="share of buses from 0 to 1")
    optParser.add_option("--route-mode", type="choice", choices=["random", "eval1"], default="random", help="unrestricted routes or Eval.1 A/C straight-only routes")
    optParser.add_option("--quiet", action="store_true", default=False, help="suppress verbose per-step output")
    optParser.add_option("--no-save", action="store_true", default=False, help="do not append the run to statistics CSV")
    optParser.add_option("--deceleration-shadow", action="store_true", default=False,
                         help="record read-only deceleration-propagation comparisons")
    optParser.add_option("--deceleration-active", action="store_true", default=False,
                         help="experimentally use deceleration-propagation decisions")
    options, args = optParser.parse_args()
    if len(args) != 5:
        optParser.error("expected: alpha seed inflow_left inflow_bottom inflow_right")
    if options.stop_time is not None and not 0 < options.stop_time <= options.duration:
        optParser.error("--stop-time must be greater than 0 and no greater than --duration")
    if not 0 <= options.bus_share <= 1:
        optParser.error("--bus-share must be between 0 and 1")
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
    route_mode = options.route_mode
    if not options.quiet:
        print(args)
    alpha = str(args[0])
    seed = args[1]
    random.seed(seed)
    vehicle_type_rng.seed(f"{seed}:vehicle-types")
    inflow_0 = int(args[2])
    inflow_1 = int(args[3])
    inflow_2 = int(args[4])

    # this script has been called from the command line. It will start sumo as a server, then connect and run
    if options.nogui:
        sumoBinary = checkBinary('sumo')
    else:
        sumoBinary = checkBinary('sumo-gui')

    # this is the normal way of using traci. sumo is started as a subprocess and then the python script connects and runs
    sumo_command = [sumoBinary, '-c', os.path.join('junction_three.sumocfg')]
    if options.quiet:
        sumo_command.extend(["--no-step-log", "true"])

    if options.quiet:
        with open(os.devnull, "w") as devnull:
            with redirect_stdout(devnull):
                traci.start(sumo_command)
                run(alpha, inflow_0, inflow_1, inflow_2, quiet=True, save_statistics=not options.no_save)
                vehicle_instance.clear()
    else:
        traci.start(sumo_command)
        run(alpha, inflow_0, inflow_1, inflow_2, save_statistics=not options.no_save)
