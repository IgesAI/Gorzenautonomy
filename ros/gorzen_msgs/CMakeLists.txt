cmake_minimum_required(VERSION 3.8)
project(gorzen_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/TelemetryFrame.msg"
  "msg/MissionPlan.msg"
  "msg/Waypoint.msg"
  "msg/MissionPredictions.msg"
  "msg/LegPrediction.msg"
  "msg/MissionProgress.msg"
  "msg/MissionStatus.msg"
  "msg/ValidationResult.msg"
  "msg/PreflightHealth.msg"
  "srv/UploadMission.srv"
  "srv/StartRecording.srv"
  "srv/StopRecording.srv"
  DEPENDENCIES std_msgs
)

ament_package()
