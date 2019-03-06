#!/usr/bin/python
# Software License Agreement (MIT License)
#
# Copyright (c) 2018, TU Bergakademie Freiberg
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
# Author: grehl
import copy

import rospy
import tf
import message_filters

from geometry_msgs.msg import Pose, PoseStamped
import std_msgs.msg

from autonomy.Task import GraspTask
from autonomy.MoveitInterface import MoveitInterface
from tbf_gripper_tools.Equipment import Equipment
from tubaf_tools.help import invert_pose, add_pose
import tbf_gripper_rviz.ssb_marker as marker


def continue_by_console(text=None):
    """
    Prompt the console with a generic Y/N question and return the result
    :param text: optional quesion
    :type text: String
    :return: result
    :rtype: Bool
    """
    if text is None:
        print("Continue the program (Y/n)?: ")
    else:
        print(text+" (Y/n): ")
    inp = raw_input()
    if inp == "Y":
        return True
    elif inp == "n":
        return False
    else:
        return continue_by_console(text)


def continue_by_topic(topic=None):
    """
    Wait for a msg from a defined topic
    :param topic: name of the topic where the msg will be received
    :type topic: String
    :return: result
    :rtype: Bool
    """
    if topic is None:
        topic = rospy.get_param("~continue_topic", "/equipment_task/continue")
    subscriber = message_filters.Subscriber(topic, std_msgs.msg.Bool)
    cache = message_filters.Cache(subscriber, 5, allow_headerless=True)
    while cache.getLast() is None:
        rospy.sleep(2.0)
    return cache.getLast().data


class EquipmentTask(GraspTask):
    """
    Handle equipment using the gripper unit of Julius
    """

    def __init__(self):
        """
        Default constructor, start ROS, hand_model and demo_monitoring
        """

        # Init Moveit
        self.moveit = MoveitInterface("~moveit")
        # Equipment Parameter
        self.lst_equipment = []
        for equip in rospy.get_param("~equipment"):
            eq = Equipment(equip)
            self.moveit.add_equipment(eq)
            self.lst_equipment.append(eq)
        self.selected_equipment = self.lst_equipment[0]

        # Static joint values for specific well known poses
        self.backup_joint_values = rospy.get_param("~arm/backup_joint_values", [-180, -90, 0.0, -90, 0.00, 0.0])
        self.home_joint_values = rospy.get_param("~arm/home_joint_values", [-180, -90, 0.0, -90, 0.00, 0.0])
        self.watch_joint_values = rospy.get_param("~arm/watch_joint_values", [-180, -90, 0.0, -90, 0.00, 0.0])

        # @All parameters were imported@
        super(EquipmentTask, self).__init__(js_t=rospy.get_param("~arm/joint_states_topic"),
                                            bu_pos=self.backup_joint_values,
                                            ltcp_s=rospy.get_param("~arm/linear_tcp_speed"),
                                            ltcp_a=rospy.get_param("~arm/linear_tcp_acceleration"),
                                            j_s=rospy.get_param("~arm/joint_speed"),
                                            j_a=rospy.get_param("~arm/joint_acceleration"))

        self.tf_listener = tf.TransformListener(rospy.Duration.from_sec(15.0))
        rospy.loginfo("EquipmentTask.__init__(): initialized")

    def select_equipment(self, name="Smart Sensor Box"):
        """
        Select one of the equipment defined by the corresponding yaml file on the parameter server
        :param name: name of the equipment
        :type name: basestring
        :return: True if equipment was selected
        :rtype: bool
        """
        retValue = False
        for item in self.lst_equipment:
            retValue = item.name == name
            if retValue:
                self.selected_equipment = item
                return retValue
        return retValue

    def generate_goal(self, query_pose):
        """
        The pose may not be given in a frame suitable for stable planing, therefore you may change its reference frame
        and pose accordingly here
        :param query_pose: pose given
        :type query_pose: PoseStamped
        :return: pose expressed in suitable reference frame
        :rtype: PoseStamped
        """
        target_frame = self.moveit.group.get_pose_reference_frame()

        rospy.loginfo("EquipmentTask.generate_goal(): query_pose: \n %s", query_pose)
        rospy.logdebug("EquipmentTask.generate_goal(): moveit.group.get_pose_reference_frame(): \n %s", target_frame)

        return self.moveit.attached_equipment.get_grasp_pose(query_pose, target_frame, self.tf_listener)

    def perform(self, stages=range(9)):
        """
        Equipment Handle Task:
            0. Open Hand
            1. Scan Environment (HOME, Watch Pose)
            2. Pick Up Equipment (PreGrasp, Grasp)
            3. Update Planning Scene (PostGrasp)
            4. Query Set Pose
            5. Calculate target pose
            6. Move to intermediate pose (INTERMED_POSE)
            7. Move to set pose (TARGET_POSE)
            8. Return Equipment or Open Hand ([Grasp])
            9. Return to Home Pose (HOME)
        :return: -
        :rtype: -
        """
        stages = frozenset(stages)
        # 0. Open hand, in case smart equipment is still stuck
        if 0 in stages:
            rospy.loginfo("STAGE 0: Open Hand")
            rospy.loginfo("EquipmentTask.perform(): Equipment handling started - Robot starting at HOME position")
            self.hand_controller.openHand()
            rospy.sleep(1.0)
        # 1. Scan Environment
        if 1 in stages:
            rospy.loginfo("STAGE 1: Scan Env")
            rospy.loginfo("EquipmentTask.perform(): Closing hand  and scan the environment by given watch pose")
            self.hand_controller.closeHand()
            self.moveit.move_to_target(self.home_joint_values, info="HOME")
            self.moveit.move_to_target(self.watch_joint_values, info="Watch Pose")

        # 2. Pick Up Equipment
        if 2 in stages:
            rospy.loginfo("STAGE 2: Pickup Equipment")
            # TODO: Select Equipment
            self.moveit.move_to_target(self.selected_equipment.pick_waypoints["pre"], info="PreGrasp")
            rospy.loginfo("EquipmentTask.perform(): Opening hand ...")
            self.hand_controller.openHand()
            self.moveit.move_to_target(self.selected_equipment.pick_waypoints["grasp"], info="Grasp")
            rospy.loginfo("EquipmentTask.perform(): Grasp equipment")
            # Grasp station
            self.hand_controller.closeHand()
            rospy.sleep(5.)

        debug_pose_pub = rospy.Publisher("debug_target_pose", PoseStamped)
        # 3. Update Planning Scene - Attach collision object to end effector
        if 3 in stages:
            rospy.loginfo("STAGE 3: Update scene, Attach object")
            rospy.loginfo("EquipmentTask.perform(): Attach equipment to end effector")
            self.moveit.attach_equipment(self.selected_equipment)
            self.selected_equipment.calculate_grasp_offset(self.moveit.eef_link, self.moveit.group.get_planning_frame(),
                                                           self.tf_listener)
            self.moveit.move_to_target(self.selected_equipment.pick_waypoints["post"], info="PostGrasp")
            # self.moveit.move_to_target(self.selected_equipment.pick_waypoints["hover"], info="Hover")

        set_successfully = False
        while not set_successfully:
            # 4. Query Goal from User Interface
            if 4 in stages:
                rospy.loginfo("STAGE 4: Ask for target Pose")
                eq_set_pose = Pose()
                eq_set_pose.position.x -= 1.0
                int_marker = marker.SSBMarker(pose=eq_set_pose)
                query_pose_topic = int_marker.get_pose_topic()
                query_pose_subscriber = message_filters.Subscriber(query_pose_topic, PoseStamped)
                query_pose_cache = message_filters.Cache(query_pose_subscriber, 5)
                query_pose = None
                while query_pose is None:
                    query_pose = query_pose_cache.getLast()
                    rospy.logdebug("EquipmentTask.perform(): Set equipment to pose: \n %s", query_pose)
                    rospy.sleep(0.5)

            # 5. Calculate target pose
            if 5 in stages:
                rospy.loginfo("STAGE 5: Calculate Target Pose")
                rospy.loginfo("EquipmentTask.perform(): Set equipment ...")
                # Formulate Planning Problem
                self.moveit.clear_octomap_on_marker(int_marker)
                target_pose = self.generate_goal(query_pose)
                while target_pose is None:
                    rospy.loginfo("EquipmentTask.perform(): Query new Equipment Pose")
                    now = rospy.Time.now()
                    rospy.sleep(1.0)
                    query_pose = query_pose_cache.getLast()
                    if query_pose.header.time > now:
                        target_pose = self.generate_goal(query_pose)
                    else:
                        rospy.logdebug("EquipmentTask.perform(): No new Equipment Pose yet")
                rospy.sleep(2.0)
                # debug_pose_pub.publish(target_pose)

            if 6 in stages:
                rospy.loginfo("STAGE 6: Move to Intermediate Pose")
                # Plan Path using Moveit
                intermediate_pose = copy.deepcopy(target_pose.pose)
                intermediate_pose.position.z += 0.3
                # debug_pose_pub.publish(PoseStamped(pose=intermediate_pose, header=target_pose.header))
                if not self.moveit.move_to_target(intermediate_pose, info="INTERMED_POSE"):
                    continue

            if 7 in stages:
                rospy.loginfo("STAGE 7: Move to Target Pose")
                # debug_pose_pub.publish(target_pose)
                set_successfully = self.moveit.move_to_target(target_pose.pose, info="TARGET_POSE")

        if 8 in stages:
            rospy.loginfo("STAGE 8: Set equipment to Target Pose")
            if self.selected_equipment.hold_on_set != 0.0:
                rospy.sleep(self.selected_equipment.hold_on_set)
                self.moveit.move_to_target(self.selected_equipment.pick_waypoints["grasp"], info="Grasp")
            rospy.loginfo("EquipmentTask.perform(): Release Equipment")
            self.hand_controller.openHand()
            rospy.sleep(5.)
            self.moveit.scene.remove_attached_object(link=self.moveit.eef_link, name=self.selected_equipment.name)
            rospy.sleep(0.5)
            # self._setup_move_group()
            # Remove collision object from end effector
            # self._hand_ssb_broadcaster.stop()
            # self.eef_link = rospy.get_param("~eef_link", "gripper_robotiq_palm_planning")
            # self.move_wait(self.waypoints["set_down"], v=self.j_arm_speed, a=self.j_arm_acceleration,
            # move_cmd="movej")
        if 9 in stages:
            rospy.loginfo("STAGE 9: Return to home pose")
            # Plan back to home station
            self.moveit.move_to_target(self.home_joint_values, info="HOME")
            self.moveit.scene.remove_world_object(name=self.selected_equipment.name)
            rospy.sleep(0.5)
        rospy.loginfo("EquipmentTask.perform(): Finished")

    def start(self):
        """
        Start the equipment handle task
        :return: -
        :rtype: -
        """
        rospy.loginfo("GraspTask.start():")
        self.perform([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        # super(EquipmentTask, self).run_as_process(self.perform)


if __name__ == '__main__':
    rospy.init_node("EquipmentTask", log_level=rospy.INFO)
    obj = EquipmentTask()
    obj.start()

    rospy.spin()