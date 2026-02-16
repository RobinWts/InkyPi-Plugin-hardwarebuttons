#!/bin/bash
# Demo script: Button Event Logger
# This script logs button press events with timestamps and action type
# Usage: Bind this script to different button actions (short/double/long press) 
#        to track button usage patterns
#
# You can pass the action type via environment variable or detect from script path
# The plugin passes context, but for simplicity, this script uses the first argument

LOG_FILE="${HOME}/.inkypi_button_logs/button_events.log"
LOG_DIR="$(dirname "$LOG_FILE")"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Get current timestamp
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Determine action type from script path or argument
SCRIPT_NAME=$(basename "$0")
ACTION_TYPE="unknown"

# Check if this is being called with different script paths for different actions
# (You can create symlinks or copies: demo_button_logger_short.sh, demo_button_logger_double.sh, etc.)
case "$SCRIPT_NAME" in
    *short*)
        ACTION_TYPE="SHORT_PRESS"
        ;;
    *double*)
        ACTION_TYPE="DOUBLE_CLICK"
        ;;
    *long*)
        ACTION_TYPE="LONG_PRESS"
        ;;
    *)
        # Try to get from first argument if provided
        ACTION_TYPE="${1:-BUTTON_PRESS}"
        ;;
esac

# Log the event
{
    echo "[$TIMESTAMP] $ACTION_TYPE detected"
} >> "$LOG_FILE"

# Print confirmation (will be captured by plugin)
echo "Button event logged: $ACTION_TYPE at $TIMESTAMP"

# Optional: Keep only last 100 entries
tail -n 100 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"

exit 0
