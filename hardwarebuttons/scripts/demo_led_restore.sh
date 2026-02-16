#!/bin/bash
# Demo script: Restore Raspberry Pi LED to normal function
# This script restores the activity LED to its default behavior
# Usage: Bind this script to a button action in the Hardware Buttons plugin settings

LOG_FILE="${HOME}/.inkypi_button_logs/led_control.log"
LOG_DIR="$(dirname "$LOG_FILE")"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Load saved state
SAVE_FILE="${HOME}/.inkypi_button_logs/led_state_saved.txt"

if [ ! -f "$SAVE_FILE" ]; then
    # No saved state, use defaults
    LED_PATH=""
    RESTORE_TRIGGER="mmc0"  # Default activity LED trigger
    RESTORE_BRIGHTNESS="1"
    
    # Try to find LED path
    for path in /sys/class/leds/led0 /sys/class/leds/ACT /sys/class/leds/led1; do
        if [ -d "$path" ]; then
            LED_PATH="$path"
            break
        fi
    done
else
    # Load saved state
    source "$SAVE_FILE" 2>/dev/null || true
    LED_PATH="${led_path:-}"
    RESTORE_TRIGGER="${trigger:-mmc0}"
    RESTORE_BRIGHTNESS="${brightness:-1}"
fi

if [ -z "$LED_PATH" ] || [ ! -d "$LED_PATH" ]; then
    # Try to find LED path if not saved or invalid
    for path in /sys/class/leds/led0 /sys/class/leds/ACT /sys/class/leds/led1; do
        if [ -d "$path" ]; then
            LED_PATH="$path"
            break
        fi
    done
fi

if [ -z "$LED_PATH" ] || [ ! -d "$LED_PATH" ]; then
    ERROR_MSG="No LED found (checked led0, ACT, led1)"
    echo "[$TIMESTAMP] ERROR: $ERROR_MSG" >> "$LOG_FILE"
    echo "ERROR: $ERROR_MSG"
    exit 1
fi

LED_NAME=$(basename "$LED_PATH")

# Restore LED: set trigger back and restore brightness
if sudo sh -c "echo ${RESTORE_TRIGGER} > ${LED_PATH}/trigger && echo ${RESTORE_BRIGHTNESS} > ${LED_PATH}/brightness" 2>/dev/null; then
    {
        echo "[$TIMESTAMP] LED restored to NORMAL (${LED_NAME})"
        echo "  Restored trigger: $RESTORE_TRIGGER"
        echo "  Restored brightness: $RESTORE_BRIGHTNESS"
    } >> "$LOG_FILE"
    echo "LED restored to normal function (${LED_NAME})"
    exit 0
else
    ERROR_MSG="Failed to restore LED - may need sudo permissions"
    echo "[$TIMESTAMP] ERROR: $ERROR_MSG" >> "$LOG_FILE"
    echo "ERROR: $ERROR_MSG"
    exit 1
fi
