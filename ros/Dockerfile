# Multi-stage Dockerfile for Gorzenautonomy ROS 2 packages.
# Built on ROS 2 Humble (LTS, Ubuntu 22.04) — the PX4-supported release.
#
# Build targets:
#   docker build --target gorzen-bridge -t gorzen-bridge ros/
#   docker build --target gorzen-full   -t gorzen-ros    ros/
#
# Uses network_mode: host at runtime so ROS 2 DDS can discover
# the uXRCE-DDS agent and other nodes on the same host.

# ── Stage 1: Build workspace ────────────────────────────────────────

FROM ros:humble-ros-base AS build

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /ws/src

# Clone px4_msgs for message definitions (pinned to main for Humble compatibility)
RUN git clone --depth 1 --branch main \
    https://github.com/PX4/px4_msgs.git /ws/src/px4_msgs

# Copy our packages
COPY gorzen_msgs/ /ws/src/gorzen_msgs/
COPY gorzen_bridge/ /ws/src/gorzen_bridge/
COPY gorzen_bringup/ /ws/src/gorzen_bringup/

# Install Python deps for the bridge
RUN pip3 install --no-cache-dir httpx

WORKDIR /ws

# Build all packages
RUN source /opt/ros/humble/setup.bash && \
    colcon build --symlink-install --cmake-args -DCMAKE_BUILD_TYPE=Release

# ── Stage 2: gorzen-bridge runtime ──────────────────────────────────

FROM ros:humble-ros-base AS gorzen-bridge

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir httpx

COPY --from=build /ws/install /ws/install

# Source workspace on every shell
RUN echo "source /ws/install/setup.bash" >> /root/.bashrc

ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ENTRYPOINT ["/bin/bash", "-c", "source /ws/install/setup.bash && ros2 run gorzen_bridge bridge_node --ros-args -p planner_url:=${GORZEN_API_URL:-http://localhost:8000} -p forward_rate_hz:=${FORWARD_RATE_HZ:-10.0} -p source:=${BRIDGE_SOURCE:-ros2} -p vehicle_ns:=${VEHICLE_NS:-}"]

# ── Stage 3: Full stack (bridge + bringup + future nodes) ──────────

FROM ros:humble-ros-base AS gorzen-full

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-colcon-common-extensions \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir httpx

COPY --from=build /ws/install /ws/install
COPY --from=build /ws/src /ws/src

RUN echo "source /ws/install/setup.bash" >> /root/.bashrc

ENV RMW_IMPLEMENTATION=rmw_fastrtps_cpp

CMD ["/bin/bash"]
