from __future__ import absolute_import
from __future__ import print_function
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os
from matplotlib.offsetbox import OffsetImage, AnnotationBbox

class Animation:

    def __init__(self, name):
        fig, self.ax = plt.subplots(figsize=(14,2))
        self.dirname = name
        os.makedirs("./gif/gif_" + self.dirname, exist_ok = True)

    def path_animation(self, vehicle_instance, time, objects=None):

        self.ax.cla()
        # 道路描画と軸の情報
        plt.plot([0, 400], [-3.2, -3.2], color="yellowgreen", linewidth=300)
        plt.plot([0, 400], [-6.4, -6.4], color="dimgray", linewidth=105)
        plt.plot([0, 400], [-3.2, -3.2], color="white", linewidth=2)
        # plt.plot([0, 400], [-3.2, -3.2], color="white", linestyle="dotted", dashes=[11, 13], linewidth=2)
        plt.plot([0, 400], [-6.4, -6.4], color="white", linestyle="dotted", dashes=[11, 13], linewidth=2)
        plt.plot([0, 400], [-9.6, -9.6], color="white", linewidth=2)
        
        plt.title("time[s]:" + str(time))
        plt.xlim(0, 400)
        plt.ylim(-10.0, -3.0)
        plt.xticks([x*20 for x in range(21)])
        plt.yticks([-9.6, -8.0, -6.4, -4.8, -3.2])
        plt.subplots_adjust(left=0.04, right=0.98, bottom=0.1, top=0.9)

        # 障害物の画像
        bace = os.path.dirname(os.path.abspath(__file__)) # 実行ファイルのディレクトリ名
        coneimg = plt.imread(os.path.join(bace, "safetycone.png"), format='png') # パスの連結
        coneimg = OffsetImage(coneimg, zoom=0.1)

        # 車線封鎖
        # self.ax.add_artist(AnnotationBbox(coneimg, [200, -8.0], xycoords="data", frameon=False))
        # for i in range(10):
            # self.ax.add_artist(AnnotationBbox(coneimg, [i*20 + 200, -8.0], xycoords="data", frameon=False))
        for i in range(5):
            self.ax.add_artist(AnnotationBbox(coneimg, [i*20 + 300, -8.0], xycoords="data", frameon=False))

        for ins in vehicle_instance:
            #予定経路
            if ins.plannedPath:
                color = ins.myColor
                if ins.status == "yield":
                    color = "magenta"
                plt.plot(ins.plannedPath.x, ins.plannedPath.y, color=color)
                plt.plot(ins.plannedPath.x[::10], ins.plannedPath.y[::10], color=color, marker='.', markersize=10, linewidth=0)
                plt.text(ins.pos_x, ins.pos_y+0.2, "PT:" + ins.plannedPath.pathID)
            #希望経路
            if ins.desiredPaths:
                plt.plot(ins.desiredPaths[0].x, ins.desiredPaths[0].y, color="red")
                plt.plot(ins.desiredPaths[0].x[::10], ins.desiredPaths[0].y[::10], color="red", marker=".", linewidth=0)
                plt.text(ins.pos_x, ins.pos_y-1, "DT:" + ins.desiredPaths[0].pathID)
            #代替経路
            if ins.alter_straight_path:    
                plt.plot(ins.alter_straight_path.x, ins.alter_straight_path.y, color="orange")
                plt.plot(ins.alter_straight_path.x[::10], ins.alter_straight_path.y[::10], color="orange", marker=".", linewidth=0)
                plt.text(ins.pos_x, ins.pos_y-1, "AT:" + ins.alter_straight_path.pathID)
            # if ins.alter_change_path:
            #     plt.plot(ins.alter_change_path.x[1:], ins.alter_change_path.y[1:], color="gold")
            #     plt.plot(ins.alter_change_path.x[::10], ins.alter_change_path.y[::10], color="gold", marker=".", linewidth=0)
            #     plt.text(ins.pos_x-15, ins.pos_y-1, "AT_C:" + ins.alter_change_path.pathID)

        for ins in vehicle_instance:
            color = ins.myColor
            if ins.status == "yield":
                color = "magenta"
                plt.text(ins.pos_x, ins.pos_y-1, "yield"+str(ins.leader))
            elif ins.desiredPaths:
                color = "red"

            #現在地
            # self.ax.add_artist(AnnotationBbox(carimg, [ins.pos_x, ins.pos_y], xycoords="data", frameon=False))
            plt.plot(ins.pos_x, ins.pos_y, color=color, marker=">", markersize=15)
            plt.text(ins.pos_x-10, ins.pos_y+1.0, str(round(ins.speed,2))+"m/s")
            plt.text(ins.pos_x-3.1, ins.pos_y-0.2, ins.id, color='white')
        
        plt.pause(0.001)