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

import grasping.haf_client
import grasping.hand
import grasping.arm

import tf.transformations as tfs

from visualization_msgs.msg import *

class Controller(object):
    # see: http://docs.ros.org/hydro/api/pr2_moveit_tutorials/html/planning/src/doc/planning_scene_ros_api_tutorial.html

    def __init__(self):
        self.end_effector_link = rospy.get_param("end_effector_link", "gripper_ur5_ee_link")
        self.gripper_link = rospy.get_param("gripper_link", "gripper_robotiq_palm")

        self.haf_client = grasping.haf_client.HAFClient()
        rospy.loginfo("controller.py: Controller(): initilized HAF client")

        self.haf_client.add_grasp_cb_function(self.onGraspSearchCallback)

        self.moveit_controller = grasping.arm.MoveItWrapper()
        rospy.loginfo("controller.py: Controller(): initilized arm")

        self.hand_controller = grasping.hand.HandController()
        rospy.loginfo("controller.py: Controller(): initilized hand")

        self.tf_listener = tf.TransformListener()

        # rospy.loginfo("controller.py: Controller(): get transformation from ee to gripper")
        # now = rospy.Time.now()
        # # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): approach_vector = %s", approach_vector)
        # self.tf_listener.waitForTransform(self.gripper_link, self.end_effector_link, now, rospy.Duration(4))

        self.haf_client.register_pc_callback()

        # Debugging & Development tools
        # self.marker = Marker()
        # self.marker_pub = rospy.Publisher("cntrl_marker", Marker, queue_size=1)
        #
        # self.marker.id = 1
        # self.marker.ns = "controller"
        # self.marker.action = Marker.ADD
        # self.marker.type = Marker.MESH_RESOURCE
        # self.marker.mesh_resource = "package://robotiq_s_model_visualization/meshes/s-model_articulated/visual/full_hand.stl"
        # self.marker.scale.x = 1.
        # self.marker.scale.y = 1.
        # self.marker.scale.z = 1.
        # self.marker.color.r = 0.1
        # self.marker.color.g = 0.5
        # self.marker.color.b = 0.5
        # self.marker.color.a = 1.0
        # self.marker_frame_id = self.gripper_link

        rospy.loginfo("controller.py: Controller(): finished initialization")

    def calc_box_pose(self, grasp_pose):

        grasp_detection_frame = grasp_pose.header.frame_id
        approach_vector = rospy.get_param("gripper_approach_vector")
        now = rospy.Time.now()
        # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): approach_vector = %s", approach_vector)
        self.tf_listener.waitForTransform(grasp_detection_frame, self.end_effector_link, now, rospy.Duration(4))
        norm_av = [element/tfs.vector_norm(approach_vector) for element in approach_vector]
        # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): norm_av = %s", norm_av)
        offset = 0.07
        grasp_pose.pose.position.x -= offset * norm_av[0]
        grasp_pose.pose.position.y -= offset * norm_av[1]
        grasp_pose.pose.position.y -= offset * norm_av[2]
        return self.tf_listener.transformPose(self.end_effector_link, grasp_pose)

    def convert_grasp_pose(self, grasp_pose):
        ret_pose = grasp_pose
        now = rospy.Time.now()
        self.tf_listener.waitForTransform(self.gripper_link, self.end_effector_link, now, rospy.Duration(4))
        (t, r) = self.tf_listener.lookupTransform(target_frame=self.gripper_link, source_frame=self.end_effector_link,
                                                  time=now)
        rospy.loginfo("controller.py: Controller.convert_grasp_pose(): translation: %s", t)
        rospy.loginfo("controller.py: Controller.convert_grasp_pose(): rotation: %s", r)

        ret_pose.pose.position.x += t[0]
        ret_pose.pose.position.y += t[1]
        ret_pose.pose.position.z += t[2]
        ret_pose.pose.orientation = geometry_msgs.msg.Quaternion(*tf.transformations.quaternion_multiply(
            (grasp_pose.pose.orientation.x, grasp_pose.pose.orientation.y, grasp_pose.pose.orientation.z,
             grasp_pose.pose.orientation.w), r))
        # rotate_on_axis = tf.transformations.quaternion_about_axis(-1.0 * numpy.pi / 2.0, [0, 0, 1])
        return ret_pose

    def onGraspSearchCallback(self, grasp_pose):

        rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): received grasp_pose")  # : %s", grasp_pose)
        self.haf_client.remove_grasp_cb_function(self.onGraspSearchCallback)

        target_pose = self.convert_grasp_pose(grasp_pose)

        self.hand_controller.closeHand()
        origin = self.moveit_controller.get_current_joints()

        #transform from hand_link to ur5_ee_link
        # now = rospy.Time.now()
        # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): approach_vector = %s", approach_vector)
        # self.tf_listener.waitForTransform(grasp_pose.header.frame_id, self.end_effector_link, now,
        #                                   rospy.Duration(4))
        # target_pose = self.tf_listener.transformPose(self.end_effector_link, grasp_pose)
        # self.tf_listener.waitForTransform(grasp_pose.header.frame_id, "base_link", now,
        #                                   rospy.Duration(4))
        # base_pose = self.tf_listener.transformPose("base_link", grasp_pose)
        # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): grasp_pose: \n %s\n ", grasp_pose)
        # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): target_pose: \n %s\n ", target_pose)
        # rospy.loginfo("controller.py: Controller.onGraspSearchCallback(): base_pose: \n %s\n ", base_pose)

        if not self.moveit_controller.plan_to_pose(target_pose):
            # no plan calculated
            rospy.loginfo("Controller.onGraspSearchCallback(): couldn't calculate a plan, trying with next pose")
            self.haf_client.add_grasp_cb_function(self.onGraspSearchCallback)
            return

        # may wait for approval
        # raw_input("Press any key to continue ...")
        self.hand_controller.openHand()
        rospy.sleep(5.0)  # sleep so the hand can open

        execute_plan = True
        if execute_plan:
            rospy.loginfo("Controller.onGraspSearchCallback(): Execution: Moving towards grasp pose ")
            self.moveit_controller.move_to_pose()
        rospy.sleep(5.0)  # wait while the gripper moves towards the pose

        # grasp object
        rospy.loginfo("Controller.onGraspSearchCallback(): closing hand")
        self.hand_controller.closeHand()
        rospy.sleep(5.0)  # wait till the hand grasp the object

        # set an object at grasp point that can collide with the end_effector
        # box_pose = self.calc_box_pose(grasp_pose)
        # box_name ="one_box"
        # self.moveit_controller.attach_box(box_name, pose=grasp_pose, size=(0.07, 0.25, 0.4))

        # lift grasped object
        # plan path towards origin
        if not self.moveit_controller.plan_to_joints(origin):
            # no plan calculated
            rospy.loginfo("Controller.onGraspSearchCallback(): couldn't calculate to origin")
            return
        rospy.loginfo("Controller.onGraspSearchCallback(): Execution: Moving towards origin")
        # raw_input("Press any key to continue ...")
        self.moveit_controller.move_to_pose()
        rospy.sleep(5.0)  # wait while the arm returns to origin

        self.hand_controller.openHand()
        rospy.sleep(5.0)  # sleep so the hand can open

        # self.moveit_controller.remove_attached_object(box_name)
        rospy.loginfo("Controller.onGraspSearchCallback(): END")
        self.haf_client.add_grasp_cb_function(self.onGraspSearchCallback)


if __name__ == '__main__':
    rospy.init_node("tubaf_grasping_controller", anonymous=False)
    cntrl = Controller()
    rospy.spin()
