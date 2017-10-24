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

import rospy
import tf
import numpy as np
from pyquaternion import Quaternion
import signal
import sys

import rospy

import autonomy.Task
import numpy as np


class InterruptError(Exception):
    def __init__(self, *args, **kwargs):
        super(InterruptError, self).__init__(*args, **kwargs)


class EndEffectorMoveTask(autonomy.Task):
    """
    Class that moves the end-effector to the next way-point
    """
    def __init__(self, station_nr=1):
        """
        Default constructor
        """
        autonomy.Task.SetTask.__init__(self)
        self.waypoints = rospy.get_param("~camera_calib_path")
        self.exec_thread = None
        self.index = 0  # position index
        self.listener = tf.TransformListener("ee_move_task_tf_listener")
        self.base_frame = rospy.get_param("base_frame", "gripper_ur5_base_link")
        self.ee_frame = rospy.get_param("ee_frame", "gripper_ur5_ee_link")

    def perform(self):
        """
        Hard coded task to pickup a water sample station from the robot, take a sample and return it to the robot
        :return: -
        :rtype: -
        """
        if self.index > len(self.waypoints)-1:
            self.index = 0
        else:
            self.index += 1
        rospy.loginfo("EndEffectorMoveTask.perform(): Move to Position "+str(self.index))
        self.move_wait(self.waypoints["pos_"+str(self.index)], v=self.j_arm_speed, a=self.j_arm_acceleration, move_cmd="movel")
        rospy.sleep(2.)
        self.exec_thread = None

    def getEEtransformation(self):
        """
        Returns the end-effector transformation once the arm stopped moving
        :return: end-effector to base transformation as affine transformation
        :rtype: numpy.matrix
        """
        while self.exec_thread is not None:
            rospy.sleep(.5)
            rospy.logdebug("EndEffectorMoveTask.perform(): Arm is moving to position "+str(self.index))
        Pe = np.diag(np.ones(4))
        Pe_trans = []
        Pe_rot = []
        q = Quaternion()
        R = q.rotation_matrix
        while not rospy.is_shutdown():
            # Get arm base to end effector transformation
            try:
                (Pe_trans, Pe_rot) = listener.lookupTransform(ee_frame, base_frame, rospy.Time(
                    0))  # return [t.x, t.y, t.z], [r.x, r.y, r.z, r.w]
                q = Quaternion(Pe_rot[3], Pe_rot[0], Pe_rot[1], Pe_rot[2])
                R = q.rotation_matrix
                Pe[0:3, 0:3] = R[0:3, 0:3]
                Pe[0:3, 3] = Pe_trans[0:3]
                rospy.loginfo("EndEffectorMoveTask.perform(): ee transformation\n"+Pe.__str__())
                break
                rospy.sleep(2.0)
            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                continue
        return Pe

if __name__ == '__main__':
    rospy.init_node("calib_camera_ee_transformation")
    arm_task = EndEffectorMoveTask()
    while not rospy.is_shutdown():
        arm_task.perform()
        arm_task.getEEtransformation()
        rospy.sleep(2.)