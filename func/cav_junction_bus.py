import os
from re import S
import sys
import numpy as np
import copy
import time

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("please declare environment variable 'SUMO_HOME'")
import traci  # noqa
sys.path.append("../PathPlanning/FrenetOptimalTrajectory/")
from frenet_junction import generate_frenet_frame, emergency_stop

maxSpeed = 11.11 # [m/s]
maxAccel = 1.0 # [m/ss] 3.0
maxDecel = -3.0 # [m/ss] -5.0
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


class CAV_bus:
    # constructor
    def __init__(self, vehID, alpha, withAgree=False):
        self.id = str(vehID)
        # not allow autonomous lanechange
        traci.vehicle.setLaneChangeMode(vehID=self.id, lcm=0b000000000000)
        # control vehicle speed by traci
        traci.vehicle.setSpeedMode(vehID=self.id, sm=0b100000)

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

        self.pos_x = 0
        self.pos_y = 0
        if self.route in ["RL", "RB"]:
            self.pos_x = 300.0
            self.pos_y = 1.6
        if self.route in ["LR", "LB"]:
            self.pos_x = 0.0
            self.pos_y = -1.6
        elif self.route in ["BR", "BL"]:
            self.pos_x = 151.6
            self.pos_y = -150.0
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

        elif self.status == "yield": # 譲った相手が交差点を通過したらyield状態を解除
            if traci.vehicle.getRoadID(self.leader) in ["right", "-left"]:
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
            
            if self.road == "-bottom":
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
        if not self.plannedPath or round(self.simTime - self.plannedPath.t[0], 2) >= pathValidTime or self.isPathValid == False:

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
        # if x.vehID != self.id and x.isTurn == True and x.type == "planned" and self.route not in ["BL", "BR"]:
        #     return True
        

        if ego_path.type == x.type:
            route_priority = {"LR":1, "RL":1, "TB":1, "LB":2, "BR":2, "RB":3, "BL":4}
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
            if (self.route == "LR" and x_route == "RL") or (self.route == "RL" and x_route == "LR") or self.route == "TB" or x_route == "TB":
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

        if self.plannedPath and self.pos_y >= -50.0 and self.route in ["BR", "BL"] and self.road == "bottom":
            return True
        else:
            return False


    def judgeYield(self, collision_list, ob):
        
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

                            k1 = 1
                            #utility = self.alpha*(d_ego_speed*(1+followVehs)) + (1-self.alpha)*(d_alt_speed)
                            print(self.id, " yield to", leadPath.vehID, "because utirity is ", utility)

                    # 両車両の加速度の増減が閾値以上であれば道を譲る
                    if utility > yield_th or (self.status=="yield" and self.leader==leadPath.vehID):
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

        if self.leader: #前方車両に追従走行
            #前方車両が既に停止している場合
            if traci.vehicle.getSpeed(self.leader) < 0.1:

                if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
                    target_pos = 150 + traci.vehicle.getPosition(self.leader)[1] - D_0 - self.length
                    c_s = 150 + self.pos_y
                elif self.route == "LR" or self.road == "right":
                    target_pos = traci.vehicle.getPosition(self.leader)[0] - D_0 - self.length
                    c_s = self.pos_x
                elif self.route == "RL" or self.road == "-left":
                    target_pos = 300 - traci.vehicle.getPosition(self.leader)[0] - D_0 - self.length
                    c_s = 300 - self.pos_x

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
                        if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
                            target_pos = 150 + leadPath.y[converge] - D_0 - self.length
                            c_s = 150 + self.pos_y
                        elif self.route in ["LR", "LB"] or self.road == "right":
                            target_pos = leadPath.x[converge] - D_0 - self.length
                            c_s = self.pos_x
                        elif self.route in ["RL", "RB"] or self.road in ["-left", "-right"]:
                            target_pos = 300 - leadPath.x[converge] - D_0 - self.length
                            c_s = 300 - self.pos_x

                        path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=c_s, c_d=0.0,\
                                                                target_pos=target_pos, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)

                        _, path_candidates = self.checkPathCollision(leadPath, path_candidates)
                        print("B gen stop len", len(path_candidates))

                        if len(path_candidates) > 0:
                            self.status = "stop"
                            return path_candidates

                        break

                if leadPath.isTurn and self.road == "-bottom":
                    path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 + self.pos_y, c_d=0.0,\
                                                                                target_pos=141.8, target_speed=0, mode="stop", route=self.route, simTime=self.simTime, vehInstance=self)
                    _, path_candidates = self.checkPathCollision(leadPath, path_candidates)  
                    if len(path_candidates) > 0:
                        self.status = "follow"
                        return path_candidates

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
        if self.route in ["BR", "BL"] and self.road == "-bottom":
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
                self.status = "stop"
                for path in path_candidates:
                    path.t = [round(n+self.simTime, 1) for n in path.t]

        if len(path_candidates) == 0:
            path_candidates = emergency_stop(self.pos_x, self.speed, self.pos_y, self.route)
            self.status = "stop"

        return path_candidates


    def generateDesiredPath(self, ob):
        # 下から進入する車両（BR, BL）が停止線付近に近づいたときのみ希望経路（右左折）を生成
        if self.route in ["BR", "BL"] and self.road == "bottom" and self.pos_y > -50.0:
            path_candidates = generate_frenet_frame(objects=ob, c_s_d=self.speed, c_s_dd=self.accel, c_s=150 + self.pos_y, c_d=0.0,\
                                                target_pos=141.8, target_speed=0, mode="turn", route=self.route, simTime=self.simTime, vehInstance=self)
        else:
            path_candidates = []

        return path_candidates


    def generateAlterPath(self, path, ob):

        if self.route in ["BR", "BL"] and self.road not in ["right", "-left"]:
            return []

        elif self.route == "LR" or self.road == "right":
            c_s = self.pos_x
            self.route = "LR"
        elif self.route == "RL" or self.road == "-left":
            c_s = 300 - self.pos_x
            self.route = "RL"

        collide_path = path["path"]
        if self.route == "LR":
            target_pos = path["collide_x"]
        elif self.route == "RL":
            target_pos = 300 - path["collide_x"]
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
                    next_speed = max(min(dif_pos/timeStep, maxSpeed), 0)
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


    # destructor
    def __del__(self):
        print("delete veh:", self.id)

