# Aggregated vehicle telemetry snapshot, bridged to the Gorzen planner.
# Mirrors backend TelemetryFrame dataclass fields for 1:1 mapping.

std_msgs/Header header

# Position
float64 latitude_deg
float64 longitude_deg
float64 altitude_amsl_m
float64 altitude_agl_m

# Attitude (Euler, degrees)
float64 roll_deg
float64 pitch_deg
float64 yaw_deg

# Velocity (NED, m/s)
float64 vn_ms
float64 ve_ms
float64 vd_ms
float64 groundspeed_ms
float64 airspeed_ms
float64 climb_rate_ms

# Battery
float64 battery_voltage_v
float64 battery_current_a
float64 battery_remaining_pct

# GPS
uint8 gps_fix       # 0=NO_GPS .. 6=RTK_FIXED
uint8 satellites

# Status
bool armed
string flight_mode
bool in_air
bool health_ok

# Wind estimate (if available)
float64 wind_speed_ms
float64 wind_direction_deg
