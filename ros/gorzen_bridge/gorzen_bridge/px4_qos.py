"""PX4-compatible QoS profiles.

PX4's Micro XRCE-DDS client publishes with BEST_EFFORT reliability and
VOLATILE durability.  Using ROS 2 defaults (RELIABLE / TRANSIENT_LOCAL)
causes silent message drops.  Every subscriber to /fmu/* topics must use
these profiles.

Reference: https://docs.px4.io/main/en/ros2/user_guide.html#ros-2-qos-settings
"""

from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)

PX4_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    durability=DurabilityPolicy.VOLATILE,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

GORZEN_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)
