#!/bin/bash
# Demo script: System Status Logger
# This script logs system information to a file that can be displayed or checked
# Usage: Bind this script to a button action in the Hardware Buttons plugin settings

LOG_FILE="${HOME}/.inkypi_button_logs/system_status.log"
LOG_DIR="$(dirname "$LOG_FILE")"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Get current timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Collect system information
UPTIME=$(uptime -p 2>/dev/null || uptime | awk -F'up ' '{print $2}' | awk -F',' '{print $1}')
CPU_TEMP=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 || echo "N/A")
MEMORY=$(free -h | awk '/^Mem:/ {print $3 "/" $2 " (" $3/$2*100 "%)"}')
DISK=$(df -h / | awk 'NR==2 {print $3 "/" $2 " (" $5 " used)"}')
LOAD=$(uptime | awk -F'load average:' '{print $2}')

# Log the information
{
    echo "=========================================="
    echo "System Status - $TIMESTAMP"
    echo "=========================================="
    echo "Uptime: $UPTIME"
    echo "CPU Temperature: $CPU_TEMP"
    echo "Memory Usage: $MEMORY"
    echo "Disk Usage: $DISK"
    echo "Load Average: $LOAD"
    echo ""
} >> "$LOG_FILE"

# Also print to stdout (will be captured by plugin)
echo "System status logged to: $LOG_FILE"
echo "Uptime: $UPTIME | CPU: $CPU_TEMP | Memory: $MEMORY"

# Optional: Keep only last 50 entries to prevent log file from growing too large
tail -n 200 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"

exit 0
