# coding: utf-8
#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import print_function
from distutils.spawn import spawn

import os
import sys
import optparse
import numpy as np
import datetime

# the directory in which this script resides
THISDIR = os.path.dirname(__file__)
sys.path.append("../PathPlanning/FrenetOptimalTrajectory/")
sys.path.append("../func")
from cav_merge import CAV
from animation_merge import Animation
from frenet_merge import emergency_stop

# we need to import python modules from the $SUMO_HOME/tools directory
# If the the environment variable SUMO_HOME is not set, try to locate the python modules relative to this script
if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")
import traci  # noqa
from sumolib import checkBinary  # noqa


simulation_time = 60.0
# matplotlibによる描画
show_animation = False
import random

vehicle_instance = []
nonCAV_list = []
veh_id = 0
alpha = 0.0

departTime_lane0 = []
departTime_lane1 = []
departTime_lane2 = []

count_accept_utility = 0
count_refuse_utility = 0
count_refuse_physics = 0
count_send_PT = 0
count_send_DT = 0
count_send_AT = 0

#初期設定（障害物の配置など）
def set_environment(inflow=1500):
    global vehicle_instance
    global veh_id
    global departTime_lane0, departTime_lane1, departTime_lane2

    #合流地点を示すための障害物
    traci.vehicle.add(vehID="stone", routeID="main", typeID="CAV_0", departLane="0", departPos="205.0", departSpeed="0")
    traci.vehicle.setColor("stone", (250, 250, 250))
    traci.vehicle.setSpeed(vehID="stone", speed=0)
    nonCAV_list.append("stone")

    lane = 2
    k = int((simulation_time/3600)*inflow/lane)
    # 車両の合流時刻を決定
    departTime_lane0 = sorted(random.sample(range(int(simulation_time/2.0)), k))
    departTime_lane1 = sorted(random.sample(range(int(simulation_time/2.0)), k))
    # departTime_lane2 = sorted(random.sample(range(int(simulation_time/2.0)), k))

    # 2秒以上開けて流入
    departTime_lane0 = [round((n*2.0), 1)+0.1 for n in departTime_lane0]
    departTime_lane1 = [round((n*2.0), 1)+0.1 for n in departTime_lane1]
    # departTime_lane2 = [round((n*2.0), 1)+0.1 for n in departTime_lane2]

    print(departTime_lane0)
    print(departTime_lane1)
    # print(departTime_lane2)


def add_vehicle(alpha):
    global veh_id
    global departTime_lane0, departTime_lane1, departTime_lane2
    sumo_time = traci.simulation.getTime()

    alpha = float(alpha)
    # if sumo_time in departTime_lane1:
    if sumo_time in departTime_lane1:
        traci.vehicle.add(vehID=str(veh_id), routeID="main", typeID="CAV_1", departLane="1", departPos="base", departSpeed="16.67")
        instance = CAV(veh_id, alpha, withAgree=False)
        vehicle_instance.append(instance)
        veh_id += 1

    # if sumo_time in departTime_lane0:
    if sumo_time in departTime_lane0:
        traci.vehicle.add(vehID=str(veh_id), routeID="main", typeID="CAV_0", departLane="0", departPos="base", departSpeed="16.67")
        instance = CAV(veh_id, alpha, withAgree=False)
        vehicle_instance.append(instance)
        veh_id += 1


def run(alpha='0.0', inflow=1500):
    """execute the TraCI control loop"""
    global vehicle_instance
    global count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT
    sumo_time = 0
    central_path_server = []
    next_central_path_server = []

    #初期設定（障害物の配置など）
    set_environment(inflow)
    file = alpha + '_' + str(inflow)
    animator = Animation(file)

    #シミュレーション開始
    while sumo_time != simulation_time:
        traci.simulationStep()
        sumo_time = traci.simulation.getTime()
        print("\nTIME:", sumo_time)
        if sumo_time % 20 == 0:
            now = datetime.datetime.now().time()
            print("TIME:", sumo_time, now, "alpha", alpha, "seed", seed, "inflow", inflow, file = sys.stderr)

        arrived_list = traci.simulation.getArrivedIDList()
        running_list = traci.vehicle.getIDList()

        ob = np.array([[202.5, -7.3]]) # obstacles lists (車両で障害物を表現しているため、幅と長さを考慮した位置)
        central_path_server = [path for path in next_central_path_server if path.vehID in running_list]
        next_central_path_server = []
        poplist = []
        
        #non-CAVは等加速度で動くと仮定して経路を生成
        stone_pos = traci.vehicle.getPosition("stone")
        stonePath = emergency_stop(202.5, 0.0, stone_pos[1], route=None)[0]
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

            au, ru, rp, sp, sd, sa = ins.getStatistics()
            count_accept_utility += au
            count_refuse_utility += ru
            count_refuse_physics += rp
            count_send_PT += sp
            count_send_DT += sd
            count_send_AT += sa

        #車両インスタンスを削除
        if poplist:
            for i in sorted(poplist, reverse=True):
                vehicle_instance.pop(i)

        if show_animation:
            animator.path_animation(vehicle_instance, time=sumo_time, objects=ob)

        # 車両の新規流入
        add_vehicle(alpha)

    with open("./statistics/acceptance.csv", "a", encoding='utf-8') as f:
        text = "{},{},{},{},{},{},{},{},{}\n".format(seed, alpha, inflow, count_accept_utility, count_refuse_utility, count_refuse_physics, count_send_PT, count_send_DT, count_send_AT)
        f.write(text)

    sys.stdout.flush()
    traci.close()


def get_options():
    """define options for this script and interpret the command line"""
    optParser = optparse.OptionParser()
    optParser.add_option("--nogui", action="store_true",
                         default=False, help="run the commandline version of sumo")
    options, args = optParser.parse_args()
    return options


# this is the main entry point of this script
if __name__ == "__main__":
    # load whether to run with or without GUI
    options = get_options()
    args = sys.argv
    print(args)
    alpha = str(args[1])
    seed = args[2]
    random.seed(seed)
    inflow = int(args[3])

    # this script has been called from the command line. It will start sumo as a server, then connect and run
    if options.nogui:
        sumoBinary = checkBinary('sumo')
    else:
        sumoBinary = checkBinary('sumo-gui')

    # this is the normal way of using traci. sumo is started as a subprocess and then the python script connects and runs
    traci.start([sumoBinary, '-c', os.path.join('merge.sumocfg')])
    run(alpha, inflow)