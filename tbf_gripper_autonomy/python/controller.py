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
import tf.transformations
import copy
import random
import numpy

import grasping.haf_client
import grasping.hand
import grasping.arm


from visualization_msgs.msg import *
from std_srvs.srv import Empty
from ar_track_alvar_msgs.msg import AlvarMarkers as AlvarMarkers
from tbf_gripper_perception.srv import *
from geometry_msgs.msg import PoseArray, PoseStamped

"""@package grasping
This package is made to handle a grasping task. Assuming the object of interest is within vision of a defined camera.
The position of a grasp on this object is computed by the haf_grasping package and hand to a controller. This then
manages to grasp the object by making use of MoveIt! and a HandController.
@author: Steve Grehl
"""


class Controller(object):
    """
    Controller that handles a grasping/ pick up task. It does so by using a haf_graspin-Client, MoveIt-Wrapper and
    HandController. their functionality is utilized to solve the grasping task.
    """
    # see: http://docs.ros.org/hydro/api/pr2_moveit_tutorials/html/planning/src/doc/planning_scene_ros_api_tutorial.html

    def __init__(self):
        """
        Default constructor that loads parameter from the parameter server, register callbacks and publisher
        """
        rospy.loginfo("controller.py: Controller(): initializing")
        self.end_effector_link = rospy.get_param("~end_effector_link", "gripper_robotiq_palm_planning")
        self.base_link = rospy.get_param("~base_link", "gripper_ur5_base_link")
        self.target_object_name = rospy.get_param("~target_object_name", "wlan_box")

        self.haf_client = grasping.haf_client.HAFClient()
        rospy.loginfo("controller.py: Controller(): initialized HAF client")

        self.moveit_controller = grasping.arm.MoveItWrapper()
        self.moveit_controller.clear_attached_objects()
        rospy.loginfo("controller.py: Controller(): initialized arm")

        self.hand_controller = grasping.hand.HandController()
        rospy.loginfo("controller.py: Controller(): initialized hand")

        self.tf_listener = tf.TransformListener()
        rospy.sleep(1.0)  # sleep a bit so all transformations become known
        self.haf_client.add_grasp_cb_function(self.to_target_pose)

        self.origin_pose = self.moveit_controller.get_current_pose(frame_id=self.base_link)
        self.hover_pose = self.moveit_controller.get_current_pose(frame_id=self.base_link)

        self.marker_id = 1
        self.marker_pub = rospy.Publisher("/controller_marker", Marker, queue_size=1)
        self.ar_topic = rospy.get_param("~ar_topic", "/ar_pose_marker")
        self.ork_pose_topic = rospy.get_param("~ork_poses_topic", "/ork/obj_poses")
        self.sub_ar_track = None
        self.sub_ork_poses = None
        self.toggle_perception(True)

        rospy.loginfo("controller.py: Controller(): finished initialization")

    def convert_grasp_pose(self, grasp_pose):
        """
        Converts a given pose from the camera to the end-effector frame, used for planing in MoveIt!
        :param grasp_pose: pose of the object to grasp in camera_frame
        :type grasp_pose: PoseStamped
        :return: grasping pose in end-effector frame (last element of the kinematic chain)
        :rtype: PoseStamped
        """
        ret_pose = copy.deepcopy(grasp_pose)
        ret_pose.header.frame_id = self.base_link
        now = rospy.Time.now()

        self.tf_listener.waitForTransform(grasp_pose.header.frame_id, ret_pose.header.frame_id, now, rospy.Duration(4))
        ret_pose = self.tf_listener.transformPose(ret_pose.header.frame_id, ps=grasp_pose)
        return ret_pose

    def show_marker(self, pose_stamped):
        """
        Visualize a marker at the given pose in rviz by publishing
        :param pose_stamped: pose where the marker should be published
        :type pose_stamped: PoseStamped
        :return: -
        :rtype: -
        """
        a_marker = Marker()
        a_marker.header = pose_stamped.header
        a_marker.pose = pose_stamped.pose
        a_marker.action = Marker.ADD
        a_marker.type = Marker.ARROW
        a_marker.scale.x = 0.12
        a_marker.scale.y = 0.06
        a_marker.scale.z = 0.03
        a_marker.color.r = random.random()
        a_marker.color.g = 0.5
        a_marker.color.b = 0.5
        a_marker.color.a = 1.0
        a_marker.id = self.marker_id
        # self.marker_id += 1
        self.marker_pub.publish(a_marker)

    def _setup(self):
        """
        This function is called prior the hover_pose calculation and movement
        :return: -
        :rtype: None
        """
        self.hand_controller.closeHand()
        # Unsubscribe and continue with given pose
        self.sub_ar_track.unregister()
        self.sub_ork_poses.unregister()
        # self.toggle_perception(False)

    def to_hover_ork_pose(self, msg):
        """
        Callback from the Recognition-Node to move the robot over the object for grasp estimation
        :param msg: array with found obj poses
        :type msg: geometry_msgs.PoseArray
        :return: -
        :rtype: -
        """
        rospy.loginfo("Controller.to_hover_ork_pose(): starting")
        if len(msg.poses) < 1:
            rospy.loginfo("Controller.to_hover_ork_pose(): no pose")
            rospy.sleep(1.0)
            return
        self._setup()

        # Calculate the hover pose
        _hover_pose = PoseStamped()
        _hover_pose.pose = msg.poses[0]
        _hover_pose.header = msg.header

        # self.to_hover_pose(_hover_pose)
        # Skip one step
        self.haf_client.register_pc_callback()

    def to_hover_marker_pose(self, msg):
        """
        Callback from the Object Recognition (ar_track_alvar) to move the robot over the object for grasp estimation
        :param msg: ar marker pose
        :type msg: ar_track_alvar_msgs.msg.AlvarMarkers
        :return: -
        :rtype: -
        """
        rospy.loginfo("Controller.to_hover_marker_pose(): starting")
        if len(msg.markers) < 1:
            rospy.loginfo("Controller.to_hover_marker_pose(): no pose")
            rospy.sleep(1.0)
            return
        self._setup()

        # Calculate the hover pose
        self.to_hover_pose(msg.markers[0])

    def to_hover_pose(self, hover_pose):
        """
        After receiving a message from the recognition section and calculating a object pose this function tries to
        hover over the object
        :param hover_pose: pose to hover over
        :type hover_pose: geometry_msgs.PoseStamped
        :return: -
        :rtype: None
        """
        frame_from = hover_pose.header.frame_id
        frame_to = self.base_link
        # see:  http://wiki.ros.org/tf/TfUsingPython#TransformerROS_and_TransformListener
        #       http://wiki.ros.org/tf/Tutorials/tf%20and%20Time%20(Python)
        if self.tf_listener.frameExists(frame_from) and self.tf_listener.frameExists(frame_to):
            ps = hover_pose
            self.tf_listener.waitForTransform(frame_from, frame_to, rospy.Time(), rospy.Duration(4))
            tf_found = False
            while tf_found:
                try:
                    self.hover_pose = self.tf_listener.transformPose(frame_to, ps)
                    tf_found = True
                except Exception as ex:
                    rospy.logwarn("[cluster_analysis::ObjectFilter.transform] Couldn't Transform from " + frame_from +
                                  " to " + frame_to)
                    rospy.logwarn(ex.message)
                    tf_found = False
        else:
            rospy.logwarn(
                "[cluster_analysis::ObjectFilter.transform] Couldn't Transform from " + frame_from + " to " +
                frame_to)

        # self.hover_pose.pose.position.z += 0.8
        quat = tf.transformations.quaternion_from_euler(0, numpy.pi / 2.0, 0)
        self.hover_pose.pose.orientation.x = quat[0]
        self.hover_pose.pose.orientation.y = quat[1]
        self.hover_pose.pose.orientation.z = quat[2]
        self.hover_pose.pose.orientation.w = quat[3]

        # Move to Target
        rospy.loginfo("Controller.to_hover_pose(): to hover_pose")
        if not self.move_to_pose(self.hover_pose, self.origin_pose):
            rospy.logwarn("Controller.to_hover_pose(): Moving to hover_pose failed")
            self.toggle_perception(True)
            return

        # Next Step: Find a Grasp point -> haf_grasping
        self.haf_client.register_pc_callback()

    def to_target_pose(self, msg):
        """
        Callback after determining a grasp point
        :param msg: determined grasp point
        :type msg: geometry_msgs.PoseStamped
        :return: -
        :rtype: -
        """
        if msg is None:
            return
        # Unsubscribe and continue with given pose
        self.haf_client.unregister_pc_callback()

        # Determine if the target pose is correct
        answer = raw_input("Controller.to_target_pose(): Plan towards grasp? (y/n)")
        if answer != 'y':
            self.haf_client.register_pc_callback()
            return

        # Calculate the target pose
        rospy.logdebug("Controller.to_target_pose(): Pose.Frame: %s", msg.header.frame_id)
        msg.pose.position.x -= 0.04  # offset planning frame gripper -> gripper_robotiq_palm_planning
        self.toggle_perception(False)
        self.hand_controller.openHand()

        # Move to target pose
        if not self.move_to_pose(msg, self.origin_pose):
            rospy.logwarn("Controller.to_target_pose(): Moving to target_pose failed")
            self.toggle_perception(True)
            return

        # Next Step: Grasp the object
        self.grasp_object()

    def grasp_object(self):
        """
        Grasp an object after reaching a target pose determined by haf_grasping earlier
        :return: -
        :rtype: -
        """
        rospy.loginfo("Controller.grasp_object(): closing hand")
        self.hand_controller.closeHand()
        rospy.sleep(3.0)  # wait till the hand grasp the object
        obj_link = self.moveit_controller.grasped_object(self.target_object_name)

        # Next Step: lift object
        self.lift_object(obj_link, self.target_object_name)

    def lift_object(self, link="gripper_robotiq_palm_planning", name="/ar_pose_marker"):
        """
        Remove a previous attached object from the scene
        :param link: remove all that is connected to this link
        :type link: String
        :param name: id of the object
        :type name: String
        :return: -
        :rtype: -
        """
        while not self.move_to_pose(self.hover_pose, self.origin_pose):
            rospy.loginfo("Controller.lift_object(): try tp plan towards origin again ... ")
            rospy.sleep(0.5)

        hand_closed = True
        while hand_closed:
            answer = raw_input("Controller: Open Hand? (y/n) ...")
            if answer == 'y':
                self.hand_controller.openHand()
                rospy.loginfo("Controller.lift_object(): %s on link %s lifted", name, link)
                self.moveit_controller.remove_attached_object(link, name)
                hand_closed = False
            else:
                rospy.sleep(3.0)  # sleep so the hand can open
        self.hand_controller.restHand()

        go_on = False
        while not go_on:
            answer = raw_input("Controller: Start grasping again?(y/n)")
            if answer == 'y':
                self.toggle_perception(True)
            else:
                rospy.sleep(3.0)  # sleep so the hand can open

    def move_to_origin(self, origin):
        """
        Move the arm to the given joint set, that is assumed to be the origin of the gripper
        :param origin: joints
        :type origin: JointState
        :return: -
        :rtype: -
        """
        # plan path towards origin
        while not self.moveit_controller.plan_to_joints(origin):
            # no plan calculated
            answer = raw_input("Controller..move_to_pose(): couldn't calculate a plan - Plan again?"
                               " Clear Octomap and plan again? Abort? (y/c/n)")
            if answer == 'y' or answer == 'c':
                if answer == 'c':
                    rospy.wait_for_service("clear_octomap")
                    clear_octomap = rospy.ServiceProxy('clear_octomap', Empty)
                    clear_octomap()
            else:
                return False
        rospy.loginfo("Controller.move_to_origin(): Execution: Moving towards origin")
        # raw_input("Press any key to continue ...")
        executed = False
        try:
            while not rospy.is_shutdown() and not executed:
                executed = self.moveit_controller.move_to_pose()
                if executed:
                    rospy.loginfo("Controller.move_to_origin(): Execution: Moved to origin ")
                    # rospy.sleep(3.0)  # wait while the gripper moves towards the pose
                else:
                    # rospy.sleep(0.5)
                    rospy.loginfo("Controller.move_to_origin(): Execution: Try to move towards origin again")
        except:
            rospy.logerr("Controller.move_to_origin(): Error during Execution: PLaning to origin")
            if origin is not None:
                self.move_to_origin(origin)
            self.haf_client.register_pc_callback()
            return False
        return True

    def move_to_pose(self, pose, origin):
        """
        Move the arm to a given pose, if any error occurs or no plan can be found hold the origin for recovery
        :param pose: desired pose of the end-effector (defined by the group in the srdf)
        :type pose: PoseStamped
        :param origin: joint states of the origin
        :type origin: JointState
        :return: return if the pose could be reached within the tolerances (after execution)
        :rtype: Boolean
        """
        # Visualize target
        self.show_marker(pose)

        # Planing
        rospy.loginfo("Controller.move_to_pose(): planning")
        while not self.moveit_controller.plan_to_pose(pose):
            # rospy.loginfo("Controller.move_to_pose(): couldn't calculate a plan")
            answer = raw_input("Controller.move_to_pose(): couldn't calculate a plan - Plan again (p)?"
                               " Clear Octomap and plan again (c)? Abort (a)? Skip (s) ? (p/c/a/s)")
            if answer == 'p' or answer == 'c':
                if answer == 'c':
                    rospy.wait_for_service("clear_octomap")
                    clear_octomap = rospy.ServiceProxy('clear_octomap', Empty)
                    clear_octomap()
            elif answer == 's':
                return True
            else:
                if origin is not None:
                    self.move_to_pose(origin, pose)
                return False
        # Executing
        executed = False
        rospy.loginfo("Controller.move_to_pose(): Execution: Moving towards pose ")
        try:
            while not rospy.is_shutdown() and not executed:
                executed = self.moveit_controller.move_to_pose()
                if executed:
                    rospy.loginfo("Controller.move_to_pose(): Execution: Moved to pose ")
                    # rospy.sleep(3.0)  # wait while the gripper moves towards the pose
                else:
                    # rospy.sleep(0.5)
                    rospy.loginfo("Controller.move_to_pose(): Execution: Try to move again")
        except:
            rospy.logerr("Controller.move_to_pose(): Error during Execution: Planing to origin")
            if origin is not None:
                self.move_to_pose(origin, pose)
            return False
        return True

    def toggle_perception(self, active):
        """
        Activate/Deactivate the perception component
        :param active:
        :type active: Boolean
        :return: -
        :rtype: None
        """
        if active:
            self.sub_ar_track = rospy.Subscriber(name=self.ar_topic, data_class=AlvarMarkers,
                                                 callback=self.to_hover_marker_pose,
                                                 queue_size=1)
            self.sub_ork_poses = rospy.Subscriber(name=self.ork_pose_topic, data_class=PoseArray,
                                                  callback=self.to_hover_ork_pose,
                                                  queue_size=1)
        else:
            self.sub_ar_track.unregister()
            self.sub_ork_poses.unregister()

if __name__ == '__main__':
    print "Hello World: Starting controller.py"
    rospy.init_node("tubaf_grasping_controller", anonymous=False, log_level=rospy.DEBUG)
    cntrl = Controller()
    rospy.spin()
