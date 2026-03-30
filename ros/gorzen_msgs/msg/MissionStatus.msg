# Mission state machine.

std_msgs/Header header
string mission_id

uint8 IDLE=0
uint8 UPLOADING=1
uint8 READY=2
uint8 RUNNING=3
uint8 PAUSED=4
uint8 DONE=5
uint8 FAILED=6

uint8 state
string detail
