"""Full SITL launch: uXRCE-DDS agent + gorzen-bridge.

PX4 SITL + Gazebo Harmonic must be started separately (they manage their
own lifecycle). This launch file starts the ROS 2 side only.

Usage:
    # Terminal 1: PX4 SITL
    cd PX4-Autopilot && make px4_sitl gz_x500

    # Terminal 2: uXRCE-DDS agent
    MicroXRCEAgent udp4 -p 8888

    # Terminal 3: This launch file
    ros2 launch gorzen_bringup sitl.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        DeclareLaunchArgument(
            "planner_url",
            default_value="http://localhost:8000",
            description="Gorzen planner REST API base URL",
        ),
        DeclareLaunchArgument(
            "xrce_port",
            default_value="8888",
            description="uXRCE-DDS agent UDP port",
        ),
        DeclareLaunchArgument(
            "start_agent",
            default_value="true",
            description="Whether to start the uXRCE-DDS agent (set false if running externally)",
        ),

        # uXRCE-DDS Agent v2.x — the bridge between PX4 and ROS 2 DDS.
        # Launches only if start_agent=true.
        ExecuteProcess(
            cmd=[
                "MicroXRCEAgent", "udp4",
                "-p", LaunchConfiguration("xrce_port"),
            ],
            name="xrce_dds_agent",
            output="screen",
            condition=None,  # TODO: add IfCondition(start_agent) when wired
        ),

        # Delay bridge startup to let the agent initialize.
        TimerAction(
            period=2.0,
            actions=[
                Node(
                    package="gorzen_bridge",
                    executable="bridge_node",
                    name="gorzen_bridge",
                    output="screen",
                    parameters=[{
                        "planner_url": LaunchConfiguration("planner_url"),
                        "forward_rate_hz": 10.0,
                        "source": "ros2",
                        "vehicle_ns": "",
                    }],
                ),
            ],
        ),
    ])
