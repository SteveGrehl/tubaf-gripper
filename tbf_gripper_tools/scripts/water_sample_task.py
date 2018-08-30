#!/usr/bin/python
# Software License Agreement (BSD License)
#
# Copyright (c) 2015, TU Bergakademie Freiberg
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the names of its
#       contributors may be used to endorse or promote products derived from
#       this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# author: grehl

import signal
import sys

import rospy

import autonomy.Task
import numpy as np


class InterruptError(Exception):
    def __init__(self, *args, **kwargs):
        super(InterruptError, self).__init__(*args, **kwargs)


def pos2str(pos):
    rad = np.deg2rad(pos)
    rad = map(str, rad)
    return "[" + ", ".join(rad) + "]"


def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


class WaterSampleTask(autonomy.Task.GraspTask):
    """
    Class to get a water sample
    """

    def __init__(self):
        """
        default constructor of the perform the sampling task
        """
        autonomy.Task.GraspTask.__init__(self)
        self.waypoints = rospy.get_param("~waypoints")
        self.exec_thread = None

    def perform(self):
        """
        Hard coded task to pickup a water sample station from the robot, take a sample and return it to the robot
        :return: -
        :rtype: -
        """
        rospy.loginfo("WaterSampleTask.perform(): Move to Station on top of the Robot starting at HOME position")
        # Move to Station on top of the Robot starting at HOME position
        self.move_wait(self.waypoints["home_pose"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.hand_controller.openHand()
        self.move_wait(self.waypoints["pre_pickup"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.move_wait(self.waypoints["pickup"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")

        rospy.loginfo("WaterSampleTask.perform(): Grasp station")
        # Grasp station
        self.hand_controller.closeHand()
        rospy.sleep(5.)
        self.move_wait(self.waypoints["lift"], v=self.l_arm_speed, a=self.l_arm_acceleration, move_cmd="movel")
        self.move_wait(self.waypoints["post_pickup"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")

        # Set station
        rospy.loginfo("WaterSampleTask.perform(): Set station")
        self.move_wait(self.waypoints["hover"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.move_wait(self.waypoints["sample_pose"], v=self.l_arm_speed, a=self.l_arm_acceleration, move_cmd="movel")

        rospy.loginfo("WaterSampleTask.perform(): Take sample -automatic-")
        # Take sample -automatic-
        rospy.sleep(30.)

        rospy.loginfo("WaterSampleTask.perform(): Lift station")
        # Lift station
        self.move_wait(self.waypoints["lifted"], v=self.l_arm_speed, a=self.l_arm_acceleration, move_cmd="movel")

        # TODO: check if successful

        rospy.loginfo("WaterSampleTask.perform(): Move to origin")
        # Move to origin
        self.move_wait(self.waypoints["post_pickup"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.move_wait(self.waypoints["lift"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.move_wait(self.waypoints["pickup"], v=self.l_arm_speed, a=self.l_arm_acceleration, move_cmd="movel")

        rospy.loginfo("WaterSampleTask.perform(): Release station")
        # Release station
        self.hand_controller.openHand()
        rospy.sleep(5.)

        rospy.loginfo("WaterSampleTask.perform(): Move back to home station")
        # Move back to home station
        self.move_wait(self.waypoints["lift"], v=self.l_arm_speed, a=self.l_arm_acceleration, move_cmd="movel")
        self.move_wait(self.waypoints["pre_pickup"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.move_wait(self.waypoints["home_pose"], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movej")
        self.hand_controller.closeHand()

        # self.exec_thread = None
        rospy.sleep(2.0)
        self.perform()

    def start(self):
        """
        Start the water Sample Task
        :return: -
        :rtype: -
        """
        rospy.loginfo("GraspTask.start():")
        self.run_as_process(WaterSampleTask.perform)


if __name__ == '__main__':
    rospy.init_node("WaterSampleTask")
    obj = WaterSampleTask()
    while obj.exec_thread is not None:
        rospy.sleep(0.5)
    obj.start()
    rospy.spin()
