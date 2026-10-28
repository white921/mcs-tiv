from __future__ import absolute_import
from __future__ import print_function
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

class Animation:

    def __init__(self, name):
        fig, self.ax = plt.subplots(figsize=(22,11))
        self.dirname = name
        os.makedirs("./gif/gif_" + self.dirname, exist_ok = True)


    def path_animation(self, vehicle_instance, time, objects=None):

        self.ax.cla()

        # 横方向の道路
        self.ax.add_patch(patches.Rectangle(xy=(0.0, -3.5), width=300, height=7, fc='dimgray'))
        #self.ax.plot([0, 300], [0.0, 0.0], color="dimgray", linewidth=33)
        #self.ax.plot([0, 142.8], [0.0, 0.0], color="dimgray", linewidth=33)
        #self.ax.plot([157.2, 300], [0.0, 0.0], color="dimgray", linewidth=33)
        self.ax.plot([0, 142.8], [-3.3, -3.3], color="white", linewidth=1)
        self.ax.plot([157.2, 300], [-3.3, -3.3], color="white", linewidth=1)
        self.ax.plot([0, 142.8], [0.0, 0.0], color="white", linewidth=1)
        self.ax.plot([157.2, 400], [0.0, 0.0], color="white", linewidth=1)
        #self.ax.plot([0, 300], [3.3, 3.3], color="white", linewidth=1)
        self.ax.plot([0, 142.8], [3.3, 3.3], color="white", linewidth=1)
        self.ax.plot([157.8, 300], [3.3, 3.3], color="white", linewidth=1)
        
        self.ax.plot([142.8, 142.8], [-3.2, 0.0], color="white", linewidth=1)
        self.ax.plot([157.2, 157.2], [0.0, 3.2], color="white", linewidth=1)
        

        # 縦方向の道路
        #self.ax.add_patch(patches.Rectangle(xy=(146.5, -150), width=7, height=150, fc='dimgray'))
        self.ax.add_patch(patches.Rectangle(xy=(146.5, -150), width=7, height=300, fc='dimgray'))
        self.ax.plot([146.7, 146.7], [-150, -7.2], color="white", linewidth=1)
        self.ax.plot([150, 150], [-150, -7.2], color="white", linewidth=1)
        self.ax.plot([153.2, 153.2], [-150, -7.2], color="white", linewidth=1)

        self.ax.plot([150, 153.2], [-7.2, -7.2], color="white", linewidth=1)
        #ここから追加
        self.ax.plot([146.7, 146.7], [7.2, 150], color="white", linewidth=1)
        self.ax.plot([150, 150], [7.2, 150], color="white", linewidth=1)
        self.ax.plot([153.2, 153.2], [7.2, 150], color="white", linewidth=1)

        self.ax.plot([146.7, 150], [7.2, 7.2], color="white", linewidth=1)
        #ここまで


        # 交差部の曲線
        self.ax.add_patch(patches.Rectangle(xy=(153.5, -7.2), width=3.7, height=3.7, fc='dimgray'))
        self.ax.add_patch(patches.Circle(xy=(157.2, -7.2), radius=3.7, fc='white'))

        self.ax.add_patch(patches.Rectangle(xy=(142.8, -7.2), width=3.7, height=3.7, fc='dimgray'))
        self.ax.add_patch(patches.Circle(xy=(142.8, -7.2), radius=3.7, fc='white'))

        #ここから追加
        self.ax.add_patch(patches.Rectangle(xy=(142.8, 3.5), width=3.7, height=3.7, fc='dimgray'))
        self.ax.add_patch(patches.Circle(xy=(142.8, 7.2), radius=3.7, fc='white'))

        self.ax.add_patch(patches.Rectangle(xy=(153.5, 3.5), width=3.7, height=3.7, fc='dimgray'))
        self.ax.add_patch(patches.Circle(xy=(157.2, 7.2), radius=3.7, fc='white'))
        #ここまで

        # 図の調整
        plt.title("time[s]:" + str(time))
        plt.xlim(0, 300)
        #plt.ylim(-150.0, 5.0)
        plt.ylim(-150.0, 150.0)
        plt.xticks([x*20 for x in range(16)])
        plt.subplots_adjust(left=0.04, right=0.98, bottom=0.05, top=0.95)


        for ins in vehicle_instance:

            #希望経路
            if ins.desiredPaths:
                self.ax.plot(ins.desiredPaths[0].x, ins.desiredPaths[0].y, color="red")
                self.ax.plot(ins.desiredPaths[0].x[::10], ins.desiredPaths[0].y[::10], color="red", marker=".", linewidth=0)
                self.ax.text(ins.pos_x, ins.pos_y-3, "DT:" + ins.desiredPaths[0].pathID, clip_on=True)
            #予定経路
            if ins.plannedPath:
                color = ins.myColor
                if ins.status == "yield":
                    color = "magenta"
                self.ax.plot(ins.plannedPath.x, ins.plannedPath.y, color=color)
                self.ax.plot(ins.plannedPath.x[::10], ins.plannedPath.y[::10], color=color, marker='.', markersize=10, linewidth=0)
                self.ax.text(ins.pos_x, ins.pos_y+0.2, "PT:" + ins.plannedPath.pathID, clip_on=True)

            #代替経路
            # if ins.alter_straight_path:    
            #     plt.plot(ins.alter_straight_path.x, ins.alter_straight_path.y, color="orange")
            #     plt.plot(ins.alter_straight_path.x[::10], ins.alter_straight_path.y[::10], color="orange", marker=".", linewidth=0)
                # plt.text(ins.pos_x, ins.pos_y-1, "AT:" + ins.alter_straight_path.pathID)
            # if ins.alter_change_path:
            #     plt.plot(ins.alter_change_path.x[1:], ins.alter_change_path.y[1:], color="gold")
            #     plt.plot(ins.alter_change_path.x[::10], ins.alter_change_path.y[::10], color="gold", marker=".", linewidth=0)
            #     plt.text(ins.pos_x-15, ins.pos_y-1, "AT_C:" + ins.alter_change_path.pathID)

        for ins in vehicle_instance:
            if ins.route in ["BR", "BL"]:
                mk = "^"
            elif ins.route in ["LR", "LB"]:
                mk = ">"
            elif ins.route in ["RL", "RB"]:
                mk = "<"
            elif ins.route == "TB":
                mk = "v"
            #ここから追加
            elif ins.route in ["BT"]:
                mk = "^"
            elif ins.route in ["LT"]:
                mk = ">"
            elif ins.route in ["RT"]:
                mk = "<"
            elif ins.route in ["TL", "TR"]:
                mk = "v"
            #ここまで

            color = ins.myColor
            if ins.status == "yield":
                color = "magenta"
                plt.text(ins.pos_x-5, ins.pos_y-2.0, "yield"+str(ins.leader), clip_on=True)
            elif ins.desiredPaths:
                color = "red"

            #現在地
            # self.ax.add_artist(AnnotationBbox(carimg, [ins.pos_x, ins.pos_y], xycoords="data", frameon=False))
            self.ax.plot(ins.pos_x, ins.pos_y, color=color, marker=mk, markersize=10)
            self.ax.text(ins.pos_x-8, ins.pos_y+1.0, str(round(ins.speed,1))+"m/s", clip_on=True)
            self.ax.text(ins.pos_x-1.2, ins.pos_y-0.5, ins.id, color='white', clip_on=True)
            self.ax.text(ins.pos_x-8, ins.pos_y-3.0, ins.route, clip_on=True)


        ## =================================================================================== ##
        ## =================================================================================== ##
        # zoomしたグラフの描画
        axins = self.ax.inset_axes([0.55, 0.03, 0.43, 0.43])
        # 横方向の道路
        axins.add_patch(patches.Rectangle(xy=(0.0, -3.5), width=300, height=7, fc='dimgray'))
        #axins.plot([0, 300], [0.0, 0.0], color="dimgray", linewidth=33)
        #axins.plot([0, 142.8], [0.0, 0.0], color="dimgray", linewidth=33)
        #axins.plot([157.2, 300], [0.0, 0.0], color="dimgray", linewidth=33)
        axins.plot([0, 142.8], [-3.3, -3.3], color="white", linewidth=1)
        axins.plot([157.2, 300], [-3.3, -3.3], color="white", linewidth=1)
        axins.plot([0, 142.8], [0.0, 0.0], color="white", linewidth=1)
        axins.plot([157.2, 400], [0.0, 0.0], color="white", linewidth=1)
        #axins.plot([0, 300], [3.3, 3.3], color="white", linewidth=1)
        axins.plot([0, 142.8], [3.3, 3.3], color="white", linewidth=1)
        axins.plot([157.8, 300], [3.3, 3.3], color="white", linewidth=1)
        
        axins.plot([142.8, 142.8], [-3.2, 0.0], color="white", linewidth=1)
        axins.plot([157.2, 157.2], [0.0, 3.2], color="white", linewidth=1)


        # 縦方向の道路
        #axins.add_patch(patches.Rectangle(xy=(146.5, -150), width=7, height=150, fc='dimgray'))
        axins.add_patch(patches.Rectangle(xy=(146.5, -150), width=7, height=300, fc='dimgray'))
        axins.plot([146.7, 146.7], [-150, -7.2], color="white", linewidth=1)
        axins.plot([150, 150], [-150, -7.2], color="white", linewidth=1)
        axins.plot([153.2, 153.2], [-150, -7.2], color="white", linewidth=1)

        axins.plot([150, 153.2], [-7.2, -7.2], color="white", linewidth=1)
        #ここから追加
        axins.plot([146.7, 146.7], [7.2, 150], color="white", linewidth=1)
        axins.plot([150, 150], [7.2, 150], color="white", linewidth=1)
        axins.plot([153.2, 153.2], [7.2, 150], color="white", linewidth=1)

        axins.plot([146.7, 150], [7.2, 7.2], color="white", linewidth=1)
        #ここまで

        # 交差部の曲線
        axins.add_patch(patches.Rectangle(xy=(153.5, -7.2), width=3.7, height=3.7, fc='dimgray'))
        axins.add_patch(patches.Circle(xy=(157.2, -7.2), radius=3.7, fc='white'))

        axins.add_patch(patches.Rectangle(xy=(143.1, -7.2), width=3.7, height=3.7, fc='dimgray'))
        axins.add_patch(patches.Circle(xy=(142.8, -7.2), radius=3.7, fc='white'))

        #ここから追加
        axins.add_patch(patches.Rectangle(xy=(142.8, 3.5), width=3.7, height=3.7, fc='dimgray'))
        axins.add_patch(patches.Circle(xy=(142.8, 7.2), radius=3.7, fc='white'))

        axins.add_patch(patches.Rectangle(xy=(153.5, 3.5), width=3.7, height=3.7, fc='dimgray'))
        axins.add_patch(patches.Circle(xy=(157.2, 7.2), radius=3.7, fc='white'))
        #ここまで

        for ins in vehicle_instance:

            #希望経路
            if ins.desiredPaths:
                axins.plot(ins.desiredPaths[0].x, ins.desiredPaths[0].y, color="red")
                axins.plot(ins.desiredPaths[0].x[::10], ins.desiredPaths[0].y[::10], color="red", marker=".", linewidth=0)
                axins.text(ins.pos_x, ins.pos_y-3, "DT:" + ins.desiredPaths[0].pathID, clip_on=True)
            #予定経路
            if ins.plannedPath:
                color = ins.myColor
                if ins.status == "yield":
                    color = "magenta"
                axins.plot(ins.plannedPath.x, ins.plannedPath.y, color=color)
                axins.plot(ins.plannedPath.x[::10], ins.plannedPath.y[::10], color=color, marker='.', markersize=10, linewidth=0)
                axins.text(ins.pos_x, ins.pos_y+0.2, "PT:" + ins.plannedPath.pathID, clip_on=True)

            # 代替経路
            # if ins.alter_straight_path:    
            #     plt.plot(ins.alter_straight_path.x, ins.alter_straight_path.y, color="orange")
            #     plt.plot(ins.alter_straight_path.x[::10], ins.alter_straight_path.y[::10], color="orange", marker=".", linewidth=0)
            #     plt.text(ins.pos_x, ins.pos_y-1, "AT:" + ins.alter_straight_path.pathID)
            # if ins.alter_change_path:
            #     plt.plot(ins.alter_change_path.x[1:], ins.alter_change_path.y[1:], color="gold")
            #     plt.plot(ins.alter_change_path.x[::10], ins.alter_change_path.y[::10], color="gold", marker=".", linewidth=0)
            #     plt.text(ins.pos_x-15, ins.pos_y-1, "AT_C:" + ins.alter_change_path.pathID)

        for ins in vehicle_instance:
            if ins.route in ["BR", "BL"]:
                mk = "^"
            elif ins.route in ["LR", "LB"]:
                mk = ">"
            elif ins.route in ["RL", "RB"]:
                mk = "<"
            elif ins.route == "TB":
                mk = "v"
            #ここから追加
            elif ins.route in ["BT"]:
                mk = "^"
            elif ins.route in ["LT"]:
                mk = ">"
            elif ins.route in ["RT"]:
                mk = "<"
            elif ins.route in ["TL", "TR"]:
                mk = "v"
            #ここまで

            color = ins.myColor
            if ins.status == "yield":
                color = "magenta"
                axins.text(ins.pos_x-2, ins.pos_y-2.0, "yield"+str(ins.leader), clip_on=True)
            elif ins.desiredPaths:
                color = "red"

            #現在地
            # self.ax.add_artist(AnnotationBbox(carimg, [ins.pos_x, ins.pos_y], xycoords="data", frameon=False))
            axins.plot(ins.pos_x, ins.pos_y, color=color, marker=mk, markersize=10)
            axins.text(ins.pos_x-4, ins.pos_y+1.0, str(round(ins.speed,1))+"m/s", clip_on=True)
            axins.text(ins.pos_x-1, ins.pos_y-0.5, ins.id, color='white', clip_on=True)

        # zoomしたグラフの設定
        x1, x2, y1, y2 = 120, 180, -30, 30
        axins.set_xlim(x1, x2)
        axins.set_ylim(y1, y2)
        axins.set_xticklabels([])
        axins.set_yticklabels([])

        self.ax.indicate_inset_zoom(axins)

        ## =================================================================================== ##
        ## =================================================================================== ##
        
        plt.pause(0.001)