import os
from re import S
import sys
import numpy as np
import copy
import thesis_tiv
import thesis_baselines
import time

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")
import traci  # noqa
sys.path.append("../PathPlanning/FrenetOptimalTrajectory/")
from frenet_three_junction import generate_frenet_frame as _generate_frenet_frame, emergency_stop as _emergency_stop

maxSpeed = 11.11 # [m/s]
maxAccel = 1.0 # [m/ss]
maxDecel = -3.0 # [m/ss]
sensorRange = 200 # [m]
commRange = 200 # [m]
maxPathLen = 10.0 # max path time [s]
LANE_WIDTH = 3.2 # [m]

timeStep = 0.1 # [s]
predTime = 10.0 # [s]
pathValidTime = 1.0 # [s]

D_0 = 5.0 # longitudinal safe margin [m]
tau = 1.5 # safe headway time [s]
PET_th = 3.0 # safe PET [s] 
yield_th = 0.0 # threshold whether yield
R_max = 0.9 # 後続係数の最大値
R_co = -0.1  #後続係数の計算に対する係数
R_per = 0.1  #性能優先度に対する係数


def generate_frenet_frame(*args, **kwargs):
    """Generate a trajectory using the physical limits of a CAV bus."""
    kwargs.setdefault("vehicle_max_speed", maxSpeed)
    kwargs.setdefault("vehicle_max_accel", maxAccel)
    kwargs.setdefault("vehicle_max_decel", maxDecel)
    return _generate_frenet_frame(*args, **kwargs)


def emergency_stop(pos_x, speed, pos_y, route):
    return _emergency_stop(pos_x, speed, pos_y, route, max_decel=maxDecel)


class CAV_bus:
    # constructor
    def __init__(self, vehID, alpha, withAgree=False):
        self.id = str(vehID)
        # not allow autonomous lanechange
        traci.vehicle.setLaneChangeMode(self.id, 0b000000000000)
        # control vehicle speed by traci
        traci.vehicle.setSpeedMode(self.id, 0b100000)

        self.plannedPath = None
        self.desiredPaths = None
        self.receivedPaths = []
        self.alter_change_path = None
        self.alter_straight_path = None
        self.isPathValid = True
        self.pathID = 0

        self.typeID = traci.vehicle.getTypeID(self.id)
        self.route = traci.vehicle.getRouteID(self.id)
        self.road = None
        self.lane = None
        self.status = None # free, follow, stop, lanechange, turn, yield
        self.type = "Bus"
        self.passjunctionstatus = None

        self.pos_x = 0
        self.pos_y = 0
        if self.route in ["RL", "RB", "RT"]:
            self.pos_x = 300.0
            self.pos_y = 1.6
        if self.route == ["LR", "LB", "LT"]:
            self.pos_x = 0.0
            self.pos_y = -1.6
        elif self.route in ["BR", "BL", "BT"]:
            self.pos_x = 151.6
            self.pos_y = -150.0
        elif self.route in ["TR", "TL", "TB"]:
            self.pos_x = 148.4
            self.pos_y = 150.0
        self.angle = None
        self.speed = 0
        self.accel = 0
        self.leader = None
        self.leadPath = None
        self.length = 5.0
        self.width = 1.8

        self.simTime = 0
        self.myColor = ["blue", "navy", "steelblue", "deepskyblue", "cyan", "indigo", "royalblue"][vehID%7]
        self.alpha = alpha
        self.yetJudgedList = []

        self.WithAgreementPhase = withAgree
        self.isWaitAgree = False
        self.waitPath = None
        self.waitAgreeID = []
        self.receiveAgreeID = []

        self.count_accept_utility = 0
        self.count_refuse_utility = 0
        self.count_refuse_physics = 0
        self.count_send_PT = 0
        self.count_send_DT = 0
        self.count_send_AT = 0


    # update own status every step
    def updateStatus(self, running_list):
        self.simTime = traci.simulation.getTime()
        
        # update own position
        pos = traci.vehicle.getPosition(self.id)
        self.pos_x = pos[0]
        self.pos_y = pos[1]

        if self.plannedPath:
            for i in range(len(self.plannedPath.t)):
                if self.plannedPath.t[i] == self.simTime:
                    self.pos_x = self.plannedPath.x[i]
                    self.pos_y = self.plannedPath.y[i]

        self.angle = traci.vehicle.getAngle(self.id)
        self.speed = min(traci.vehicle.getSpeed(self.id), maxSpeed)
        self.accel = min(traci.vehicle.getAcceleration(self.id), maxAccel)
        self.road = traci.vehicle.getRoadID(self.id)
        self.lane = traci.vehicle.getLaneIndex(self.id)

        # leaderがシミュレーション範囲から出たらleaderを初期化
        if self.leader not in running_list:
            self.leader = None
            self.leadPath = None

        # update own status
        if self.status == "turn": # 交差点を通過したらturn状態を解除
            if self.route == "BR" and self.road == "right":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "LR")
                self.route = "LR"
                self.isPathValid = False
            elif self.route == "BL" and self.road == "-left":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "RL")
                self.route = "RL"
                self.isPathValid = False
            elif self.route == "LB" and self.road == "bottom":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "TB")
                self.route = "TB"
                self.isPathValid = False
            elif self.route == "RB" and self.road == "bottom":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "TB")
                self.route = "TB"
                self.isPathValid = False
            #以下追加
            elif self.route == "LT" and self.road == "-top":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "BT")
                self.route = "BT"
                self.isPathValid = False
            elif self.route == "RT" and self.road == "-top":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "BT")
                self.route = "BT"
                self.isPathValid = False
            elif self.route == "TR" and self.road == "right":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "TB")
                self.route = "TB"
                self.isPathValid = False
            elif self.route == "TL" and self.road == "-left":
                self.status = "free"
                traci.vehicle.setRouteID(self.id, "TB")
                self.route = "TB"
                self.isPathValid = False
            #ここまで

        elif self.status == "yield": # 譲った相手が交差点を通過したらyield状態を解除
            if traci.vehicle.getRoadID(self.leader) in ["right", "-left", "-bottom", "-top"]:
                self.status = None
                self.leader = None
                self.leadPath = None
                self.isPathValid = False

        # set leading vehicle
        ld = traci.vehicle.getLeader(self.id)
        if ld is not None:
            if self.status == "yield":
                leadPath = [path for path in self.receivedPaths if path.vehID == self.leader and path.isTurn == True]
                if leadPath:
                    self.leadPath = leadPath[0]

                if self.leader == ld[0]:
                    self.status = "follow"

            elif (self.pos_x - traci.vehicle.getPosition(ld[0])[0])**2 + (self.pos_y - traci.vehicle.getPosition(ld[0])[1])**2 <= sensorRange**2 and traci.vehicle.getRoadID(ld[0]):
                self.leader = ld[0]
                leadPath = [path for path in self.receivedPaths if path.vehID == self.leader and path.type == "planned"]
                if leadPath:
                    if self.leadPath and self.leadPath.pathID != leadPath[0].pathID and self.status not in ["yield", "turn"]:
                        # 直前の予定経路が変更された場合、自身の経路も合わせて再設定
                        self.isPathValid = False
                    self.leadPath = leadPath[0]

            # 前方車両が車線変更中の場合は、さらに一つ前の車両に追従する
            if self.leadPath and self.plannedPath and self.leadPath.isLaneChange and (self.plannedPath.y[-1] != self.leadPath.y[-1]):
                ld = traci.vehicle.getLeader(self.leadPath.vehID)
                self.leader = ld[0]

        elif ld is None:
            if self.status == "follow":
                self.leader = None
                self.status = "free"
            
            if self.road in ["right", "-left", "-bottom", "-top"]:
                self.leader = None
                self.status = "free"

        # set leading path
        if self.leader:
            leadPath = [path for path in self.receivedPaths if path.vehID == self.leader and path.type == "planned"]
            if leadPath:        
                self.leadPath = leadPath[0]
            else:
                self.leadPath = None
        else:
            self.leadPath = None

        self.count_accept_utility = 0
        self.count_refuse_utility = 0
        self.count_refuse_physics = 0
        self.count_send_PT = 0
        self.count_send_DT = 0
        self.count_send_AT = 0


    # update own planned path
    def updatePlannedPath(self, ob):
            
        if self.plannedPath:  
            # check collision among own planned path and other PLANNED paths
            collision_list_planned, _ = self.checkPathCollision(self.plannedPath, self.receivedPaths, s_type="planned")
            if len(collision_list_planned) > 0:
                if self.status == "turn" and self.pos_y > -8.2: # 交差点進入後は止まらない
                    pass
                else:
                    print("my planned path collide")
                    self.status = None
                    self.isPathValid = False

            # check collision among own planned path and other DESIRED paths
            collision_list_desired, _ = self.checkPathCollision(self.plannedPath, self.receivedPaths, s_type="desired")
            # 他車両の希望経路と重複している場合には、代替経路を生成
            if len(collision_list_desired) > 0 and self.status != "turn":
                self.judgeYield(collision_list_desired, ob)

        # 他の車両が全て交渉を受け入れる場合に代替経路を予定経路に設定
        if self.WithAgreementPhase and self.isWaitAgree:
            self.waitAgreeID.sort()
            self.receiveAgreeID.sort()
            print("\tagree wait id", self.waitAgreeID, "receive id", self.receiveAgreeID)
            if self.waitAgreeID == self.receiveAgreeID:
                print("\talter to", self.waitPath.pathID)
                self.alter_straight_path.type = "planned"
                self.plannedPath = self.alter_straight_path
                self.alter_straight_path = None
                self.status = "yield"
                self.leader = self.waitPath.vehID
                self.leadPath = self.waitPath
                self.isPathValid = True

                self.isWaitAgree = False
                self.waitAgreeID = []
                self.receiveAgreeID = []
                self.waitPath = None

        # 期限切れの代替経路を削除
        if self.alter_straight_path and round(self.simTime - self.alter_straight_path.t[0], 2) >= pathValidTime:
            self.alter_straight_path = None
            self.isWaitAgree = False
            self.waitAgreeID = []
            self.receiveAgreeID = []
            self.waitPath = None

        # 新しい経路を生成
        if not self.plannedPath or round(self.simTime - self.plannedPath.t[0], 2) >= thesis_tiv.planned_update_interval(self, pathValidTime) or self.isPathValid == False:

            #経路候補をたくさん生成
            path_candidates = self.generatePlannedPath(ob=ob)

            #コスト関数が最小になるものを選定
            best_path = self.selectBestPath(path_candidates)

            self.pathID += 1
            path_id = self.id + "_" + str(self.pathID)
            best_path.pathID = path_id
            best_path.vehID = self.id
            best_path.type = "planned"
    
            self.plannedPath = best_path 
            
            self.isPathValid = True


    def updateDesiredPath(self, ob):
        # 希望経路を決定 (最初の1ステップはスキップ)
        if self.simTime <= timeStep:
            return 

        # 期限切れの経路を削除
        if self.desiredPaths and round(self.simTime - self.desiredPaths[0].t[0], 2) >= pathValidTime:
            self.desiredPaths = None

        if self.checkPathChangeNecessity() and not self.desiredPaths:
            #経路候補をたくさん生成
            path_candidates = self.generateDesiredPath(ob=ob)
            # print("gen desired len", len(path_candidates))
            if len(path_candidates) == 0:
                self.desiredPaths = None
                return

            # コスト関数が最小になるものを選定
            best_path = self.selectBestPath(path_candidates)

            self.pathID += 1
            path_id = self.id + "_" + str(self.pathID)
            best_path.pathID = path_id
            best_path.vehID = self.id
            best_path.type = "desired"
            self.desiredPaths = [best_path]
            

    def checkRoutePriority(self, ego_path, x):

        x_route = traci.vehicle.getRouteID(x.vehID)

        # 同車線の後続車両と経路が重複していても先頭車両が優先
        if (self.pos_y>0 and self.pos_y<3.2) and (x.y[0]>0 and x.y[0]<3.2) and self.pos_x<x.x[0]:
            return True
        if (self.pos_y<0 and self.pos_y>-3.2) and (x.y[0]<0 and x.y[0]>-3.2) and self.pos_x>x.x[0]:
            return True
        if (self.pos_x>150 and self.pos_x<153.2) and (x.x[0]>150 and x.x[0]<153.2) and self.pos_y>x.y[0]:
            return True
        #追加
        if (self.pos_x<150 and self.pos_x>146.8) and (x.x[0]<150 and x.x[0]>146.8) and self.pos_y<x.y[0]:
            return True
        #ここまで
        # if x.vehID != self.id and x.isTurn == True and x.type == "planned" and self.route not in ["BL", "BR"]:
        #     return True
        

        if ego_path.type == x.type:
            route_priority = {"LR":1, "RL":1, "TB":1, "LB":2, "BR":2, "RB":3, "BL":4, "BT":1, "RT":2, "TL":2, "LT":3, "TR":4} #"RB":3, "BL":4に倣って,左右方向を優先道路としてみる
            if route_priority[self.route] < route_priority[x_route]:
                return True
            else:
                return False

        return False


    def checkPathCollision(self, own_path, other_paths, s_type="all"):
        
        collision_list = []
        notCollision_list = []
        
        if len(other_paths) == 0:
            return collision_list, notCollision_list

        #自身の経路は最新版、他車の経路は1ステップ古い
        for x in other_paths:
            if s_type == "all":
                pass
            elif x.type != s_type:
                continue
            
            startItr_own = None
            startItr_x = None
            for i in range(len(own_path.t)):
                if self.simTime == own_path.t[i]:
                    startItr_own = i
            for i in range(len(x.t)):
                if self.simTime == x.t[i]:
                    startItr_x = i
                
            if startItr_own is None or startItr_x is None:
                print(own_path.pathID, own_path.t[0], "~", own_path.t[-1], file=sys.stderr)
                print(x.pathID, x.t[0], "~", x.t[-1], file=sys.stderr)

            # print("check collision", own_path.type, own_path.pathID, "and", x.type, x.pathID) 
            assert own_path.t[startItr_own] == x.t[startItr_x]
            t_last = min(len(own_path.x)-startItr_own, len(x.x)-startItr_x)-1

            isCollide = False
            dict = {"path": None, "collide_x": None, "collide_y" : None, "speed" : None, "duration" : None}

            # 重複し得ない経路は計算量削減のため衝突判定を省略
            x_route = traci.vehicle.getRouteID(x.vehID)
            #修正 TBが交差点通過後のみを示さなくなるため
            #if (self.route == "LR" and x_route == "RL") or (self.route == "RL" and x_route == "LR") or self.route == "TB" or x_route == "TB":
            if (self.route == "LR" and x_route == "RL") or (self.route == "RL" and x_route == "LR"):
                notCollision_list.append(x)
                continue
            elif (self.route == "LB" and x_route == "BL") or (self.route == "BL" and x_route == "LB"):
                notCollision_list.append(x)
                continue
            elif (self.route == "LB" and x_route == "BR") or (self.route == "BR" and x_route == "LB"):
                notCollision_list.append(x)
                continue
            elif (self.route == "RB" and x_route == "BR") or (self.route == "BR" and x_route == "RB"):
                notCollision_list.append(x)
                continue
            elif (self.route == "RL" and x_route == "LB") or (self.route == "LB" and x_route == "RL"):
                notCollision_list.append(x)
                continue
            #ここから追加
            elif (self.route == "LT" and x_route == "TL") or (self.route == "LT" and x_route == "BR") or (self.route == "LT" and x_route == "RB"):
                notCollision_list.append(x)
                continue
            elif (self.route == "LR" and x_route == "RT") or (self.route == "LR" and x_route == "TL"):
                notCollision_list.append(x)
                continue
            elif (self.route == "LB" and x_route == "BT") or (self.route == "LB" and x_route == "RT") or (self.route == "LB" and x_route == "TL") or (self.route == "LB" and x_route == "TR"):
                notCollision_list.append(x)
                continue
            elif (self.route == "TR" and x_route == "RT") or (self.route == "TR" and x_route == "LB") or (self.route == "TR" and x_route == "BL"):
                notCollision_list.append(x)
                continue
            elif (self.route == "TB" and x_route == "BR") or (self.route == "TB" and x_route == "BT") or (self.route == "TB" and x_route == "RT"):
                notCollision_list.append(x)
                continue
            elif (self.route == "TL" and x_route == "LT") or (self.route == "TL" and x_route == "LR") or (self.route == "TL" and x_route == "LB") or (self.route == "TL" and x_route == "BT") or (self.route == "TL" and x_route == "BR") or (self.route == "TL" and x_route == "RT") or (self.route == "TL" and x_route == "RB"):
                notCollision_list.append(x)
                continue
            elif (self.route == "RB" and x_route == "TL") or (self.route == "RB" and x_route == "LT"):
                notCollision_list.append(x)
                continue
            elif (self.route == "RL" and x_route == "BR"):
                notCollision_list.append(x)
                continue
            elif (self.route == "RT" and x_route == "TR") or (self.route == "RT" and x_route == "TB") or (self.route == "RT" and x_route == "TL") or (self.route == "RT" and x_route == "LR") or (self.route == "RT" and x_route == "LB") or (self.route == "RT" and x_route == "BR") or (self.route == "RT" and x_route == "BL"):
                notCollision_list.append(x)
                continue
            elif (self.route == "BL" and x_route == "RT") or (self.route == "BL" and x_route == "TR"):
                notCollision_list.append(x)
                continue
            elif (self.route == "BT" and x_route == "TB") or (self.route == "BT" and x_route == "TL") or (self.route == "BT" and x_route == "LT"):
                notCollision_list.append(x)
                continue
            elif (self.route == "BR" and x_route == "RL") or (self.route == "BR" and x_route == "RT") or (self.route == "BR" and x_route == "TB") or (self.route == "BR" and x_route == "TL") or (self.route == "BR" and x_route == "LT"):
                notCollision_list.append(x)
                continue
            #ここまで

            if self.checkRoutePriority(own_path, x):
                notCollision_list.append(x)
                continue

            collision_point = None
            # 交差点内での衝突判定にはPETを使用
            if (self.route == "BL" and x_route == "LR") or (self.route == "LR" and x_route == "BL"):
                collision_point = (149, -1.6)
            elif (self.route == "BL" and x_route == "RL") or(self.route == "RL" and x_route == "BL"):
                collision_point = (141.8, 1.6)
            elif (self.route == "BR" and x_route == "LR") or (self.route == "LR" and x_route == "BR"):
                collision_point = (158.2, -1.6)
            elif (self.route == "RB" and x_route == "LR") or (self.route == "LR" and x_route == "RB"):
                collision_point = (151, -1.6)        
            elif (self.route == "LB" and x_route == "RB") or (self.route == "RB" and x_route == "LB"):
                collision_point = (148.4, -8.2)
            elif (self.route == "RB" and x_route == "BL") or (self.route == "BL" and x_route == "RB"):
                collision_point = (150, -2.83)
            #ここから追加
            #まず既存の衝突点と重なるもの
            elif (self.route == "BL" and x_route == "TL") or(self.route == "TL" and x_route == "BL"):
                collision_point = (141.8, 1.6)
            elif (self.route == "TL" and x_route == "RL") or(self.route == "RL" and x_route == "TL"):
                collision_point = (141.8, 1.6)
            elif (self.route == "LB" and x_route == "TB") or (self.route == "TB" and x_route == "LB"):
                collision_point = (148.4, -8.2)
            elif (self.route == "TB" and x_route == "RB") or (self.route == "RB" and x_route == "TB"):
                collision_point = (148.4, -8.2)
            elif (self.route == "BR" and x_route == "TR") or (self.route == "TR" and x_route == "BR"):
                collision_point = (158.2, -1.6)
            elif (self.route == "TR" and x_route == "LR") or (self.route == "LR" and x_route == "TR"):
                collision_point = (158.2, -1.6)
            #ここから十字路変更による追加分
            elif (self.route == "LT" and x_route == "BT") or (self.route == "BT" and x_route == "LT"):
                collision_point = (151.6, 8.2)
            elif (self.route == "LT" and x_route == "RT") or (self.route == "RT" and x_route == "LT"):
                collision_point = (151.6, 8.2)
            elif (self.route == "RT" and x_route == "BT") or (self.route == "BT" and x_route == "RT"):
                collision_point = (151.6, 8.2)
            elif (self.route == "TB" and x_route == "BL") or (self.route == "BL" and x_route == "TB"):
                collision_point = (148.4, -1)
            elif (self.route == "LT" and x_route == "BL") or (self.route == "BL" and x_route == "LT"):
                collision_point = (147.17, 0)
            elif (self.route == "LT" and x_route == "TB") or (self.route == "TB" and x_route == "LT"):
                collision_point = (148.4, 1)
            elif (self.route == "LT" and x_route == "RL") or (self.route == "RL" and x_route == "LT"):
                collision_point = (149, 1.6)
            elif (self.route == "LT" and x_route == "TR") or (self.route == "TR" and x_route == "LT"):
                collision_point = (150, 2.83)
            elif (self.route == "TR" and x_route == "RL") or (self.route == "RL" and x_route == "TR"):
                collision_point = (151, 1.6)
            elif (self.route == "TR" and x_route == "BT") or (self.route == "BT" and x_route == "TR"):
                collision_point = (151.6, 1)
            elif (self.route == "TR" and x_route == "RB") or (self.route == "RB" and x_route == "TR"):
                collision_point = (152.83, 0)
            elif (self.route == "RB" and x_route == "BT") or (self.route == "BT" and x_route == "RB"):
                collision_point = (151.6, -1)
            elif (self.route == "RL" and x_route == "TB") or (self.route == "TB" and x_route == "RL"):
                collision_point = (148.4, 1.6)
            elif (self.route == "RL" and x_route == "BT") or (self.route == "BT" and x_route == "RL"):
                collision_point = (151.6, 1.6)
            elif (self.route == "LR" and x_route == "TB") or (self.route == "TB" and x_route == "LR"):
                collision_point = (148.4, -1.6)
            elif (self.route == "LR" and x_route == "BT") or (self.route == "BT" and x_route == "LR"):
                collision_point = (151.6, -1.6)
            #ここまで

            own_passtime = None
            other_passtime = None

            for i in range(1, t_last):
                # 車頭間隔を確保
                own_pos_x = own_path.x[startItr_own+i]
                own_pos_y = own_path.y[startItr_own+i]
                other_pos_x = x.x[startItr_x+i]
                other_pos_y = x.y[startItr_x+i]

                if collision_point and ((140.0 < own_pos_x < 160.0 and -7.0 < own_pos_y < 3.2) or (140.0 < other_pos_x < 160.0 and -7.0 < other_pos_y < 3.2)):

                    # 衝突候補点を通過した時刻を計算
                    own_pass_x = (collision_point[0] - own_pos_x)*(collision_point[0] - own_path.x[0])
                    own_pass_y = (collision_point[1] - own_pos_y)*(collision_point[1] - own_path.y[0])
                    other_pass_x = (collision_point[0] - other_pos_x)*(collision_point[0] - x.x[0])
                    other_pass_y = (collision_point[1] - other_pos_y)*(collision_point[1] - x.y[0])

                    if own_passtime is None and own_pass_x <= 0 and own_pass_y <= 0:
                        own_passtime = own_path.t[startItr_own+i]
                    if other_passtime is None and other_pass_x <= 0 and other_pass_y <= 0:
                        other_passtime = x.t[startItr_x+i]

                    # PETが閾値を下回る場合に衝突とみなす
                    if own_passtime and other_passtime and abs(own_passtime - other_passtime) <= PET_th:
                        print("collide at", own_path.pathID, own_path.type, "other", x.pathID, x.type, "time", x.t[startItr_x+i], \
                            "PET", abs(own_passtime - other_passtime))
                        isCollide = True
                        dict["path"] = x
                        dict["collideID"] = x.vehID
                        dict["collide_x"] = collision_point[0]
                        dict["collide_y"] = collision_point[1]
                        dict["speed"] = 5.56
                        dict["duration"] = max(own_passtime, other_passtime) - self.simTime
                        break

                else:
                    # estimate speed at each step
                    own_dx = (own_pos_x - own_path.x[startItr_own+i-1]) / timeStep
                    own_dy = (own_pos_y - own_path.y[startItr_own+i-1]) / timeStep
                    other_dx = (other_pos_x - x.x[startItr_x+i-1]) / timeStep
                    other_dy = (other_pos_y - x.y[startItr_x+i-1]) / timeStep

                    if own_pos_y > 0:
                        if own_pos_x > other_pos_x:
                            if abs(own_pos_x - other_pos_x) < max(self.length, abs(own_dx)*tau) and abs(own_pos_y - other_pos_y) < self.width:
                                isCollide = True
                        else:
                            if abs(own_pos_x - other_pos_x) < max(self.length, abs(other_dx)*tau) and abs(own_pos_y - other_pos_y) < self.width:
                                isCollide = True
                    
                    elif own_pos_y > -3.2:
                        if own_pos_x < other_pos_x:
                            if abs(own_pos_x - other_pos_x) < max(self.length, abs(own_dx)*tau) and abs(own_pos_y - other_pos_y) < self.width:
                                isCollide = True
                        else:
                            if abs(own_pos_x - other_pos_x) < max(self.length, abs(other_dx)*tau) and abs(own_pos_y - other_pos_y) < self.width:
                                isCollide = True

                    else:
                        if own_pos_y < other_pos_y:
                            if abs(own_pos_y - other_pos_y) < max(self.length, abs(own_dy)*tau) and abs(own_pos_x - other_pos_x) < self.width:
                                isCollide = True
                        else:
                            if abs(own_pos_y - other_pos_y) < max(self.length, abs(other_dy)*tau) and abs(own_pos_x - other_pos_x) < self.width:
                                isCollide = True

                    if isCollide:
                        # print("collide at", own_path.pathID, own_path.type, "other", x.pathID, x.type, "time", x.t[startItr_x+i],\
                        #     "own_pos (", own_pos_x, ",", own_pos_y, ") other_pos (", other_pos_x, ",", other_pos_y, ")")

                        dict["path"] = x
                        dict["collideID"] = x.vehID
                        dict["collide_x"] = other_pos_x
                        dict["collide_y"] = other_pos_y
                        dict["speed"] = other_dx
                        dict["duration"] = x.t[startItr_x+i] - self.simTime
                        break
            
            if isCollide:
                collision_list.append(dict)
            else:
                notCollision_list.append(x)

        return collision_list, notCollision_list


    # 経路変更の必要があるか判定
    def checkPathChangeNecessity(self):

        if self.plannedPath and self.pos_y >= -50.0 and self.route in ["BR", "BL"] and self.road == "bottom": #とりあえず右左折だけにしておく
            return True
        #以下、一応追加
        elif self.plannedPath and self.pos_y <= 50.0 and self.route in ["TR", "TL"] and self.road == "top":
            return True
        elif self.plannedPath and self.pos_x <= 200.0 and self.route in ["RT", "RB"] and self.road == "-right":
            return True
        elif self.plannedPath and self.pos_x >= 100.0 and self.route in ["LT", "LB"] and self.road == "left":
            return True
        else:
            return False


    def judgeYield(self, collision_list, ob):
        if thesis_tiv.enabled(self):
            return thesis_tiv.judge_yield(self, collision_list, ob, traci)
        
        desired_list = []
        for i in collision_list:
            desired_list.append(i["path"].pathID)
        print("Negotiation list", desired_list)
        
        if self.WithAgreementPhase:
            if self.isWaitAgree and self.waitPath.pathID in desired_list:
                # 他車両との合意待ち中は他との交渉は行わない
                return
            elif self.isWaitAgree and self.waitPath.pathID not in desired_list:
                # 合意待ち中に元の希望経路が無くなった場合，一から交渉を始める
                self.isWaitAgree = False
                self.waitAgreeID = []
                self.receiveAgreeID = []
                self.waitPath = None

        for path in collision_list:
            leadPath = path["path"]
            
            # 同車線の車両の場合には無視（先頭の車両が優先権を持つ）
            if traci.vehicle.getRoadID(leadPath.vehID) == self.road:
                continue

            # 一度拒否した希望経路は経路が変わるまで判定しない
            if leadPath.pathID in self.yetJudgedList:
                continue

            print("judge yield to", leadPath.vehID)

            # R(X) uses the maximum speed of the vehicle whose trajectory is
            # being evaluated.  Do not reuse the accepting vehicle's value
            # for the requesting vehicle's desired trajectory.
            ego_max_speed = traci.vehicle.getAllowedSpeed(self.id)
            desired_max_speed = traci.vehicle.getAllowedSpeed(leadPath.vehID)

            collide_x = path["collide_x"]
            collide_y = path["collide_y"]        
            # 道を譲る場合は代替経路を生成
            alterPaths = self.generateAlterPath(path, ob)
            print("gen alter path", len(alterPaths))

            if len(alterPaths) == 0:
                print("cannot generate alter paths")
                self.yetJudgedList.append(leadPath.pathID)
                self.count_refuse_physics += 1
                continue

            else:
                self.alter_straight_path = self.selectBestPath(alterPaths)

                # 経路変更による車速の増減を比較
                if self.alter_straight_path:
                    utility = 0
                    for path in self.receivedPaths:
                        if path.vehID == leadPath.vehID and path.type == "planned":
                            # 経路変更による速度の増加量
                            d_ego_speed = min(self.alter_straight_path.s_d) - maxSpeed
                            d_alt_speed = leadPath.s_d[-1] - path.s_d[-1] # 最終速度の増加量

                            # 経路変更による減速度の改善量
                            alter_decel = 0.0
                            ego_decel = 0.0
                            desire_decel = 0.0
                            alt_decel = 0.0

                            # 経路変更により強いられる減速の絶対値和
                            for i in self.alter_straight_path.s_dd:
                                if i < 0:
                                    alter_decel += i
                            for i in self.plannedPath.s_dd:
                                if i < 0:
                                    ego_decel += i
                            for i in leadPath.s_dd:
                                if i < 0:
                                    desire_decel += i
                            for i in path.s_dd:
                                if i < 0:
                                    alt_decel += i

                            d_ego_speed = round((d_ego_speed / maxSpeed), 2)
                            d_alt_speed = round((d_alt_speed / maxSpeed), 2)
                            
                            # 後続の車両台数
                            followVehs = 0
                            for i in self.receivedPaths:
                                if self.route in ["LR"]:
                                    if i.x[0] < self.pos_x and abs(i.y[0] - self.pos_y) < 1.0:
                                        followVehs += 1
                                elif self.route in ["RL"]:
                                    if i.x[0] > self.pos_x and abs(i.y[0] - self.pos_y) < 1.0:
                                        followVehs += 1
                                elif self.route in ["BL", "BR"]:
                                    if i.y[0] < self.pos_y and abs(i.x[0] - self.pos_x) < 1.0:
                                        followVehs += 1
                            
                            #ここから追加
                            followVehs_alt_list = []
                            followVehs_ego_list = []
                            followCoefficient1_alt_list = []
                            followCoefficient1_ego_list = []
                            followCoefficientnew_alt_list = []
                            followCoefficientnew_ego_list = []


                            for i in self.receivedPaths:
                                if self.route in ["LR", "LT", "LB"]:
                                    if i.x[0] < self.pos_x and abs(i.y[0] - self.pos_y) < 1.0:
                                        co_ego = (commRange - self.pos_x + i.x[0]) / commRange
                                        print(self.pos_x - i.x[0])
                                        co_ego_new = self.calculateBehindRate(
                                            self.pos_x - i.x[0], ego_max_speed
                                        )
                                        check_duplication = 0
                                        for j in followVehs_ego_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_ego_list.append(i.vehID)
                                            followCoefficient1_ego_list.append(co_ego)
                                            followCoefficientnew_ego_list.append(co_ego_new * i.s_d[-1])
                                        print(co_ego_new, "*", i.s_d[-1])
                                elif self.route in ["RL", "RT", "RB"]:
                                    if i.x[0] > self.pos_x and abs(i.y[0] - self.pos_y) < 1.0:
                                        co_ego = (commRange - i.x[0] + self.pos_x) / commRange
                                        print(i.x[0] - self.pos_x)
                                        co_ego_new = self.calculateBehindRate(
                                            i.x[0] - self.pos_x, ego_max_speed
                                        )
                                        check_duplication = 0
                                        for j in followVehs_ego_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_ego_list.append(i.vehID)
                                            followCoefficient1_ego_list.append(co_ego)
                                            followCoefficientnew_ego_list.append(co_ego_new * i.s_d[-1])
                                        print(co_ego_new, "*", i.s_d[-1])
                                elif self.route in ["BL", "BR", "BT"]:
                                    if i.y[0] < self.pos_y and abs(i.x[0] - self.pos_x) < 1.0:
                                        co_ego = (commRange - self.pos_y + i.y[0]) / commRange
                                        print(self.pos_y - i.y[0])
                                        co_ego_new = self.calculateBehindRate(
                                            self.pos_y - i.y[0], ego_max_speed
                                        )
                                        check_duplication = 0
                                        for j in followVehs_ego_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_ego_list.append(i.vehID)
                                            followCoefficient1_ego_list.append(co_ego)
                                            followCoefficientnew_ego_list.append(co_ego_new * i.s_d[-1])
                                        print(co_ego_new, "*", i.s_d[-1])
                                elif self.route in ["TR", "TL", "TB"]:
                                    if i.y[0] > self.pos_y and abs(i.x[0] - self.pos_x) < 1.0:
                                        co_ego = (commRange - i.y[0] + self.pos_y) / commRange
                                        print(i.y[0] - self.pos_y)
                                        co_ego_new = self.calculateBehindRate(
                                            i.y[0] - self.pos_y, ego_max_speed
                                        )
                                        check_duplication = 0
                                        for j in followVehs_ego_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_ego_list.append(i.vehID)
                                            followCoefficient1_ego_list.append(co_ego)
                                            followCoefficientnew_ego_list.append(co_ego_new * i.s_d[-1])
                                        print(co_ego_new, "*", i.s_d[-1])


                                if path.x[0] < 145:
                                    if i.x[0] < path.x[0] and abs(i.y[0] - path.y[0]) < 1.0:
                                        check_duplication = 0
                                        for j in followVehs_alt_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_alt_list.append(i.vehID)
                                            co_alt = (commRange - path.x[0] + i.x[0]) / commRange
                                            print(path.x[0] - i.x[0])
                                            co_alt_new = self.calculateBehindRate(
                                                path.x[0] - i.x[0], desired_max_speed
                                            )
                                            followCoefficient1_alt_list.append(co_alt)
                                            followCoefficientnew_alt_list.append(co_alt_new * i.s_d[-1])
                                        print(co_alt_new, "*", i.s_d[-1])
                                elif path.x[0] > 155:
                                    if i.x[0] > path.x[0] and abs(i.y[0] - path.y[0]) < 1.0:
                                        check_duplication = 0
                                        for j in followVehs_alt_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_alt_list.append(i.vehID)
                                            co_alt = (commRange - i.x[0] + path.x[0]) / commRange 
                                            print(i.x[0] - path.x[0])
                                            co_alt_new = self.calculateBehindRate(
                                                i.x[0] - path.x[0], desired_max_speed
                                            )
                                            followCoefficient1_alt_list.append(co_alt)
                                            followCoefficientnew_alt_list.append(co_alt_new * i.s_d[-1])
                                        print(co_alt_new, "*", i.s_d[-1])
                                elif path.x[0] > 150 and path.x[0] < 155:
                                    if i.y[0] < path.y[0] and abs(i.x[0] - path.x[0]) < 1.0:
                                        check_duplication = 0
                                        for j in followVehs_alt_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_alt_list.append(i.vehID)
                                            co_alt = (commRange - path.y[0] + i.y[0]) / commRange
                                            print(path.y[0] - i.y[0])
                                            co_alt_new = self.calculateBehindRate(
                                                path.y[0] - i.y[0], desired_max_speed
                                            )
                                            followCoefficient1_alt_list.append(co_alt)
                                            followCoefficientnew_alt_list.append(co_alt_new * i.s_d[-1])
                                        print(co_alt_new, "*", i.s_d[-1])
                                elif path.x[0] > 145 and path.x[0] < 150:
                                    if i.y[0] > path.y[0] and abs(i.x[0] - path.x[0]) < 1.0:
                                        check_duplication = 0
                                        for j in followVehs_alt_list:
                                            if j == i.vehID:
                                                check_duplication += 1
                                        if check_duplication == 0:
                                            followVehs_alt_list.append(i.vehID)
                                            co_alt = (commRange - i.y[0] + path.y[0]) / commRange
                                            print(i.y[0] - path.y[0])
                                            co_alt_new = self.calculateBehindRate(
                                                i.y[0] - path.y[0], desired_max_speed
                                            )
                                            followCoefficient1_alt_list.append(co_alt)
                                            followCoefficientnew_alt_list.append(co_alt_new * i.s_d[-1])
                                        print(co_alt_new, "*", i.s_d[-1])

                            print(followVehs_ego_list)
                            print(followVehs_alt_list)
                            print(followCoefficientnew_ego_list)
                            print(followCoefficientnew_alt_list)
                            followVehs_ego = len(set(followVehs_ego_list))
                            followVehs_alt = len(set(followVehs_alt_list))

                            followCoefficient1_ego = sum(followCoefficient1_ego_list)
                            followCoefficient1_alt = sum(followCoefficient1_alt_list)
                            followCoefficientnew_ego = sum(followCoefficientnew_ego_list)
                            followCoefficientnew_alt = sum(followCoefficientnew_alt_list)
                            print(followCoefficient1_ego)
                            print(followCoefficient1_alt)
                            print(followCoefficientnew_ego)
                            print(followCoefficientnew_alt)
                            #ここまで（既存研究の判定分）

                            #ここから追加
                            collide_time_ego = 500
                            collide_distance_min = 500
                            if self.route in ["LR", "LT", "LB", "RL", "RT", "RB"]:
                                print(len(self.plannedPath.x))
                                for a in range(len(self.plannedPath.x)):
                                    print(self.plannedPath.x[a], self.plannedPath.y[a])
                                    collide_distance_x = abs(self.plannedPath.x[a] - collide_x)
                                    if collide_distance_x < collide_distance_min:
                                        collide_time_ego = a
                                        collide_distance_min = collide_distance_x
                                    elif collide_distance_x < 0.05:
                                        collide_time_ego = a
                                        break

                            elif self.route in ["BL", "BR", "BT", "TR", "TL", "TB"]:
                                print(len(self.plannedPath.y))
                                for a in range(len(self.plannedPath.y)):
                                    collide_distance_y = abs(self.plannedPath.y[a] - collide_y)
                                    if collide_distance_y < collide_distance_min:
                                        collide_time_ego = a
                                        collide_distance_min = collide_distance_y
                                    elif collide_distance_y < 0.05:
                                        collide_time_ego = a
                                        break

                            print("collide_time_ego", collide_time_ego, collide_distance_min)
                            print("coeff_ego", collide_time_ego + followCoefficientnew_ego)


                            collide_time_alt = 500
                            collide_distance_min = 500
                            if leadPath.x[0] < 145 or leadPath.x[0] > 155:
                                print(len(leadPath.x))
                                for a in range(len(leadPath.x)):
                                    collide_distance_x = abs(leadPath.x[a] - collide_x)
                                    if collide_distance_x < collide_distance_min:
                                        collide_time_alt = a
                                        collide_distance_min = collide_distance_x
                                    elif collide_distance_x < 0.05:
                                        collide_time_alt = a
                                        break

                            elif leadPath.x[0] < 155 and leadPath.x[0] > 145:
                                print(len(leadPath.y))
                                for a in range(len(leadPath.y)):
                                    collide_distance_y = abs(leadPath.y[a] - collide_y)
                                    if collide_distance_y < collide_distance_min:
                                        collide_time_alt = a
                                        collide_distance_min = collide_distance_y
                                    elif collide_distance_y < 0.05:
                                        collide_time_alt = a
                                        break

                            print("collide_time_alt", collide_time_alt, collide_distance_min)
                            print("coeff_alt", collide_time_alt + followCoefficientnew_alt)

                            #ここまで






                            k1 = 1
                            #utility = self.alpha*(d_ego_speed*(1+followVehs)) + (1-self.alpha)*(d_alt_speed)
                            #全て受け入れ　alpha = 1
                            if self.alpha == 1:
                                utility = 1

                            #道路交通法ベース（直進車両優先） alpha = 2
                            elif self.alpha == 2:
                                utility = thesis_baselines.act_utility(self.route)

                            #PriMa(20%) alpha = 3
                            elif self.alpha == 3:
                                utility = 0.2 - (self.plannedPath.s_d[1] - min(self.alter_straight_path.s_d))/self.plannedPath.s_d[1]

                            #PriMa(40%)  alpha = 4
                            elif self.alpha == 4:
                                utility = 0.4 - (self.plannedPath.s_d[1] - min(self.alter_straight_path.s_d))/self.plannedPath.s_d[1]

                            #卒論ベース  alpha = 5
                            #improvement function (linear)
                            elif self.alpha == 5:
                                utility = d_ego_speed*(1+followCoefficient1_ego) + d_alt_speed*(1+followCoefficient1_alt)

                            #修論提案（環境優先度のみ） alpha = 6
                            elif self.alpha == 6:
                                coeff_ego = (
                                    collide_time_ego * timeStep
                                    + R_co * (
                                        self.plannedPath.s_d[-1]
                                        + followCoefficientnew_ego
                                    )
                                )
                                coeff_alt = (
                                    collide_time_alt * timeStep
                                    + R_co * (
                                        leadPath.s_d[-1]
                                        + followCoefficientnew_alt
                                    )
                                )
                                utility = coeff_ego - coeff_alt

                            #修論提案（性能優先度込み）  alpha = 7
                            elif self.alpha == 7:
                                ego_max_accel = traci.vehicletype.getAccel(self.typeID)
                                desired_type_id = traci.vehicle.getTypeID(leadPath.vehID)
                                desired_max_accel = traci.vehicletype.getAccel(desired_type_id)

                                coeff_ego = (
                                    collide_time_ego * timeStep
                                    + R_co * (
                                        self.plannedPath.s_d[-1]
                                        + followCoefficientnew_ego
                                    )
                                    + R_per * ego_max_accel
                                )
                                coeff_alt = (
                                    collide_time_alt * timeStep
                                    + R_co * (
                                        leadPath.s_d[-1]
                                        + followCoefficientnew_alt
                                    )
                                    + R_per * desired_max_accel
                                )
                                utility = coeff_ego - coeff_alt


                            print(self.id, " yield to", leadPath.vehID, "because utirity is ", utility)
                            #print("utility: ", utility, "= ", self.alpha,"*(",d_ego_speed, "*(", 1+followVehs, ")) + (", 1-self.alpha, ")*(", d_alt_speed, ")")
                            print("utility: ", utility, "= ", d_ego_speed, "*(", 1+followCoefficient1_ego, ") + ", d_alt_speed, "*(", 1+followCoefficient1_alt, ")")
                            if self.alpha in [6, 7]:
                                print("TIV utility:", utility, "=", coeff_ego, "-", coeff_alt)

                    # 両車両の加速度の増減が閾値以上であれば道を譲る
                    if thesis_baselines.accepts_utility(self.alpha, utility, yield_th) or (self.status=="yield" and self.leader==leadPath.vehID):
                        self.count_accept_utility += 1

                        self.pathID += 1
                        path_id = self.id + "_" + str(self.pathID)
                        self.alter_straight_path.pathID = path_id
                        self.alter_straight_path.vehID = self.id

                        if self.WithAgreementPhase:
                            self.alter_straight_path.type = "alter"
                            self.alter_straight_path.yieldTo = leadPath.vehID

                            # 他の車両の交渉受け入れを待つ
                            self.waitAgreeID = leadPath.negotiationID
                            self.receiveAgreeID.append(self.id)
                            self.isWaitAgree = True
                            self.waitPath = leadPath
                            return
                        
                        else:
                            self.alter_straight_path.type = "planned"
                            self.plannedPath = self.alter_straight_path
                            self.alter_straight_path = None
                            self.status = "yield"
                            self.leader = leadPath.vehID
                            self.leadPath = leadPath
                            print("alter to", leadPath.pathID)
                            self.isPathValid = True

                    else:
                        self.yetJudgedList.append(leadPath.pathID)
                        self.count_refuse_utility +=1


    def sendMCM(self, central_path_server):
        if thesis_tiv.enabled(self):
            return thesis_tiv.send_mcm(self, central_path_server, traci)
        # send PLANNED path
        if self.plannedPath:
            self.count_send_PT += 1
            # 経路がmaxPathLen秒以上ある場合にはmaxT秒分だけ送る
            if len(self.plannedPath.t) > round(maxPathLen/timeStep):
                count = round(maxPathLen/timeStep)+1
                tmp = copy.deepcopy(self.plannedPath)
                tmp.t = tmp.t[:count]
                tmp.d = tmp.d[:count]
                tmp.d_d = tmp.d_d[:count]
                tmp.d_dd = tmp.d_dd[:count]
                tmp.d_ddd = tmp.d_ddd[:count]
                tmp.s = tmp.s[:count]
                tmp.s_d = tmp.s_d[:count]
                tmp.s_dd = tmp.s_dd[:count]
                tmp.s_ddd = tmp.s_ddd[:count]
                tmp.x = tmp.x[:count]
                tmp.y = tmp.y[:count]

                central_path_server.append(tmp)
            
            else:
                central_path_server.append(self.plannedPath)

        # send DESIRED path
        if self.desiredPaths:
            for dp in self.desiredPaths:
                self.count_send_DT += 1
                central_path_server.append(dp)

        # send ALTER path
        if self.alter_straight_path:
            self.count_send_AT += 1
            cp = copy.deepcopy(self.alter_straight_path)
            central_path_server.append(cp)

    #MCMを受信
    def receiveMCM(self, central_path_server):
        # 通信範囲内の他車両の経路情報を受信
        self.receivedPaths = [path for path in central_path_server \
                if (path.vehID != self.id and np.sqrt((self.pos_x-path.x[0])**2+(self.pos_y-path.y[0])**2) <= commRange)]

        # 他の車両が交渉に合意しているかをチェック
        if self.WithAgreementPhase and self.isWaitAgree:
            for path in self.receivedPaths:
                if self.alter_straight_path.yieldTo == path.yieldTo:
                    self.receiveAgreeID.append(path.vehID)


    #経路を10秒後まで延長
    def extendPath(self, path):
        count = round((self.simTime - path.t[0]) / timeStep)
        lack = 101-(len(path.t) - count)

        path.t = path.t[count:]
        path.t.extend([round(path.t[-1]+timeStep*(i+1), 3) for i in range(lack)])
        path.s_d = path.s_d[count:]
        path.s_d.extend([path.s_d[-1] for i in range(lack)])
        path.s_dd.extend([path.s_dd[-1] for i in range(lack)])
        path.s_ddd.extend([path.s_ddd[-1] for i in range(lack)])
        path.x = path.x[count:]
        path.x.extend([path.x[-1] + (path.x[-1] - path.x[-2])*(i+1) for i in range(lack)])
        path.y = path.y[count:]
        path.y.extend([path.y[-1] + (path.y[-1] - path.y[-2])*(i+1) for i in range(lack)])

        path.convergeTime = max(path.convergeTime - count*timeStep, 0)

        return path

    def generatePlannedPath(self, ob):
        path_candidates = []

        if self.status == "turn":
            print("extend path")
            # 予定経路を延長
            self.plannedPath = self.extendPath(self.plannedPath)
            return [self.plannedPath]

        if self.status == "yield":
            print("extend path")
            # 予定経路を延長
            path_candidates = [self.extendPath(self.plannedPath)]

            realLeader = traci.vehicle.getLeader(self.id)
            if realLeader and self.leader != realLeader[0]:
                leadPath = [path for path in self.receivedPaths if path.vehID == realLeader[0] and path.type=="planned"]
                if leadPath:
                    _, path_candidates = self.checkPathCollision(leadPath[0], path_candidates)

            if len(path_candidates) > 0:
                return path_candidates
            elif realLeader:
                self.leader = realLeader[0]

        if self.leader and self.leadPath: #前方車両に追従走行
            #前方車両が既に停止している場合
            if traci.vehicle.getSpeed(self.leader) < 0.1:

                #if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
                #    target_pos = 150 + traci.vehicle.getPosition(self.leader)[1] - D_0 - self.length
                #    c_s = 150 + self.pos_y
                #elif self.route == "LR" or self.road == "right":
                #    target_pos = traci.vehicle.getPosition(self.leader)[0] - D_0 - self.length
                #    c_s = self.pos_x
                #elif self.route == "RL" or self.road == "-left":
                #    target_pos = 300 - traci.vehicle.getPosition(self.leader)[0] - D_0 - self.length
                #    c_s = 300 - self.pos_x
                #ここから追加
                if self.road in ["bottom", "-top"]:
                    target_pos = 150 + traci.vehicle.getPosition(self.leader)[1] - D_0 - self.length
                    c_s = 150 + self.pos_y
                elif self.road in ["left", "right"]:
                    target_pos = traci.vehicle.getPosition(self.leader)[0] - D_0 - self.length
                    c_s = self.pos_x
                elif self.road in ["-right", "-left"]:
                    target_pos = 300 - traci.vehicle.getPosition(self.leader)[0] - D_0 - self.length
                    c_s = 300 - self.pos_x
                elif self.road in ["top", "-bottom"]:
                    target_pos = 150 - traci.vehicle.getPosition(self.leader)[1] - D_0 - self.length
                    c_s = 150 - self.pos_y
                #ここまで


                

                path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=c_s, c_d=0.0,\
                                                            target_pos=target_pos, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)

                # print("A gen stop len", len(path_candidates))
                if len(path_candidates) > 0:
                    self.status = "stop"
                    return path_candidates
                
            else:
                leadPath = [path for path in self.receivedPaths if path.vehID == self.leader and path.type=="planned"]
                if leadPath:
                    leadPath = self.extendPath(leadPath[0])

                # 前方車両が停止する場合
                for index, value in enumerate(leadPath.s_d):
                    if value == 0.0:
                        converge = index
                        #if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
                        #    target_pos = 150 + leadPath.y[converge] - D_0 - self.length
                        #    c_s = 150 + self.pos_y
                        #elif self.route in ["LR", "LB"] or self.road == "right":
                        #    target_pos = leadPath.x[converge] - D_0 - self.length
                        #    c_s = self.pos_x
                        #elif self.route in ["RL", "RB"] or self.road in ["-left", "-right"]:
                        #    target_pos = 300 - leadPath.x[converge] - D_0 - self.length
                        #    c_s = 300 - self.pos_x

                        #ここから追加
                        if self.road in ["bottom", "-top"]:
                            target_pos = 150 + leadPath.y[converge] - D_0 - self.length
                            c_s = 150 + self.pos_y
                        elif self.road in ["left", "right"]:
                            target_pos = leadPath.x[converge] - D_0 - self.length
                            c_s = self.pos_x
                        elif self.road in ["-right", "-left"]:
                            target_pos = 300 - leadPath.x[converge] - D_0 - self.length
                            c_s = 300 - self.pos_x
                        elif self.road in ["top", "-bottom"]:
                            target_pos = 150 - leadPath.y[converge] - D_0 - self.length
                            c_s = 150 - self.pos_y
                        #ここまで


                        path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=c_s, c_d=0.0,\
                                                                target_pos=target_pos, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)

                        _, path_candidates = self.checkPathCollision(leadPath, path_candidates)
                        print("B gen stop len", len(path_candidates))

                        if len(path_candidates) > 0:
                            self.status = "stop"
                            return path_candidates

                        break

                if leadPath.isTurn and self.road == "-bottom": #オリジナルは-bottomになっていたが、進入前のことを表現するためにはもしかしてbottom? -> bottomにすると余計な停止が起こるように
                    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 + self.pos_y, c_d=0.0,\
                                                                                target_pos=141.8, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)
                    _, path_candidates = self.checkPathCollision(leadPath, path_candidates)  
                    if len(path_candidates) > 0:
                        self.status = "follow"
                        return path_candidates
                    
                #ここから追加（これ何やってる？）
                #elif leadPath.isTurn and self.road == "top":
                #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 - self.pos_y, c_d=0.0,\
                #                                                                target_pos=141.8, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)
                #    _, path_candidates = self.checkPathCollision(leadPath, path_candidates)  
                #    if len(path_candidates) > 0:
                #        self.status = "follow"
                #        return path_candidates
                #elif leadPath.isTurn and self.road == "-right":
                #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=300 - self.pos_x, c_d=0.0,\
                #                                                                target_pos=141.8, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)
                #    _, path_candidates = self.checkPathCollision(leadPath, path_candidates)  
                #    if len(path_candidates) > 0:
                #        self.status = "follow"
                #        return path_candidates
                #elif leadPath.isTurn and self.road == "left":
                #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=self.pos_x, c_d=0.0,\
                #                                                                target_pos=141.8, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)
                #    _, path_candidates = self.checkPathCollision(leadPath, path_candidates)  
                #    if len(path_candidates) > 0:
                #        self.status = "follow"
                #        return path_candidates
                

                else:
                    duration = leadPath.t[-1] - self.simTime
                    target_speed = leadPath.s_d[-1]

                    if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
                        target_pos = 150 + leadPath.y[-1]
                        c_s = 150 + self.pos_y
                    elif self.route == "LR" or self.road == "right":
                        target_pos = leadPath.x[-1]
                        c_s = self.pos_x
                    elif self.route == "RL" or self.road == "-left":
                        target_pos = 300 - leadPath.x[-1]
                        c_s = 300 - self.pos_x
                    #ここから追加
                    elif self.route in ["LT", "LB"] and self.road not in ["-top", "-bottom"]:
                        target_pos = leadPath.x[-1]
                        c_s = self.pos_x
                    elif self.route in ["TL", "TR"] and self.road not in ["-left", "right"]:
                        target_pos = 150 - leadPath.y[-1]
                        c_s = 150 - self.pos_y
                    elif self.route in ["RT", "RB"] and self.road not in ["-top", "-bottom"]:
                        target_pos = 300 - leadPath.x[-1]
                        c_s = 300 - self.pos_x
                    elif self.route == "TB" or self.road == "-bottom":
                        target_pos = 150 - leadPath.y[-1]
                        c_s = 150 - self.pos_y
                    elif self.route == "BT" or self.road == "-top":
                        target_pos = 150 + leadPath.y[-1]
                        c_s = 150 + self.pos_y
                    #ここまで


                    # 安全のためのマージン
                    target_pos = target_pos - max(D_0 + self.length, target_speed*tau)
                    path_candidates = generate_frenet_frame(objects=ob, c_s=c_s, c_s_d=self.speed, c_s_dd=self.accel, c_d=0.0,\
                                                    target_speed=maxSpeed, mode="free", route=self.route, simTime=self.simTime, vehInstance=self)

                    _, path_candidates = self.checkPathCollision(leadPath, path_candidates)  
                    # print("gen follow to", self.leader ,"len", len(path_candidates))

                    if len(path_candidates) > 0:
                        self.status = "follow"
                        return path_candidates

        # 本線に出る車両は一時停止する
        if self.route in ["BR", "BL"] and self.road == "-bottom": #ここをbottomにすると一時停止するようになる
            path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 + self.pos_y, c_d=0.0,\
                                                            target_pos=141.8, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)
            # print("C gen stop len", len(path_candidates))
            if len(path_candidates) > 0:
                self.status = "stop"
                return path_candidates

        # 停止、追従経路が生成できない場合には追いつけないものと判断し自由走行を行う
        if len(path_candidates) == 0:
            self.status = "free"
            if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
                c_s = 150 + self.pos_y
            elif self.route == "LR" or self.road == "right":
                c_s = self.pos_x
                self.route = "LR"
            elif self.route == "RL" or self.road == "-left":
                c_s = 300 - self.pos_x
                self.route = "RL"
            #ここから追加
            elif self.route in ["LT", "LB"] and self.road not in ["-top", "-bottom"]:    
                c_s = self.pos_x
            elif self.route in ["TL", "TR"] and self.road not in ["-left", "right"]:
                c_s = 150 - self.pos_y
            elif self.route in ["RT", "RB"] and self.road not in ["-top", "-bottom"]:
                c_s = 300 - self.pos_x
            elif self.route == "TB" or self.road == "-bottom":
                c_s = 150 - self.pos_y
                self.route = "TB"
            elif self.route == "BT" or self.road == "-top":
                c_s = 150 + self.pos_y
                self.route = "BT"
            #ここまで


            path_candidates = generate_frenet_frame(objects=ob, c_s=c_s, c_s_d=self.speed, c_s_dd=self.accel, c_d=0.0,\
                                                target_speed=maxSpeed, mode="free", route=self.route, simTime=self.simTime, target_pos=141.8, vehInstance=self)

            if self.leadPath:
                _, path_candidates = self.checkPathCollision(self.leadPath, path_candidates)

            if len(path_candidates) > 0:
                pass
                # print("B gen free len", len(path_candidates))
            else:
                path_candidates = emergency_stop(self.pos_x, self.speed, self.pos_y, self.route)
                # print('Emergency Brake time', self.simTime, "veh", self.id, file=sys.stderr)
                self.status == "stop"
                for path in path_candidates:
                    path.t = [round(n+self.simTime, 1) for n in path.t]

        if len(path_candidates) == 0:
            path_candidates = emergency_stop(self.pos_x, self.speed, self.pos_y, self.route)

        return path_candidates


    def generateDesiredPath(self, ob):
        # 下から進入する車両（BR, BL）が停止線付近に近づいたときのみ希望経路（右左折）を生成
        #if self.route in ["BR", "BL"] and self.road == "bottom" and self.pos_y > -50.0:
        #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 + self.pos_y, c_d=0.0,\
        #                                        target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        #ここから追加 target_posは全て141.8で良いはず...
        #elif self.route in ["LT", "LB"] and self.road == "left" and self.pos_x > 100.0:
        #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=self.pos_x, c_d=0.0,\
        #                                        target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        #elif self.route in ["TR", "TL"] and self.road == "top" and self.pos_y < 50.0:
        #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 - self.pos_y, c_d=0.0,\
        #                                        target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        #elif self.route in ["RT", "RB"] and self.road == "-right" and self.pos_x < 200.0:
        #    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=300 - self.pos_x, c_d=0.0,\
        #                                        target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        #ここまで
        #試しに
        if self.route in ["BR", "BL", "BT"] and self.road == "bottom" and self.pos_y > -50.0:
            path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 + self.pos_y, c_d=0.0,\
                                                target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        elif self.route in ["LT", "LB", "LR"] and self.road == "left" and self.pos_x > 100.0:
            path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=self.pos_x, c_d=0.0,\
                                                target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        elif self.route in ["TR", "TL", "TB"] and self.road == "top" and self.pos_y < 50.0:
            path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 - self.pos_y, c_d=0.0,\
                                                target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        elif self.route in ["RT", "RB", "RL"] and self.road == "-right" and self.pos_x < 200.0:
            path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=300 - self.pos_x, c_d=0.0,\
                                                target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        #ここまで

        else:
            path_candidates = []

        return path_candidates


    def generateAlterPath(self, path, ob):

        #if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
        #    return []

        #elif self.route == "LR" or self.road == "right":
        #    c_s = self.pos_x
        #    self.route = "LR"
        #elif self.route == "RL" or self.road == "-left":
        #    c_s = 300 - self.pos_x
        #    self.route = "RL"
        #ここから追加

        if self.road in ["bottom", "-top"]:
            c_s = 150 + self.pos_y
        elif self.road in ["left", "right"]:
            c_s = self.pos_x
        elif self.road in ["-right", "-left"]:
            c_s = 300 - self.pos_x
        elif self.road in ["top", "-bottom"]:
            c_s = 150 - self.pos_y
        #ここまで



        collide_path = path["path"]
        if self.route == "LR":
            target_pos = path["collide_x"]
        elif self.route == "RL":
            target_pos = 300 - path["collide_x"]
        #ここから追加（一旦）
        elif self.route in ["LT", "LB"]:
            target_pos = path["collide_x"]
        elif self.route in ["RB", "RT"]:
            target_pos = 300 - path["collide_x"]
        elif self.route in ["BR", "BL"]:
            target_pos = 150 + path["collide_y"]
        elif self.route in ["TR", "TL", "TB"]:
            target_pos = 150 - path["collide_y"]
        #ここまで

        target_speed = path["speed"]
        duration = path["duration"]

        # 減速して対象車両の後方に着く
        alterPaths = generate_frenet_frame(objects=ob, c_s=c_s, c_s_d=self.speed, c_s_dd=self.accel, c_d=0.0,\
                                                        target_pos=target_pos, target_speed=target_speed, route=self.route, mode="yield", duration=duration, simTime=self.simTime, vehInstance=self)

        # 代替経路がしっかりと希望経路との衝突を避けられているかを判定
        _, alterPaths = self.checkPathCollision(collide_path, alterPaths)
        frontVeh = traci.vehicle.getLeader(self.id)
        if frontVeh:
            leadPath = [path for path in self.receivedPaths if path.vehID == frontVeh[0] and path.type == "planned"]
            if leadPath:
                _, alterPaths = self.checkPathCollision(leadPath[0], alterPaths)

        return alterPaths


    # find minimum cost path
    def selectBestPath(self, path_candidates):
        
        min_cost = float("inf")
        best_path = None

        for fp in path_candidates:
            if min_cost >= fp.cf:
                min_cost = fp.cf
                best_path = fp

        return best_path

    
    # 予定経路に従い速度調整
    def executionDrive(self):
        if self.plannedPath:
            next_time = round(self.simTime + timeStep, 1)
            for i in range(len(self.plannedPath.t)):
                if self.plannedPath.t[i] == next_time:
                    nextpos_x = self.plannedPath.x[i]
                    nextpos_y = self.plannedPath.y[i]
                    dif_pos = np.sqrt((nextpos_x - self.pos_x)**2 + (nextpos_y - self.pos_y)**2)
                    planned_speed = max(min(dif_pos/timeStep, maxSpeed), 0)
                    next_speed = min(planned_speed, self.speed + maxAccel*timeStep)
                    next_speed = max(next_speed, self.speed + maxDecel*timeStep, 0)
                    traci.vehicle.setSpeed(vehID=self.id, speed=next_speed)
                    break
                    

    def getStatistics(self):
        return self.count_accept_utility ,self.count_refuse_utility, self.count_refuse_physics,\
            self.count_send_PT, self.count_send_DT, self.count_send_AT


    # 周辺車両との距離を考慮し車線変更できるか判定
    def judgeAndDoLaneChange(self):
        dif_y = abs(self.pos_y - self.plannedPath.y[-1])
        if dif_y != 0 and dif_y < LANE_WIDTH/2:
            traci.vehicle.changeLane(vehID=self.id, laneIndex=1, duration=0)

    def calculateBehindRate(self, x, vehicle_max_speed):
        transition_distance = 4 * vehicle_max_speed
        peak_offset = vehicle_max_speed ** 2 / 4
        curve_denominator = peak_offset ** 2

        if x <= 5:
            return 1.0

        if x <= transition_distance:
            return (
                -R_max / curve_denominator
                * (x - (peak_offset + 5)) ** 2
                + R_max
            )

        if x <= 100:
            rate_at_transition = (
                -R_max / curve_denominator
                * (transition_distance - (peak_offset + 5)) ** 2
                + R_max
            )
            return (
                rate_at_transition
                / (100 - transition_distance)
                * (100 - x)
            )

        return 0.0


    def checkPassJunction(self):
        if self.passjunctionstatus == "now":
            self.passjunctionstatus = "passed"
        elif self.pos_x > 140 and self.pos_x < 160 and self.pos_y < 10 and self.pos_y > -10:
            if self.passjunctionstatus == "now":
                self.passjunctionstatus = "passed"
            elif self.passjunctionstatus == None:
                self.passjunctionstatus = "now"

    # destructor
    def __del__(self):
        print("delete veh:", self.id)
