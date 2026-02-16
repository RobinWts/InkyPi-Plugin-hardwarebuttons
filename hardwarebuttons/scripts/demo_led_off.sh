#!/bin/bash
# Demo script: Turn off Raspberry Pi LED
# This script disables the activity LED on Raspberry Pi Zero/other models
# Usage: Bind this script to a button action in the Hardware Buttons plugin settings

LOG_FILE="${HOME}/.inkypi_button_logs/led_control.log"
LOG_DIR="$(dirname "$LOG_FILE")"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Find the LED path (varies by Pi model)
LED_PATH=""
LED_NAME=""

# Common LED paths on different Pi models
for path in /sys/class/leds/led0 /sys/class/leds/ACT /sys/class/leds/led1; do
    if [ -d "$path" ]; then
        LED_PATH="$path"
        LED_NAME=$(basename "$path")
        break
    fi
done

if [ -z "$LED_PATH" ]; then
    ERROR_MSG="No LED found (checked led0, ACT, led1)"
    echo "$ERROR_MSG" >> "$LOG_FILE"
    echo "ERROR: $ERROR_MSG"
    exit 1
fi

# Save current trigger state to restore later
SAVE_FILE="${HOME}/.inkypi_button_logs/led_state_saved.txt"
CURRENT_TRIGGER=$(cat "${LED_PATH}/trigger" 2>/dev/null | grep -o '\[.*\]' | tr -d '[]' || echo "mmc0")
CURRENT_BRIGHTNESS=$(cat "${LED_PATH}/brightness" 2>/dev/null || echo "1")

# Save state for restoration
echo "trigger=${CURRENT_TRIGGER}" > "$SAVE_FILE"
echo "brightness=${CURRENT_BRIGHTNESS}" >> "$SAVE_FILE"
echo "led_path=${LED_PATH}" >> "$SAVE_FILE"

# Turn off LED: set trigger to 'none' and brightness to 0
if sudo sh -c "echo none > ${LED_PATH}/trigger && echo 0 > ${LED_PATH}/brightness" 2>/dev/null; then
    {
        echo "[$TIMESTAMP] LED turned OFF (${LED_NAME})"
        echo "  Previous trigger: $CURRENT_TRIGGER"
        echo "  Previous brightness: $CURRENT_BRIGHTNESS"
    } >> "$LOG_FILE"
    echo "LED turned OFF successfully (${LED_NAME})"
    exit 0
else
    ERROR_MSG="Failed to turn off LED - may need sudo permissions"
    echo "[$TIMESTAMP] ERROR: $ERROR_MSG" >> "$LOG_FILE"
    echo "ERROR: $ERROR_MSG"
    exit 1
fi
