# Pre-flight predicted outcomes for a mission, stored for post-flight validation.

string mission_id
string prediction_id
float64 predicted_endurance_min
float64 predicted_energy_wh
float64 predicted_max_blur_px
float64 predicted_mean_gsd_cm
float64 mission_completion_probability
gorzen_msgs/LegPrediction[] legs
