#!/usr/bin/python3.6
# -*- coding: utf-8 -*-
# Software License Agreement (BSD License)
#
# Copyright (c) 2020, TU Bergakademie Freiberg
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
from __future__ import print_function

import rosbag
import argparse
import sys

try:
    import autonomy.PoseGenerator as pg
    import autonomy.EvaluatePoseGenerator as ev
    import autonomy.MonteCarloClusterPoseGenerator as mc
except ImportError as ie:
    sys.path.append("/pkg/python/autonomy")
    import PoseGenerator as pg
    import EvaluatePoseGenerator as ev
    import MonteCarloClusterPoseGenerator as mc

DF_BAG_PATH = '/in/bag/buero.bag'
DF_IS = 0
DF_IE = -DF_IS
DF_VP = False


# from: https://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console
def progress(count, total, suffix=''):
    bar_len = 60
    filled_len = int(round(bar_len * count / float(total)))

    percents = round(100.0 * count / float(total), 1)
    balken = '=' * filled_len + '-' * (bar_len - filled_len)
    absolut = str(count) + "/" + str(total)

    sys.stdout.write('[%s] %s%s [%s] ...%s\r' % (balken, percents, '%', absolut, suffix))
    sys.stdout.flush()  # As suggested by Rom Ruben


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyse a BAG-file and plot results')
    parser.add_argument("-r", "--use_ros", action="store_true", default=False,
                        help="use parameters stored on the ROS Paramter server, if false commandline arguments could be used instead")
    parser.add_argument("-p", "--path", default=DF_BAG_PATH, help='Path of the BAG-file', type=str)
    parser.add_argument("-pd", "--plot_dir", default=pg.DF_PLT_SAVE_DIR,
                        help='Directory where the plots should be saved (will be created if not existent)', type=str)

    parser.add_argument("-pt", "--pub_topic", default=pg.DF_PUB_TOPIC, help='Publisher topic', type=str)
    parser.add_argument("-ot", "--obstacle_topic", default=pg.DF_OBS_TOPIC, help='Topic name of the obstacles',
                        type=str)
    parser.add_argument("-ft", "--floor_topic", default=pg.DF_FLR_TOPIC, help='Topic name of the floor', type=str)

    parser.add_argument("-ss", "--sub_sample", default=pg.DF_SUB_SAMPLE, help='Subsample rate', type=float)
    parser.add_argument("-nb", "--n_bins", default=pg.DF_N_BINS, help='[KDE] Number of Bins used ', type=int)
    parser.add_argument("-mcr", "--mc_raster", default=pg.DF_MC_RASTER, help='[Ref] Number of x and y line', type=int)
    parser.add_argument("-mc_wo", "--mc_weight_obstacle", default=pg.DF_MC_WO,
                        help='[Ref] Weight for obstacle distance',
                        type=float)
    parser.add_argument("-bh", "--histogram_bins", default=ev.DF_N_BINS, help='Number of Bins used in the Histograms '
                                                                              'during Evaluation', type=int)

    parser.add_argument("-is", "--start_index", default=DF_IS, help='Message number to start the analysis', type=int)
    parser.add_argument("-ie", "--end_index", default=DF_IE, help='Message number to end the analysis', type=int)

    parser.add_argument("-nc", "--n_cpu", default=mc.DF_N_CPU, help='Number of CPUs used for multiprocessing', type=int)
    parser.add_argument("-vp", "--verbose_plot", default=DF_IE,
                        help='Plot results for every new pair of obstacle and floor message', type=bool)

    args = parser.parse_args()

    if args.use_ros:
        print("Using ROS")
        import rospy

        rospy.init_node("evaluate_bag_set_pose", log_level=rospy.INFO)
        bag_path = rospy.get_param("~bag", DF_BAG_PATH)
        pub_topic = rospy.get_param("~pub_topic", pg.DF_PUB_TOPIC)
        floor_topic = rospy.get_param("~floor_topic", pg.DF_FLR_TOPIC)
        obstacles_topic = rospy.get_param("~obstacles_topic", pg.DF_OBS_TOPIC)
        sub_sample = rospy.get_param("~sub_sample", pg.DF_SUB_SAMPLE)
        n_bins = rospy.get_param("~n_bins", pg.DF_N_BINS)
        mc_raster = rospy.get_param("~ref_raster", pg.DF_MC_RASTER)
        plot_dir = rospy.get_param("~plot_dir", pg.DF_PLT_SAVE_DIR)
        mc_weight_obstacle = rospy.get_param("~ref_wo", pg.DF_MC_WO)
        histogram_bins = rospy.get_param("~histogram_bins", ev.DF_N_BINS)
        start_index = rospy.get_param("~start_index", DF_IS)
        end_index = rospy.get_param("~end_index", DF_IE)
        n_cpu = rospy.get_param("~n_cpu", mc.DF_N_CPU)
        verbose_plot = rospy.get_param("~verbose_plot", DF_VP)

    else:
        print("Using args")
        print(args)
        bag_path = args.path
        pub_topic = args.pub_topic
        floor_topic = args.floor_topic
        obstacles_topic = args.obstacle_topic
        sub_sample = args.sub_sample
        n_bins = args.n_bins
        mc_raster = args.mc_raster
        plot_dir = args.plot_dir
        mc_weight_obstacle = args.mc_weight_obstacle
        histogram_bins = args.histogram_bins
        start_index = args.start_index
        end_index = args.end_index
        n_cpu = args.n_cpu
        verbose_plot = args.verbose_plot

        from logging import basicConfig, getLogger, ERROR, INFO

        log = getLogger("not_ros")
        basicConfig(level=INFO)


        class rospy:
            logdebug = log.debug
            loginfo = log.info
            logwarn = log.warning
            logerr = log.error

    floor_msg = None
    obstacle_msg = None

    bag = rosbag.Bag(bag_path)
    n_msg = bag.get_message_count()
    i_msg = 0

    pca = pg.PcaPoseGenerator(pub_topic, obstacles_topic, floor_topic, sub_sample, args.use_ros)
    dln = pg.DelaunayPoseGenerator(pub_topic, obstacles_topic, floor_topic, sub_sample, args.use_ros)
    kde = pg.MinimalDensityEstimatePoseGenerator(pub_topic, obstacles_topic, floor_topic, sub_sample, args.use_ros,
                                                 n_bins)
    mcr = mc.MonteCarloClusterPoseGenerator(pub_topic, obstacles_topic, floor_topic, sub_sample, args.use_ros,
                                            mc_raster,
                                            mc_weight_obstacle, n_cpu)
    lst_gen = [pca, dln, kde, mcr]

    evaluation = ev.EvaluatePoseGenerators(lst_gen, save_dir=plot_dir, n_bins=histogram_bins, weight=mc_weight_obstacle)
    formats = ['.png', '.tex']

    rospy.loginfo("[evaluate_bag.py@main] Starting: bag has " + str(n_msg) + " messages")
    for topic, msg, t in bag.read_messages(topics=[floor_topic, obstacles_topic]):
        i_msg += 1
        progress(i_msg - 1, n_msg, suffix="of messages processed")
        if i_msg < start_index:
            continue
        if start_index < end_index < i_msg:
            break
        if topic in obstacles_topic:
            obstacle_msg = msg
        elif topic in floor_topic:
            floor_msg = msg
        else:
            rospy.loginfo("[evaluate_bag.py@main] unknown topic")
            continue

        if not pca.check_messages(obstacle_msg, floor_msg):
            continue
        try:
            evaluation.run(obs=obstacle_msg, flr=floor_msg)
            if verbose_plot:
                try:
                    # ev.view_general(lst_gen[0], show_it=False, print_it=True, ff=formats, save_to=plot_dir)
                    ev.view_all(lst_generator=lst_gen, show_it=False, print_it=True, ff=formats, save_to=plot_dir, index=i_msg)
                except IndexError as ie:
                    print("IndexError during view_all")
        except Exception as ex:
            rospy.logwarn("[evaluate_bag.py@main] Evaluation failed for message %d with error %s" % (i_msg, ex))

    # evaluation.plot_heatmap(print_it=True, ff=['.png', '.pgf', '.pdf'])
    # evaluation.distance_to(evaluation.dct_result[mcr.get_name()], print_it=True, show_it=False, ff=formats)
    evaluation.evaluate(print_it=True, ff=formats)
