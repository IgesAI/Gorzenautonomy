# Post-flight comparison of predicted vs actual outcomes.

std_msgs/Header header
string mission_id
string prediction_id
string source                   # "flight" or "simulation"

float64 actual_endurance_min
float64 actual_energy_wh
float64 delta_endurance_min
float64 delta_energy_wh

bool mission_completed
uint32 waypoints_reached
uint32 waypoints_total
