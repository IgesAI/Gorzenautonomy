"""Phase 1 launch: gorzen-bridge node only.

Runs the ROS 2 ↔ Gorzen planner bridge alongside the existing backend.
Assumes uXRCE-DDS agent is already running (either via docker-compose
or manually: `MicroXRCEAgent udp4 -p 8888`).

Usage:
    ros2 launch gorzen_bringup bridge_only.launch.py
    ros2 launch gorzen_bringup bridge_only.launch.py planner_url:=http://192.168.1.10:8000
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
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
            "forward_rate_hz",
            default_value="10.0",
            description="Rate (Hz) at which aggregated frames are forwarded to the planner",
        ),
        DeclareLaunchArgument(
            "vehicle_ns",
            default_value="",
            description="Vehicle namespace prefix for multi-vehicle (empty = single vehicle)",
        ),
        Node(
            package="gorzen_bridge",
            executable="bridge_node",
            name="gorzen_bridge",
            output="screen",
            parameters=[{
                "planner_url": LaunchConfiguration("planner_url"),
                "forward_rate_hz": LaunchConfiguration("forward_rate_hz"),
                "source": "ros2",
                "vehicle_ns": LaunchConfiguration("vehicle_ns"),
            }],
        ),
    ])
